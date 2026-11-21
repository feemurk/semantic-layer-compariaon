"""Static checks for the S2 semantic models (TMDL) and their DAX queries.

- parse_tmdl(): a TMDL reader for the subset this study generates (database, model, tables with measures, columns,
  hierarchies, partitions and refresh policies, relationships, expressions, roles, cultures), following the syntax rules
  of https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview (tab indentation, `name = expression`
  defaults, `key: value` properties, `///` descriptions, multi-line expressions one level deeper than properties).
- check_model(): structural integrity, relationship integrity and filter-path ambiguity, measure DAX references,
  RLS expressions, and the Best Practice Analyzer rules of deploy/bpa_rules.json (same rule ids).
- check_query(): DAX query references (tables, columns, measures, functions) against a parsed model, balanced
  parentheses, a single top-level EVALUATE, and output column names via output_columns().

Every check returns a list of problems; an empty list means the input passes.

    python lint_model.py   # lint every model under models/ and every query; exit 1 on any problem
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
QUERIES = HERE / "queries"

DAX_FUNCTIONS = {
    "ABS", "ADDCOLUMNS", "ALL", "BLANK", "CALCULATE", "COALESCE", "CONVERT", "COUNT", "COUNTROWS", "CURRENTGROUP", "DATE",
    "DATESBETWEEN", "DAY", "DISTINCT", "DISTINCTCOUNT", "DIVIDE", "EDATE", "EOMONTH", "FALSE", "FILTER", "FORMAT", "GROUPBY",
    "IF", "INT", "ISBLANK", "ISCROSSFILTERED", "KEEPFILTERS", "LOOKUPVALUE", "MAX", "MAXX", "MIN", "MINX", "MONTH", "NOT",
    "ORDERBY", "REMOVEFILTERS", "ROW", "ROWNUMBER", "SELECTCOLUMNS", "SUM", "SUMMARIZE", "SUMMARIZECOLUMNS", "SUMX", "TOPN",
    "TREATAS", "TRUE", "UNION", "VALUES", "YEAR",
}
DAX_KEYWORDS = {"VAR", "RETURN", "DEFINE", "EVALUATE", "ORDER", "BY", "ASC", "DESC", "IN", "STRING", "INTEGER", "DOUBLE",
                "CURRENCY", "BOOLEAN", "DATETIME", "TRUE", "FALSE", "NOT", "AND", "OR", "MEASURE", "TABLE", "COLUMN"}
OBJECT_KEYWORDS = {"database", "model", "table", "column", "measure", "hierarchy", "level", "partition", "relationship",
                   "role", "tablePermission", "expression", "cultureInfo", "linguisticMetadata", "annotation", "ref",
                   "refreshPolicy", "source", "sourceExpression"}
DATA_TYPES = {"int64", "string", "dateTime", "decimal", "double", "boolean"}
PARTITION_MODES = {"import", "directQuery", "dual", "directLake"}


class TmdlError(Exception):
    pass


@dataclass
class Obj:
    kind: str
    name: str
    expression: str | None = None
    props: dict[str, str] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    children: list["Obj"] = field(default_factory=list)
    description: str = ""
    annotations: dict[str, str] = field(default_factory=dict)
    file: str = ""
    line: int = 0


NAME = r"(?:'(?:[^']|'')+'|[A-Za-z0-9_][A-Za-z0-9_\-]*)"
DECL = re.compile(rf"^(?P<kind>[A-Za-z]+)(?:\s+(?P<name>{NAME}))?(?:\s*=\s*(?P<expr>.*))?$")


def unquote(name: str) -> str:
    name = name.strip()
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def split_ref(ref: str) -> tuple[str, str]:
    """'Table A'.'Column B' or Table.Column -> (table, column)."""
    m = re.fullmatch(rf"\s*({NAME})\.({NAME})\s*", ref)
    if not m:
        raise TmdlError(f"invalid column reference {ref!r}")
    return unquote(m.group(1)), unquote(m.group(2))


def parse_tmdl(text: str, file: str = "") -> list[Obj]:
    """Parse one TMDL document into top-level objects; raise TmdlError on malformed input."""
    lines = text.split("\n")
    roots: list[Obj] = []
    stack: list[tuple[int, Obj]] = []  # (indent level, object)
    pending_desc: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip():
            continue
        body = raw.lstrip("\t")
        indent = len(raw) - len(body)
        if body.startswith(" "):
            raise TmdlError(f"{file}:{i}: indentation must use tabs")
        if body.startswith("///"):
            pending_desc.append(body[3:].strip())
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else None
        if parent is None and indent != 0:
            raise TmdlError(f"{file}:{i}: unexpected indentation for {body.split()[0]!r}")
        m_prop = re.match(r"^([A-Za-z][A-Za-z0-9]*):\s*(.*)$", body)
        m_decl = DECL.match(body)
        keyword = body.split()[0] if body.split() else ""
        if m_prop:
            if parent is None:
                raise TmdlError(f"{file}:{i}: property {m_prop.group(1)!r} outside an object")
            if m_prop.group(1) in parent.props:
                raise TmdlError(f"{file}:{i}: property {m_prop.group(1)!r} declared twice")
            parent.props[m_prop.group(1)] = m_prop.group(2).strip()
            continue
        if keyword == "ref":
            if not re.fullmatch(rf"ref\s+[A-Za-z]+\s+{NAME}", body.strip()):
                raise TmdlError(f"{file}:{i}: malformed ref {body!r}")
            continue
        if keyword == "annotation":
            m = re.match(rf"^annotation\s+({NAME})\s*=\s*(.*)$", body)
            if not m or parent is None:
                raise TmdlError(f"{file}:{i}: malformed annotation")
            parent.annotations[unquote(m.group(1))] = m.group(2).strip()
            continue
        if keyword in {"source", "sourceExpression"} and parent is not None and parent.kind in {"partition", "refreshPolicy"}:
            if body.strip() in {"source", "sourceExpression"}:
                obj = Obj(keyword, keyword, file=file, line=i)
                parent.children.append(obj)
                stack.append((indent, obj))
                continue
            m = re.match(r"^(source|sourceExpression)\s*=\s*(.*)$", body)
            if not m:
                raise TmdlError(f"{file}:{i}: malformed {keyword}")
            expr, i = read_expression(lines, i, indent, m.group(2), file)
            parent.props[keyword] = expr
            continue
        if keyword == "refreshPolicy" and body.strip() == "refreshPolicy":
            obj = Obj("refreshPolicy", "refreshPolicy", file=file, line=i)
            if parent is None:
                raise TmdlError(f"{file}:{i}: refreshPolicy outside a table")
            parent.children.append(obj)
            stack.append((indent, obj))
            continue
        if keyword in OBJECT_KEYWORDS and m_decl:
            if keyword == "ref":
                continue
            name = unquote(m_decl.group("name") or "")
            obj = Obj(keyword, name, file=file, line=i, description=" ".join(pending_desc))
            pending_desc = []
            if m_decl.group("expr") is not None:
                obj.expression, i = read_expression(lines, i, indent, m_decl.group("expr"), file)
            (parent.children if parent else roots).append(obj)
            stack.append((indent, obj))
            continue
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", body.strip()) and parent is not None:
            parent.flags.add(body.strip())
            continue
        raise TmdlError(f"{file}:{i}: cannot parse {body!r}")
    if pending_desc:
        raise TmdlError(f"{file}: description block not followed by an object")
    return roots


def read_expression(lines: list[str], i: int, indent: int, first: str, file: str) -> tuple[str, int]:
    """Read a default-property expression: same line, or the deeper-indented lines that follow (two levels deeper)."""
    first = first.strip()
    if first and first != "```":
        return first, i
    body: list[str] = []
    j = i
    while j < len(lines):
        raw = lines[j]
        if raw.strip() and (len(raw) - len(raw.lstrip("\t"))) <= indent + 1:
            break
        body.append(raw)
        j += 1
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise TmdlError(f"{file}:{i}: expression expected after '='")
    if any(l.strip() and (len(l) - len(l.lstrip("\t"))) < indent + 2 for l in body):
        raise TmdlError(f"{file}:{i}: expression must be indented two levels deeper than its object")
    return "\n".join(l[indent + 2:] if l.strip() else "" for l in body), j


# --------------------------------------------------------------------------- model


@dataclass
class Model:
    name: str
    tables: dict[str, Obj]
    relationships: list[Obj]
    roles: dict[str, Obj]
    expressions: dict[str, Obj]
    database: Obj | None
    model: Obj | None
    cultures: dict[str, Obj]

    def columns(self, table: str) -> dict[str, Obj]:
        return {c.name: c for c in self.tables[table].children if c.kind == "column"}

    def measures(self) -> dict[str, tuple[str, Obj]]:
        return {m.name: (t, m) for t, o in self.tables.items() for m in o.children if m.kind == "measure"}


def load_model(definition: Path) -> Model:
    objs: list[Obj] = []
    for path in sorted(definition.rglob("*.tmdl")):
        objs += parse_tmdl(path.read_text(), str(path.relative_to(definition)))
    by = lambda k: [o for o in objs if o.kind == k]  # noqa: E731
    tables = {}
    for t in by("table"):
        if t.name in tables:
            raise TmdlError(f"table {t.name!r} declared twice")
        tables[t.name] = t
    db = by("database")
    md = by("model")
    return Model(definition.parent.name, tables, by("relationship"), {r.name: r for r in by("role")},
                 {e.name: e for e in by("expression")}, db[0] if db else None, md[0] if md else None,
                 {c.name: c for c in by("cultureInfo")})


# --------------------------------------------------------------------------- DAX


def strip_dax(text: str) -> str:
    """Remove comments and string literals (replaced by "") so references can be scanned."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("//", i) or text.startswith("--", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if text[i] == '"':
            j = i + 1
            while j < n:
                if text[j] == '"' and j + 1 < n and text[j + 1] == '"':
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            out.append('""')
            i = j + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def string_literals(text: str) -> set[str]:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = "\n".join(re.sub(r"(//|--).*$", "", l) for l in text.splitlines())
    return {m.replace('""', '"') for m in re.findall(r'"((?:[^"]|"")*)"', text)}


TABLE_COL = re.compile(r"(?:'((?:[^']|'')+)'\s*|\b([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
QUOTED_TABLE = re.compile(r"'((?:[^']|'')+)'(?!\s*\[)")
BARE_REF = re.compile(r"(?<![\]'A-Za-z0-9_])\[([^\]]+)\]")
FUNC = re.compile(r"\b([A-Z][A-Z0-9_.]*)\s*\(")


def balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += ch == "("
        depth -= ch == ")"
        if depth < 0:
            return False
    return depth == 0


def dax_references(model: Model, text: str, local_names: set[str], where: str) -> list[str]:
    problems = []
    code = strip_dax(text)
    if not balanced(code):
        problems.append(f"{where}: unbalanced parentheses")
    measures = model.measures()
    for m in TABLE_COL.finditer(code):
        table = (m.group(1) or m.group(2)).replace("''", "'")
        col = m.group(3)
        if table not in model.tables:
            problems.append(f"{where}: unknown table {table!r}")
        elif col not in model.columns(table) and col not in measures:
            problems.append(f"{where}: unknown column {table}[{col}]")
    no_cols = TABLE_COL.sub(" ", code)
    for m in QUOTED_TABLE.finditer(no_cols):
        if m.group(1).replace("''", "'") not in model.tables:
            problems.append(f"{where}: unknown table {m.group(1)!r}")
    for m in BARE_REF.finditer(no_cols):
        if m.group(1) not in measures and m.group(1) not in local_names:
            problems.append(f"{where}: [{m.group(1)}] is neither a measure nor a name defined in the query")
    for m in FUNC.finditer(no_cols):
        name = m.group(1)
        if name not in DAX_FUNCTIONS and name not in DAX_KEYWORDS:
            problems.append(f"{where}: unknown DAX function {name}")
    return problems


def top_level_args(text: str, start: int) -> tuple[list[str], int]:
    """Arguments of the call whose '(' is at text[start]; returns (args, index after ')')."""
    depth, args, cur, i = 0, [], [], start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            if depth > 1:
                cur.append(ch)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(cur).strip())
                return args, i + 1
            cur.append(ch)
        elif ch == "," and depth == 1:
            args.append("".join(cur).strip())
            cur = []
        else:
            if depth >= 1:
                cur.append(ch)
        i += 1
    raise ValueError("unterminated call")


def output_columns(query: str) -> list[str]:
    """Names of the result columns of the query's EVALUATE (SELECTCOLUMNS, ROW, or UNION of them)."""
    code = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)
    code = "\n".join(re.sub(r"//.*$", "", l) for l in code.splitlines())
    evaluates = [m.start() for m in re.finditer(r"\bEVALUATE\b", code)]
    if len(evaluates) != 1:
        raise ValueError(f"expected one EVALUATE, found {len(evaluates)}")
    expr = code[evaluates[0] + len("EVALUATE"):].strip()

    def names(e: str) -> list[str]:
        m = re.match(r"(SELECTCOLUMNS|ROW|UNION)\s*\(", e)
        if not m:
            raise ValueError(f"EVALUATE must return SELECTCOLUMNS, ROW or UNION, got {e[:40]!r}")
        args, _ = top_level_args(e, m.end() - 1)
        if m.group(1) == "UNION":
            return names(args[0])
        pairs = args[1:] if m.group(1) == "SELECTCOLUMNS" else args
        if len(pairs) % 2:
            raise ValueError("name/expression pairs are incomplete")
        out = []
        for k in range(0, len(pairs), 2):
            lit = re.fullmatch(r'"((?:[^"]|"")*)"', pairs[k])
            if not lit:
                raise ValueError(f"column name must be a string literal, got {pairs[k][:40]!r}")
            out.append(lit.group(1))
        return out

    return names(expr)


def check_query(model: Model, query: str, where: str) -> list[str]:
    problems = dax_references(model, query, string_literals(query) | defined_vars(query), where)
    try:
        output_columns(query)
    except ValueError as exc:
        problems.append(f"{where}: {exc}")
    return problems


def defined_vars(query: str) -> set[str]:
    return set(re.findall(r"\bVAR\s+([A-Za-z_][A-Za-z0-9_]*)", strip_dax(query)))


# --------------------------------------------------------------------------- model checks and BPA rules


def relationship_parts(model: Model, r: Obj) -> tuple[str, str, str, str]:
    ft, fc = split_ref(r.props.get("fromColumn", ""))
    tt, tc = split_ref(r.props.get("toColumn", ""))
    return ft, fc, tt, tc


def filter_paths(model: Model) -> dict[tuple[str, str], int]:
    """Number of distinct directed filter paths between every pair of tables (active relationships)."""
    edges: dict[str, list[str]] = {t: [] for t in model.tables}
    for r in model.relationships:
        if r.props.get("isActive") == "false":
            continue
        ft, _, tt, _ = relationship_parts(model, r)
        edges.setdefault(tt, []).append(ft)  # the 'to' side filters the 'from' side
        if r.props.get("crossFilteringBehavior") == "bothDirections":
            edges.setdefault(ft, []).append(tt)
    counts: dict[tuple[str, str], int] = {}

    def walk(start: str, node: str, seen: tuple[str, ...]) -> None:
        for nxt in edges.get(node, []):
            if nxt in seen:
                continue
            counts[(start, nxt)] = counts.get((start, nxt), 0) + 1
            walk(start, nxt, seen + (nxt,))

    for t in model.tables:
        walk(t, t, (t,))
    return counts


BPA_RULES = {
    "SLC_MEASURE_DESCRIPTION": "Every visible measure has a description.",
    "SLC_MEASURE_FORMAT": "Every measure has a format string.",
    "SLC_DIVIDE": "Measures use DIVIDE instead of the '/' operator.",
    "SLC_NO_IFERROR": "Measures do not use IFERROR or ISERROR.",
    "SLC_FACT_COLUMNS_HIDDEN": "Fact key and numeric columns are hidden; facts are reached through measures.",
    "SLC_SUMMARIZE_NONE": "Every column has summarizeBy none (no implicit measures).",
    "SLC_NO_CALCULATED_COLUMNS": "Every column maps to a source column (no calculated columns; Direct Lake compatible).",
    "SLC_DATE_TABLE": "Date dimensions used by time intelligence are marked as date tables.",
    "SLC_NO_BIDIRECTIONAL": "No bidirectional relationships.",
    "SLC_RELATIONSHIP_TYPES": "Related columns have the same data type.",
    "SLC_DISCOURAGE_IMPLICIT": "The model discourages implicit measures.",
}


def check_model(model: Model) -> list[str]:
    p: list[str] = []
    w = model.name
    if model.database is None or model.model is None:
        return [f"{w}: database.tmdl and model.tmdl are required"]
    level = model.database.props.get("compatibilityLevel", "0")
    if not level.isdigit() or int(level) < 1604:
        p.append(f"{w}: compatibilityLevel must be at least 1604 (Direct Lake), got {level}")
    measures = model.measures()
    seen_measures: set[str] = set()
    for tname, t in model.tables.items():
        cols = model.columns(tname)
        partitions = [c for c in t.children if c.kind == "partition"]
        if len(partitions) != 1:
            p.append(f"{w}: table {tname} must have exactly one partition")
        for part in partitions:
            mode = part.props.get("mode")
            if mode not in PARTITION_MODES:
                p.append(f"{w}: partition {part.name} has invalid mode {mode!r}")
            if mode == "directLake":
                src = next((c for c in part.children if c.kind == "source"), None)
                if part.expression != "entity" or src is None or "entityName" not in src.props or "expressionSource" not in src.props:
                    p.append(f"{w}: Direct Lake partition {part.name} needs an entity source with entityName and expressionSource")
                elif src.props["expressionSource"].strip("'") not in model.expressions:
                    p.append(f"{w}: partition {part.name} references unknown expression {src.props['expressionSource']}")
            elif "source" not in part.props:
                p.append(f"{w}: partition {part.name} has no M source")
        for c in cols.values():
            if c.props.get("dataType") not in DATA_TYPES:
                p.append(f"{w}: column {tname}[{c.name}] has invalid dataType {c.props.get('dataType')!r}")
            if "sourceColumn" not in c.props:
                p.append(f"{w}: SLC_NO_CALCULATED_COLUMNS {tname}[{c.name}]")
            if c.props.get("summarizeBy") != "none":
                p.append(f"{w}: SLC_SUMMARIZE_NONE {tname}[{c.name}]")
            sort_by = c.props.get("sortByColumn")
            if sort_by and unquote(sort_by) not in cols:
                p.append(f"{w}: {tname}[{c.name}] sorts by unknown column {sort_by}")
            if c.name in measures:
                p.append(f"{w}: column {tname}[{c.name}] has the same name as a measure")
        for h in (c for c in t.children if c.kind == "hierarchy"):
            for lvl in (c for c in h.children if c.kind == "level"):
                if unquote(lvl.props.get("column", "")) not in cols:
                    p.append(f"{w}: hierarchy {tname}.{h.name} level {lvl.name} references an unknown column")
        is_fact = bool([m for m in t.children if m.kind == "measure"]) and tname not in {"Date", "Pickup Date"}
        if is_fact:
            for c in cols.values():
                if c.props.get("dataType") in {"int64", "decimal", "double", "dateTime"} and "isHidden" not in c.flags \
                        and c.name not in {"Vendor ID", "Pickup Hour"}:
                    p.append(f"{w}: SLC_FACT_COLUMNS_HIDDEN {tname}[{c.name}]")
        for m in (c for c in t.children if c.kind == "measure"):
            if m.name in seen_measures:
                p.append(f"{w}: measure {m.name} declared twice")
            seen_measures.add(m.name)
            if not m.expression:
                p.append(f"{w}: measure {m.name} has no expression")
                continue
            if "isHidden" not in m.flags and not m.description:
                p.append(f"{w}: SLC_MEASURE_DESCRIPTION {m.name}")
            if "formatString" not in m.props:
                p.append(f"{w}: SLC_MEASURE_FORMAT {m.name}")
            code = strip_dax(m.expression)
            if re.search(r"(?<![/*])/(?![/*])", code):
                p.append(f"{w}: SLC_DIVIDE {m.name}")
            if re.search(r"\b(IFERROR|ISERROR)\s*\(", code):
                p.append(f"{w}: SLC_NO_IFERROR {m.name}")
            p += dax_references(model, m.expression, set(re.findall(r"\bVAR\s+(\w+)", code)), f"{w}: measure {m.name}")
            refs = set(BARE_REF.findall(TABLE_COL.sub(" ", code)))
            if m.name in refs:
                p.append(f"{w}: measure {m.name} references itself")
    if "discourageImplicitMeasures" not in model.model.flags:
        p.append(f"{w}: SLC_DISCOURAGE_IMPLICIT")
    if not any(t.props.get("dataCategory") == "Time" for t in model.tables.values()):
        p.append(f"{w}: SLC_DATE_TABLE no table is marked as a date table")
    for t in model.tables.values():
        if t.props.get("dataCategory") == "Time":
            keys = [c for c in t.children if c.kind == "column" and "isKey" in c.flags]
            if len(keys) != 1 or keys[0].props.get("dataType") != "dateTime":
                p.append(f"{w}: SLC_DATE_TABLE {t.name} needs exactly one dateTime key column")
    pairs: set[tuple[str, str]] = set()
    for r in model.relationships:
        try:
            ft, fc, tt, tc = relationship_parts(model, r)
        except TmdlError as exc:
            p.append(f"{w}: relationship {r.name}: {exc}")
            continue
        for tb, col in ((ft, fc), (tt, tc)):
            if tb not in model.tables or col not in model.columns(tb):
                p.append(f"{w}: relationship {r.name} references unknown column {tb}[{col}]")
        if p and p[-1].startswith(f"{w}: relationship {r.name}"):
            continue
        if r.props.get("crossFilteringBehavior") == "bothDirections":
            p.append(f"{w}: SLC_NO_BIDIRECTIONAL {ft} - {tt}")
        if model.columns(ft)[fc].props.get("dataType") != model.columns(tt)[tc].props.get("dataType"):
            p.append(f"{w}: SLC_RELATIONSHIP_TYPES {ft}[{fc}] - {tt}[{tc}]")
        many_to_many = r.props.get("toCardinality") == "many"
        if not many_to_many and "isKey" not in model.columns(tt)[tc].flags:
            p.append(f"{w}: relationship {r.name}: one side {tt}[{tc}] must be a key column")
        if r.props.get("isActive") != "false":
            if (ft, tt) in pairs:
                p.append(f"{w}: two active relationships between {ft} and {tt}")
            pairs.add((ft, tt))
    for (a, b), n in filter_paths(model).items():
        if n > 1:
            p.append(f"{w}: ambiguous filter paths from {a} to {b} ({n})")
    for role in model.roles.values():
        if role.props.get("modelPermission") != "read":
            p.append(f"{w}: role {role.name} must have modelPermission read")
        perms = [c for c in role.children if c.kind == "tablePermission"]
        if not perms:
            p.append(f"{w}: role {role.name} has no table permission")
        for perm in perms:
            if perm.name not in model.tables:
                p.append(f"{w}: role {role.name} filters unknown table {perm.name}")
            p += dax_references(model, perm.expression or "", set(), f"{w}: role {role.name}")
    for e in model.expressions.values():
        if not e.expression:
            p.append(f"{w}: expression {e.name} is empty")
    for c in model.cultures.values():
        lm = next((x for x in c.children if x.kind == "linguisticMetadata"), None)
        if lm is None or lm.props.get("contentType") != "json":
            p.append(f"{w}: culture {c.name} needs JSON linguistic metadata")
            continue
        try:
            doc = json.loads(lm.expression or "")
        except json.JSONDecodeError as exc:
            p.append(f"{w}: culture {c.name} linguistic metadata is not JSON: {exc}")
            continue
        for key, ent in doc.get("Entities", {}).items():
            b = ent.get("Definition", {}).get("Binding", {})
            if b.get("ConceptualEntity") not in model.tables:
                p.append(f"{w}: linguistic entity {key} binds unknown table {b.get('ConceptualEntity')}")
            prop = b.get("ConceptualProperty")
            if prop and prop not in measures and prop not in model.columns(b.get("ConceptualEntity", "")):
                p.append(f"{w}: linguistic entity {key} binds unknown property {prop}")
            if len(ent.get("Terms", [])) > 10:
                p.append(f"{w}: linguistic entity {key} has more than 10 terms")
    return p


def model_dirs() -> list[Path]:
    return sorted(MODELS.glob("*.SemanticModel"))


def model_for_query(path: Path) -> str:
    """WWI or NYC model for a query file (by question or metric id)."""
    stem = path.stem
    if stem.startswith(("Q-W-", "B-W", "W-")) or stem in {f"Q-A0{i}" for i in range(1, 6)}:
        return "WWI"
    return "NYC"


def main() -> None:
    problems: list[str] = []
    loaded: dict[str, Model] = {}
    for d in model_dirs():
        try:
            m = load_model(d / "definition")
        except TmdlError as exc:
            problems.append(f"{d.name}: {exc}")
            continue
        loaded[d.name] = m
        problems += check_model(m)
    for path in sorted(QUERIES.glob("*/*.dax")):
        dataset = model_for_query(path)
        model = loaded.get(f"SLC_{dataset}_Import.SemanticModel")
        if model is None:
            problems.append(f"{path.name}: model SLC_{dataset}_Import not loaded")
            continue
        problems += check_query(model, path.read_text(), path.name)
    for p in problems:
        print(p)
    print(f"{len(loaded)} models, {len(list(QUERIES.glob('*/*.dax')))} queries, {len(problems)} problems")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
