"""Static checks for the study's Unity Catalog metric views (YAML specification 1.1) and their consumers.

Rules follow https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference (checked 2026-11-20) and the
study conventions in METRIC_VIEWS_GUIDE.md § 2. lint_view() checks one parsed definition; lint_query() checks a
stack-native query against the set of views. Both return a list of problems; an empty list means the input passes.

    python3 lint_metric_views.py            # lint metric_views/*.yaml and queries/**/*.sql; exit 1 on any problem
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
MIN_VERSION = 1.1
SCHEMA = "slc.semantic"

TOP_KEYS = {"version", "comment", "source", "filter", "joins", "fields", "measures", "materialization"}
FIELD_KEYS = {"name", "expr", "comment", "display_name", "synonyms", "format"}
MEASURE_KEYS = FIELD_KEYS | {"window"}
JOIN_KEYS = {"name", "source", "on", "using", "cardinality", "rely", "joins"}
WINDOW_KEYS = {"order", "range", "semiadditive", "offset"}
CARDINALITIES = {"many_to_one", "one_to_many"}
FORMAT_TYPES = {"number", "currency", "percentage"}
UNITS = r"(day|days|week|weeks|month|months|quarter|quarters|year|years)"
RANGE_RE = re.compile(rf"^(current|cumulative|all|(trailing|leading) [1-9][0-9]* {UNITS}( inclusive| exclusive)?)$")
OFFSET_RE = re.compile(r"^-?[1-9][0-9]* (day|days|month|months|year|years)$")
REFRESH_POLICIES = {"auto", "incremental", "incremental strict", "full"}
INVOKER_FUNCTIONS = re.compile(r"\b(current_user|session_user|user|is_member|is_account_group_member)\s*\(", re.I)
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MEASURE_CALL = re.compile(r"\bMEASURE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.I)
QUALIFIED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'")
AGGREGATE = re.compile(r"\b(SUM|COUNT|MIN|MAX|AVG|ANY_VALUE|COUNT_IF|APPROX_COUNT_DISTINCT|PERCENTILE|MEDIAN|MEASURE)\s*\(", re.I)


def _strip_literals(expr: str) -> str:
    return STRING_LITERAL.sub("''", expr)


def _metadata(kind: str, item: dict, problems: list[str]) -> None:
    name = item.get("name")
    display = item.get("display_name")
    if display is not None and (not isinstance(display, str) or not display or len(display) > 255):
        problems.append(f"{kind} {name}: display_name must be a string of 1-255 characters")
    synonyms = item.get("synonyms")
    if synonyms is not None:
        if not isinstance(synonyms, list) or len(synonyms) > 10:
            problems.append(f"{kind} {name}: synonyms must be a list of at most 10 strings")
        else:
            for s in synonyms:
                if not isinstance(s, str) or not s or len(s) > 255:
                    problems.append(f"{kind} {name}: synonym {s!r} must be a string of 1-255 characters")
    fmt = item.get("format")
    if fmt is not None:
        if not isinstance(fmt, dict) or fmt.get("type") not in FORMAT_TYPES:
            problems.append(f"{kind} {name}: format.type must be one of {sorted(FORMAT_TYPES)}")
            return
        if fmt["type"] == "currency" and not re.fullmatch(r"[A-Z]{3}", str(fmt.get("currency_code", ""))):
            problems.append(f"{kind} {name}: currency format needs a three-letter currency_code")
        places = fmt.get("decimal_places")
        if places is not None and not (isinstance(places, dict) and places.get("type") == "exact"
                                       and isinstance(places.get("places"), int) and 0 <= places["places"] <= 10):
            problems.append(f"{kind} {name}: decimal_places must be {{type: exact, places: 0-10}}")


def _joins(joins, problems: list[str], prefix: str = "") -> list[str]:
    """Validate joins recursively; return the alias paths usable as qualifiers (nested aliases as parent.child)."""
    aliases: list[str] = []
    if joins is None:
        return aliases
    if not isinstance(joins, list):
        problems.append("joins must be a list")
        return aliases
    for j in joins:
        if not isinstance(j, dict):
            problems.append(f"join entry {j!r} must be a mapping")
            continue
        name = j.get("name")
        unknown = set(j) - JOIN_KEYS
        if unknown:
            problems.append(f"join {name}: unknown keys {sorted(unknown)}")
        if not isinstance(name, str) or not NAME_RE.match(name):
            problems.append(f"join {name!r}: name must be lower_snake_case")
            continue
        if not isinstance(j.get("source"), str) or not j["source"].strip():
            problems.append(f"join {name}: source is required")
        if ("on" in j) == ("using" in j):
            problems.append(f"join {name}: exactly one of on or using is required")
        if "cardinality" in j and j["cardinality"] not in CARDINALITIES:
            problems.append(f"join {name}: cardinality must be one of {sorted(CARDINALITIES)}")
        rely = j.get("rely")
        if rely is not None and not (isinstance(rely, dict) and set(rely) <= {"at_most_one_match"}
                                     and isinstance(rely.get("at_most_one_match"), bool)):
            problems.append(f"join {name}: rely must be {{at_most_one_match: true|false}}")
        path = f"{prefix}{name}"
        if path in aliases:
            problems.append(f"join {path}: duplicate join name")
        aliases.append(path)
        aliases.extend(_joins(j.get("joins"), problems, prefix=f"{path}."))
    return aliases


def _qualifiers(expr: str) -> set[str]:
    return {m.group(1) for m in QUALIFIED.finditer(_strip_literals(expr))
            if not re.fullmatch(r"\d+", m.group(1))}


def lint_view(doc, view: str = "view") -> list[str]:
    """Problems in one parsed metric view definition; empty when it conforms."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return [f"{view}: definition must be a mapping"]
    unknown = set(doc) - TOP_KEYS
    if unknown:
        problems.append(f"{view}: unknown top-level keys {sorted(unknown)}")
    version = doc.get("version")
    if isinstance(version, bool) or not isinstance(version, (int, float)) or version < MIN_VERSION:
        problems.append(f"{view}: version must be a number >= {MIN_VERSION}, got {version!r}")
    if not isinstance(doc.get("source"), str) or not doc["source"].strip():
        problems.append(f"{view}: source is required")
    if "dimensions" in doc:
        problems.append(f"{view}: use fields, not dimensions")
    aliases = _joins(doc.get("joins"), problems)
    qualifiers_ok = {"source"} | {a.split(".")[0] for a in aliases} | {a.split(".")[-1] for a in aliases}

    fields = doc.get("fields") or []
    measures = doc.get("measures") or []
    if not isinstance(fields, list) or not isinstance(measures, list):
        return problems + [f"{view}: fields and measures must be lists"]
    if not fields and not measures:
        problems.append(f"{view}: fields or measures are required")

    seen: dict[str, str] = {}
    field_names: list[str] = []
    field_expr: dict[str, str] = {}
    for kind, items, keys in (("field", fields, FIELD_KEYS), ("measure", measures, MEASURE_KEYS)):
        for item in items:
            if not isinstance(item, dict):
                problems.append(f"{view}: {kind} entry {item!r} must be a mapping")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not NAME_RE.match(name):
                problems.append(f"{view}: {kind} name {name!r} must be lower_snake_case")
                continue
            if name.lower() in seen:
                problems.append(f"{view}: {kind} {name} duplicates a {seen[name.lower()]} name")
            seen[name.lower()] = kind
            unknown = set(item) - keys
            if unknown:
                problems.append(f"{view}: {kind} {name}: unknown keys {sorted(unknown)}")
            expr = item.get("expr")
            if not isinstance(expr, str) or not expr.strip():
                problems.append(f"{view}: {kind} {name}: expr is required")
                continue
            _metadata(f"{view}: {kind}", item, problems)
            for q in _qualifiers(expr) - qualifiers_ok:
                problems.append(f"{view}: {kind} {name}: qualifier {q!r} is neither source nor a join name")
            if kind == "field":
                if AGGREGATE.search(_strip_literals(expr)) and "OVER" not in expr.upper():
                    problems.append(f"{view}: field {name}: aggregate functions belong in measures")
                field_names.append(name)
                field_expr[name] = expr

    measure_names = {m["name"] for m in measures if isinstance(m, dict) and isinstance(m.get("name"), str)}
    deps: dict[str, set[str]] = {}
    for m in measures:
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not isinstance(m.get("expr"), str):
            continue
        name, expr = m["name"], m["expr"]
        refs = {r for r in MEASURE_CALL.findall(expr)}
        for r in refs - measure_names:
            problems.append(f"{view}: measure {name}: MEASURE({r}) references an undefined measure")
        if name in refs:
            problems.append(f"{view}: measure {name}: references itself")
        deps[name] = refs & measure_names
        if not AGGREGATE.search(_strip_literals(expr)):
            problems.append(f"{view}: measure {name}: expr must aggregate (an aggregate function or MEASURE())")
        window = m.get("window")
        if window is None:
            continue
        if not isinstance(window, list) or not window:
            problems.append(f"{view}: measure {name}: window must be a non-empty list")
            continue
        orders = []
        for w in window:
            if not isinstance(w, dict):
                problems.append(f"{view}: measure {name}: window entry {w!r} must be a mapping")
                continue
            unknown = set(w) - WINDOW_KEYS
            if unknown:
                problems.append(f"{view}: measure {name}: unknown window keys {sorted(unknown)}")
            order = w.get("order")
            if order not in field_names:
                problems.append(f"{view}: measure {name}: window order {order!r} is not a field")
            else:
                orders.append(order)
            if not isinstance(w.get("range"), str) or not RANGE_RE.match(w["range"]):
                problems.append(f"{view}: measure {name}: window range {w.get('range')!r} is not supported")
            if "semiadditive" in w and w["semiadditive"] not in {"first", "last"}:
                problems.append(f"{view}: measure {name}: semiadditive must be first or last")
            if "offset" in w and not (isinstance(w["offset"], str) and OFFSET_RE.match(w["offset"])):
                problems.append(f"{view}: measure {name}: offset {w['offset']!r} must be '<n> day|month|year'")
        # Coarser order fields of a multi-level window must be expressions over the finest one.
        for coarser in orders[1:]:
            if not re.search(rf"\b{re.escape(orders[0])}\b", field_expr.get(coarser, "")):
                problems.append(f"{view}: measure {name}: window order {coarser} is not derived from {orders[0]}")

    # Composition must be acyclic.
    state: dict[str, int] = {}

    def visit(n: str, stack: list[str]) -> None:
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            problems.append(f"{view}: measure cycle {' -> '.join(stack + [n])}")
            return
        state[n] = 1
        for d in sorted(deps.get(n, ())):
            visit(d, stack + [n])
        state[n] = 2

    for n in sorted(deps):
        visit(n, [])

    mat = doc.get("materialization")
    if mat is not None:
        problems.extend(_materialization(view, doc, mat, set(field_names), measure_names))
    return problems


def _materialization(view: str, doc: dict, mat, fields: set[str], measures: set[str]) -> list[str]:
    problems: list[str] = []
    if not isinstance(mat, dict):
        return [f"{view}: materialization must be a mapping"]
    unknown = set(mat) - {"schedule", "mode", "materialized_views"}
    if unknown:
        problems.append(f"{view}: materialization: unknown keys {sorted(unknown)}")
    if mat.get("mode") != "relaxed":
        problems.append(f"{view}: materialization.mode must be relaxed")
    if "schedule" in mat and not (isinstance(mat["schedule"], str)
                                  and re.fullmatch(r"every [1-9][0-9]* (minute|minutes|hour|hours|day|days|week|weeks)",
                                                   mat["schedule"])):
        problems.append(f"{view}: materialization.schedule {mat['schedule']!r} is not 'every <n> <unit>'")
    mvs = mat.get("materialized_views")
    if not isinstance(mvs, list) or not mvs:
        return problems + [f"{view}: materialization.materialized_views must be a non-empty list"]
    names, unaggregated = set(), 0
    for mv in mvs:
        if not isinstance(mv, dict):
            problems.append(f"{view}: materialized view entry {mv!r} must be a mapping")
            continue
        name = mv.get("name")
        unknown = set(mv) - {"name", "type", "dimensions", "measures", "cluster_by", "partition_by", "refresh_policy"}
        if unknown:
            problems.append(f"{view}: materialized view {name}: unknown keys {sorted(unknown)}")
        if name in names:
            problems.append(f"{view}: materialized view {name}: duplicate name")
        names.add(name)
        kind = mv.get("type")
        if kind == "unaggregated":
            unaggregated += 1
            if "dimensions" in mv or "measures" in mv:
                problems.append(f"{view}: materialized view {name}: unaggregated takes no dimensions or measures")
        elif kind == "aggregated":
            if not mv.get("dimensions") and not mv.get("measures"):
                problems.append(f"{view}: materialized view {name}: aggregated needs dimensions or measures")
            for d in mv.get("dimensions") or []:
                if d not in fields:
                    problems.append(f"{view}: materialized view {name}: dimension {d!r} is not a field")
            for m in mv.get("measures") or []:
                if m not in measures:
                    problems.append(f"{view}: materialized view {name}: measure {m!r} is not a measure")
        else:
            problems.append(f"{view}: materialized view {name}: type must be aggregated or unaggregated")
        if "cluster_by" in mv and "partition_by" in mv:
            problems.append(f"{view}: materialized view {name}: cluster_by and partition_by are exclusive")
        cb = mv.get("cluster_by")
        if cb is not None:
            if not isinstance(cb, dict) or (("cols" in cb) == ("auto" in cb)):
                problems.append(f"{view}: materialized view {name}: cluster_by needs exactly one of cols or auto")
            elif "cols" in cb and kind == "aggregated":
                for c in cb["cols"]:
                    if c not in (mv.get("dimensions") or []):
                        problems.append(f"{view}: materialized view {name}: cluster column {c!r} is not materialized")
        rp = mv.get("refresh_policy")
        if rp is not None and str(rp).lower() not in REFRESH_POLICIES:
            problems.append(f"{view}: materialized view {name}: refresh_policy {rp!r} is not supported")
    if unaggregated > 1:
        problems.append(f"{view}: at most one unaggregated materialization is allowed")
    texts = [doc.get("filter") or ""] + [i.get("expr", "") for i in (doc.get("fields") or []) + (doc.get("measures") or [])
                                         if isinstance(i, dict)]
    if any(INVOKER_FUNCTIONS.search(t) for t in texts):
        problems.append(f"{view}: materialized views cannot use invoker-dependent functions")
    return problems


def lint_query(sql: str, views: dict[str, dict], query_id: str = "query") -> list[str]:
    """A stack-native query reads only slc.semantic metric views, and every MEASURE() names a measure of one of them."""
    problems: list[str] = []
    code = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    code = _strip_literals(code)
    refs = re.findall(r"\bslc\.([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", code)
    if not refs:
        problems.append(f"{query_id}: reads no {SCHEMA} metric view")
    used: set[str] = set()
    for schema, view in refs:
        if schema != "semantic":
            problems.append(f"{query_id}: reads slc.{schema}.{view}; only {SCHEMA} metric views are allowed")
        elif view not in views:
            problems.append(f"{query_id}: {SCHEMA}.{view} is not a defined metric view")
        else:
            used.add(view)
    available = {m["name"] for v in used for m in views[v].get("measures", [])}
    for name in MEASURE_CALL.findall(code):
        if used and name not in available:
            problems.append(f"{query_id}: MEASURE({name}) is not a measure of {sorted(used)}")
    if re.search(r"\b(fact_|dim_|bridge_)\w+", re.sub(r"\bslc\.semantic\.\w+", "", code)):
        problems.append(f"{query_id}: references a physical table name")
    return problems


def load_views() -> dict[str, dict]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted((HERE / "metric_views").glob("*.yaml"))}


def main() -> None:
    views = load_views()
    problems: list[str] = []
    for view, doc in views.items():
        problems += lint_view(doc, view)
    for path in sorted((HERE / "queries").glob("*/*.sql")):
        problems += lint_query(path.read_text(), views, path.stem)
    for p in problems:
        print(p)
    count = len(list((HERE / "queries").glob("*/*.sql")))
    print(f"{len(views)} metric views, {count} queries, {len(problems)} problems")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
