#!/usr/bin/env python3
"""Static checks for the S3 Tableau artifacts. Every check returns a list of problems; empty means conforming.

- validate_tds(): XML well-formedness and validation against Tableau's official 2026.3 document schema
  (schemas/vendor/twb_2026.3.0.xsd via schemas/tds.xsd).
- lint_tds(): cross-references inside a data source: calculation, filter, relationship and column-map references
  resolve; calculation syntax is balanced; functions are known Tableau functions; LOD expressions are well formed.
- validate_query(): a VDS query against the OpenAPI 20263.0 Query schema, with the Field oneOf and the Filter
  discriminator resolved, plus model cross-references (captions exist, AGG only on aggregate calculations, parameters
  exist, ad hoc calculation references resolve, aliases unique).
- assemble_columns(): runs a question's assembly over empty typed tables in DuckDB and returns its output columns.

    python3 lint_tableau.py     # lint everything; exit 1 on any problem
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from model import BY_NAME, Calc, DataSource, Param  # noqa: E402

SCHEMAS = HERE / "schemas"
OPENAPI = SCHEMAS / "vendor" / "VizQLDataServiceOpenAPISchema_20263.0.json"
KNOWN_FUNCTIONS = {
    "SUM", "COUNT", "COUNTD", "MIN", "MAX", "AVG", "ZN", "IIF", "DATEDIFF", "DATEADD", "DATETRUNC", "DATEPART", "DATE",
    "DAY", "YEAR", "ISMEMBEROF", "ISNULL", "STR", "ABS",
}
KEYWORDS = {"IF", "THEN", "ELSE", "ELSEIF", "END", "AND", "OR", "NOT", "NULL", "TRUE", "FALSE", "FIXED", "INCLUDE",
            "EXCLUDE", "CASE", "WHEN", "IN"}
STRING = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
DATE_LITERAL = re.compile(r"#\d{4}-\d{2}-\d{2}#")
REF = re.compile(r"\[([^\]]+)\]")
FUNC = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
LOD = re.compile(r"\{\s*(FIXED|INCLUDE|EXCLUDE)\b([^{}:]*):([^{}]*)\}")


@lru_cache(maxsize=1)
def _tds_schema():
    import xmlschema
    return xmlschema.XMLSchema(str(SCHEMAS / "tds.xsd"))


def validate_tds(text: str) -> list[str]:
    try:
        ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    return [f"{e.reason} at {e.path}" for e in _tds_schema().iter_errors(text)]


def lint_formula(formula: str, names: set[str], where: str) -> list[str]:
    problems = []
    code = DATE_LITERAL.sub("0", STRING.sub("''", formula))
    for open_, close in ("()", "[]", "{}"):
        depth = 0
        for ch in code:
            depth += (ch == open_) - (ch == close)
            if depth < 0:
                break
        if depth != 0:
            problems.append(f"{where}: unbalanced {open_}{close}")
    for ref in REF.findall(code):
        if ref not in names:
            problems.append(f"{where}: reference [{ref}] does not resolve")
    for fn in FUNC.findall(re.sub(r"\[[^\]]*\]", "", code)):
        if fn.upper() not in KNOWN_FUNCTIONS and fn.upper() not in KEYWORDS:
            problems.append(f"{where}: unknown function {fn}")
    for brace in re.findall(r"\{[^{}]*\}", code):
        m = LOD.fullmatch(brace)
        if not m:
            problems.append(f"{where}: malformed level-of-detail expression {brace}")
        elif not re.search(r"\b(SUM|COUNT|COUNTD|MIN|MAX|AVG)\s*\(", m.group(3)):
            problems.append(f"{where}: level-of-detail expression without an aggregate")
    if re.search(r"\bIF\b", code, re.I) and not re.search(r"\bEND\b", code, re.I):
        problems.append(f"{where}: IF without END")
    return problems


def lint_tds(text: str) -> list[str]:
    """Cross-reference checks on a rendered data source."""
    problems: list[str] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    columns = {c.get("name")[1:-1]: c for c in root.findall("column")}
    names = set(columns)
    captions = [c.get("caption") for c in root.findall("column")]
    dupes = sorted({c for c in captions if captions.count(c) > 1})
    if dupes:
        problems.append(f"duplicate captions {dupes}")
    for name, col in columns.items():
        calc_el = col.find("calculation")
        if calc_el is not None and col.get("param-domain-type") is None:
            problems += lint_formula(calc_el.get("formula", ""), names, f"calculation {name}")
    for flt in root.findall("filter"):
        target = flt.get("column", "")[1:-1]
        col = columns.get(target)
        if col is None:
            problems.append(f"filter on undefined field [{target}]")
        elif col.get("datatype") != "boolean" or col.find("calculation") is None:
            problems.append(f"filter field [{target}] is not a boolean calculation")
    objects = root.findall("object-graph/objects/object")
    ids = [o.get("id") for o in objects]
    if len(ids) != len(set(ids)):
        problems.append("duplicate object ids")
    table_cols: dict[str, set[str]] = {}
    maps = root.findall("connection/cols/map")
    for m in maps:
        key, value = m.get("key")[1:-1], m.get("value")
        table = value.split("].[")[0][1:]
        table_cols.setdefault(table, set()).add(key)
        if key not in columns:
            problems.append(f"column map {key} has no column declaration")
    caption_of = {o.get("id"): o.get("caption") for o in objects}
    for rel in root.findall("object-graph/relationships/relationship"):
        first = rel.find("first-end-point").get("object-id")
        second = rel.find("second-end-point").get("object-id")
        for end in (first, second):
            if end not in caption_of:
                problems.append(f"relationship end point {end} is not an object")
        refs = [e.get("op")[1:-1] for e in rel.iter("expression") if e.get("op", "").startswith("[")]
        if len(refs) % 2:
            problems.append(f"relationship {first}-{second} has an odd number of field references")
        for i in range(0, len(refs), 2):
            a, b = refs[i], refs[i + 1]
            if a not in table_cols.get(caption_of.get(first, ""), set()):
                problems.append(f"relationship {first}-{second}: [{a}] is not a column of {first}")
            if b not in table_cols.get(caption_of.get(second, ""), set()):
                problems.append(f"relationship {first}-{second}: [{b}] is not a column of {second}")
    graph_ids = set(ids)
    for o in objects:
        rel = o.find("properties/relation")
        if rel is None or not (rel.text or "").strip():
            problems.append(f"object {o.get('id')} has no relation")
    if objects:
        linked = {e.get("object-id") for e in root.iter() if e.tag in ("first-end-point", "second-end-point")}
        isolated = graph_ids - linked
        if len(objects) > 1 and isolated:
            problems.append(f"objects not related to any other object: {sorted(isolated)}")
    return problems


# --------------------------------------------------------------------------- VDS queries


@lru_cache(maxsize=1)
def _openapi() -> dict:
    return json.loads(OPENAPI.read_text())


def _schema(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}", "components": _openapi()["components"]}


def _validate(instance, name: str) -> list[str]:
    import jsonschema
    validator = jsonschema.Draft4Validator(_schema(name))
    return [f"{name}: {e.message} at {list(e.absolute_path)}" for e in validator.iter_errors(instance)]


def validate_query_schema(query: dict) -> list[str]:
    problems = _validate(query, "Query")
    mapping = _openapi()["components"]["schemas"]["Filter"]["discriminator"]["mapping"]
    for i, flt in enumerate(query.get("filters", [])):
        target = mapping.get(flt.get("filterType"))
        if target is None:
            problems.append(f"filter {i}: unknown filterType {flt.get('filterType')!r}")
            continue
        sub = target.rsplit("/", 1)[1]
        problems += [f"filter {i}: {p}" for p in _validate(flt, sub)]
        allowed = _filter_properties(sub)
        extra = set(flt) - allowed
        if extra:
            problems.append(f"filter {i}: properties {sorted(extra)} are not defined for {sub}")
    return problems


@lru_cache(maxsize=None)
def _filter_properties(name: str) -> frozenset:
    schemas = _openapi()["components"]["schemas"]
    props: set[str] = set()

    def walk(s: dict) -> None:
        if "$ref" in s:
            walk(schemas[s["$ref"].rsplit("/", 1)[1]])
            return
        props.update(s.get("properties", {}))
        for part in s.get("allOf", []):
            walk(part)

    walk(schemas[name])
    return frozenset(props)


def validate_query(spec: dict, where: str = "query") -> list[str]:
    """Schema and model checks for one {datasource, query, output} spec."""
    problems = [f"{where}: {p}" for p in validate_query_schema(spec["query"])]
    ds = BY_NAME.get(spec.get("datasource"))
    if ds is None:
        return problems + [f"{where}: unknown data source {spec.get('datasource')!r}"]
    fields = ds.fields()
    captions = set(fields)
    aliases = []
    for f in spec["query"].get("fields", []):
        cap = f.get("fieldCaption", "")
        aliases.append(f.get("fieldAlias"))
        if "calculation" in f:
            problems += lint_formula(f["calculation"], captions, f"{where}: calculation {cap}")
            if cap in captions:
                problems.append(f"{where}: ad hoc calculation caption {cap!r} shadows a data source field")
            continue
        target = fields.get(cap)
        if target is None:
            problems.append(f"{where}: field {cap!r} is not defined in {ds.name}")
            continue
        fn = f.get("function")
        if fn == "AGG" and not (isinstance(target, Calc) and target.role == "measure"):
            problems.append(f"{where}: AGG on {cap!r}, which is not an aggregate calculation")
        if fn is None and isinstance(target, Calc) and target.role == "measure":
            problems.append(f"{where}: aggregate calculation {cap!r} queried without function AGG")
        if isinstance(target, Param):
            problems.append(f"{where}: parameter {cap!r} queried as a field")
    if None in aliases or len(aliases) != len(set(aliases)):
        problems.append(f"{where}: every field needs a unique fieldAlias")
    if set(spec.get("output", {})) != set(a for a in aliases if a):
        problems.append(f"{where}: output types do not match the field aliases")
    for flt in spec["query"].get("filters", []):
        fld = flt["field"]
        if "fieldCaption" in fld and fld["fieldCaption"] not in captions:
            problems.append(f"{where}: filter field {fld['fieldCaption']!r} is not defined in {ds.name}")
        if "calculation" in fld:
            problems += lint_formula(fld["calculation"], captions, f"{where}: filter calculation")
    params = {p.caption for p in ds.params}
    for p in spec["query"].get("parameters", []):
        if p["parameterCaption"] not in params:
            problems.append(f"{where}: parameter {p['parameterCaption']!r} is not defined in {ds.name}")
    return problems


def lint_metric(spec: dict) -> list[str]:
    problems = []
    for i, b in enumerate(spec["branches"]):
        where = f"{spec['metric']} branch {i} ({b['grain']})"
        problems += validate_query(b, where)
        out = set(b.get("output", {}))
        for m in b["members"]:
            if m != "@anchor" and m not in out:
                problems.append(f"{where}: member alias {m!r} is not an output")
        if len(b["members"]) > 3:
            problems.append(f"{where}: more than three members")
        for label, alias in b["values"].items():
            if alias not in out:
                problems.append(f"{where}: value alias {alias!r} for {label} is not an output")
        if "anchors" in b:
            if b.get("anchor_parameter") not in {p.caption for p in BY_NAME[b["datasource"]].params}:
                problems.append(f"{where}: anchor parameter is not a data source parameter")
            if not b["anchors"] or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a[0]) for a in b["anchors"]):
                problems.append(f"{where}: anchors must be ISO dates")
            if "@anchor" in b["members"] and any(a[1] is None for a in b["anchors"]):
                problems.append(f"{where}: anchored member without a label")
    return problems


def assemble_columns(spec: dict) -> list[str]:
    """Execute the assembly over empty typed tables; return the output column names."""
    import duckdb
    con = duckdb.connect()
    try:
        for name, q in spec["queries"].items():
            cols = ", ".join(f'"{a}" {t}' for a, t in q["output"].items())
            con.execute(f'CREATE TABLE "{name}" ({cols})')
        cur = con.execute(spec["assemble"])
        return [d[0] for d in cur.description]
    finally:
        con.close()


def lint_question(spec: dict) -> list[str]:
    problems = []
    for name, q in spec["queries"].items():
        problems += validate_query(q, f"{spec['question']} query {name}")
    code = STRING.sub("''", spec["assemble"])
    known = set(spec["queries"])
    for t in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", code, re.I):
        if t.lower() not in {k.lower() for k in known} and not re.search(rf"\b{t}\s+AS\s*\(", code, re.I):
            problems.append(f"{spec['question']}: assembly reads {t!r}, which is neither a query result nor a CTE")
    if re.search(r"\bslc\.|\bfact_|\bdim_|\bbridge_", code):
        problems.append(f"{spec['question']}: assembly references physical tables")
    try:
        assemble_columns(spec)
    except Exception as exc:  # duckdb raises its own error hierarchy
        problems.append(f"{spec['question']}: assembly does not run: {str(exc).splitlines()[0]}")
    return problems


def load(kind: str) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted((HERE / "queries" / kind).glob("*.json"))}


def lint_all() -> list[str]:
    problems: list[str] = []
    for ds in BY_NAME.values():
        text = (HERE / "datasources" / ds.file).read_text()
        problems += [f"{ds.file}: {p}" for p in validate_tds(text) + lint_tds(text)]
    for spec in load("metrics").values():
        problems += lint_metric(spec)
    for spec in load("questions").values():
        problems += lint_question(spec)
    return problems


def main() -> None:
    problems = lint_all()
    for p in problems:
        print(p)
    print(f"{len(BY_NAME)} data sources, {len(load('metrics'))} metric specs, {len(load('questions'))} question specs, "
          f"{len(problems)} problems")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
