#!/usr/bin/env python3
"""Static validation of the S1 model and its MDX against the generated ASSL (no SSAS instance required).

Checks:
- model/*.dim, model/*.cube and deploy/slc.xmla are well-formed XML in the ASSL namespace; every attribute
  relationship, hierarchy level, cube dimension, measure group dimension, many-to-many intermediate measure group,
  partition data source, DSV table and column binding resolves;
- every MDX text (calculation scripts, metric and question queries) has balanced brackets, braces, parentheses and
  string literals; every [Dimension].[Hierarchy] and [Dimension].[Hierarchy].[Level] reference resolves in its cube;
  every [Measures].[Name] is a stored measure, a calculated measure of the script, or a query-scoped WITH member;
  every .Properties("X") on [Dim].[Attribute].CurrentMember names an attribute related to that attribute;
- query files: SELECT ... FROM [cube] with an explicit COLUMNS measure set; @column sources are measures on the
  COLUMNS axis or hierarchies on the ROWS axis; metric @branch rows and values resolve.

    python3 lint_mdx.py        # exit 1 on any problem
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = {"a": "http://schemas.microsoft.com/analysisservices/2003/engine"}
XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"

# Members referenced by name in the question bank (SPEC § 7 names these zones explicitly).
NAMED_MEMBERS = {
    ("[Pickup Zone].[Zone]", "JFK Airport"),
    ("[Pickup Zone].[Zone]", "LaGuardia Airport"),
}
MDX_FUNCTIONS_ON_BRACKETS = {"Measures"}


@dataclass
class CubeCatalog:
    name: str
    hierarchies: dict[str, set[str]] = field(default_factory=dict)  # "[Dim].[Hier]" -> level names
    attributes: dict[str, set[str]] = field(default_factory=dict)  # "[Dim].[Attr]" -> related attribute names
    stored_measures: set[str] = field(default_factory=set)
    calculated_measures: set[str] = field(default_factory=set)

    @property
    def measures(self) -> set[str]:
        return self.stored_measures | self.calculated_measures


def _t(el: ET.Element, tag: str) -> str:
    found = el.find(f"a:{tag}", NS)
    return found.text if found is not None and found.text is not None else ""


def parse_xml(path: Path) -> tuple[ET.Element | None, list[str]]:
    try:
        return ET.parse(path).getroot(), []
    except ET.ParseError as exc:
        return None, [f"{path.name}: malformed XML ({exc})"]


def dsv_columns(dsv_root: ET.Element) -> dict[str, set[str]]:
    xs = "{http://www.w3.org/2001/XMLSchema}"
    tables: dict[str, set[str]] = {}
    for el in dsv_root.iter(f"{xs}element"):
        seq = el.find(f"{xs}complexType/{xs}sequence")
        if seq is not None:
            tables[el.get("name")] = {c.get("name") for c in seq.findall(f"{xs}element")}
    return tables


def check_bindings(root: ET.Element, columns: dict[str, set[str]], owner: str) -> list[str]:
    problems = []
    for src in root.iter(f"{{{NS['a']}}}Source"):
        kind = src.get(XSI_TYPE)
        if kind == "ColumnBinding":
            table, column = _t(src, "TableID"), _t(src, "ColumnID")
            if table not in columns:
                problems.append(f"{owner}: binding to unknown DSV table {table!r}")
            elif column not in columns[table]:
                problems.append(f"{owner}: binding to unknown column {table}.{column}")
        elif kind == "RowBinding" and _t(src, "TableID") not in columns:
            problems.append(f"{owner}: row binding to unknown DSV table {_t(src, 'TableID')!r}")
    return problems


def lint_dimension(root: ET.Element, columns: dict[str, set[str]]) -> list[str]:
    name = _t(root, "Name")
    problems = check_bindings(root, columns, f"dimension {name}")
    attrs = {_t(a, "ID") for a in root.findall("a:Attributes/a:Attribute", NS)}
    keys = [a for a in root.findall("a:Attributes/a:Attribute", NS) if _t(a, "Usage") == "Key"]
    if len(keys) != 1:
        problems.append(f"dimension {name}: exactly one key attribute required, found {len(keys)}")
    for a in root.findall("a:Attributes/a:Attribute", NS):
        if not a.findall("a:KeyColumns/a:KeyColumn", NS):
            problems.append(f"dimension {name}: attribute {_t(a, 'ID')} has no key column")
        for r in a.findall("a:AttributeRelationships/a:AttributeRelationship", NS):
            if _t(r, "AttributeID") not in attrs:
                problems.append(f"dimension {name}: relationship to unknown attribute {_t(r, 'AttributeID')!r}")
    # Every attribute must be reachable from the key through relationships.
    graph = {_t(a, "ID"): [_t(r, "AttributeID") for r in a.findall("a:AttributeRelationships/a:AttributeRelationship", NS)]
             for a in root.findall("a:Attributes/a:Attribute", NS)}
    if keys:
        seen, stack = set(), [_t(keys[0], "ID")]
        while stack:
            n = stack.pop()
            if n not in seen:
                seen.add(n)
                stack.extend(graph.get(n, []))
        for missing in sorted(attrs - seen):
            problems.append(f"dimension {name}: attribute {missing} is not reachable from the key attribute")
    for h in root.findall("a:Hierarchies/a:Hierarchy", NS):
        levels = [_t(lv, "SourceAttributeID") for lv in h.findall("a:Levels/a:Level", NS)]
        for lv in levels:
            if lv not in attrs:
                problems.append(f"dimension {name}: hierarchy {_t(h, 'Name')} level on unknown attribute {lv!r}")
        # Natural hierarchy: each level reaches the level above through relationships.
        for lower, upper in zip(levels[1:], levels[:-1]):
            seen, stack = set(), [lower]
            while stack:
                n = stack.pop()
                if n not in seen:
                    seen.add(n)
                    stack.extend(graph.get(n, []))
            if upper not in seen:
                problems.append(f"dimension {name}: hierarchy {_t(h, 'Name')} is not natural between {upper} and {lower}")
    return problems


def load_catalog(model_dir: Path, mdx_dir: Path) -> tuple[dict[str, CubeCatalog], list[str]]:
    problems: list[str] = []
    dsv_root, errs = parse_xml(model_dir / "slc.dsv")
    problems += errs
    columns = dsv_columns(dsv_root) if dsv_root is not None else {}
    dims: dict[str, ET.Element] = {}
    for path in sorted(model_dir.glob("*.dim")):
        root, errs = parse_xml(path)
        problems += errs
        if root is not None:
            dims[_t(root, "ID")] = root
            problems += lint_dimension(root, columns)
    catalogs: dict[str, CubeCatalog] = {}
    for path in sorted(model_dir.glob("*.cube")):
        root, errs = parse_xml(path)
        problems += errs
        if root is None:
            continue
        cube = _t(root, "Name")
        cat = CubeCatalog(cube)
        problems += check_bindings(root, columns, f"cube {cube}")
        cube_dims = {}
        for cd in root.findall("a:Dimensions/a:Dimension", NS):
            cube_dims[_t(cd, "ID")] = _t(cd, "DimensionID")
            dim = dims.get(_t(cd, "DimensionID"))
            if dim is None:
                problems.append(f"cube {cube}: dimension {_t(cd, 'ID')} references unknown database dimension")
                continue
            for a in dim.findall("a:Attributes/a:Attribute", NS):
                key = f"[{_t(cd, 'Name')}].[{_t(a, 'Name')}]"
                related = {_t(r, "AttributeID") for r in a.findall("a:AttributeRelationships/a:AttributeRelationship", NS)}
                cat.attributes[key] = related
                if _t(a, "AttributeHierarchyEnabled") != "false":
                    cat.hierarchies[key] = {_t(a, "Name")}
            for h in dim.findall("a:Hierarchies/a:Hierarchy", NS):
                cat.hierarchies[f"[{_t(cd, 'Name')}].[{_t(h, 'Name')}]"] = {_t(lv, "Name") for lv in h.findall("a:Levels/a:Level", NS)}
        mg_ids = {_t(mg, "ID") for mg in root.findall("a:MeasureGroups/a:MeasureGroup", NS)}
        for mg in root.findall("a:MeasureGroups/a:MeasureGroup", NS):
            for m in mg.findall("a:Measures/a:Measure", NS):
                cat.stored_measures.add(_t(m, "Name"))
                if _t(m, "AggregateFunction") == "DistinctCount" and len(mg.findall("a:Measures/a:Measure", NS)) > 1:
                    problems.append(f"cube {cube}: distinct count measure {_t(m, 'Name')} must have its own measure group")
            for d in mg.findall("a:Dimensions/a:Dimension", NS):
                cdim = _t(d, "CubeDimensionID")
                if cdim not in cube_dims:
                    problems.append(f"cube {cube}: measure group {_t(mg, 'ID')} uses unknown cube dimension {cdim!r}")
                if d.get(XSI_TYPE) == "ManyToManyMeasureGroupDimension" and _t(d, "MeasureGroupID") not in mg_ids:
                    problems.append(f"cube {cube}: many-to-many via unknown measure group {_t(d, 'MeasureGroupID')!r}")
                if d.get(XSI_TYPE) == "RegularMeasureGroupDimension":
                    dim = dims.get(cube_dims.get(cdim, ""))
                    attr = _t(d.find("a:Attributes/a:Attribute", NS), "AttributeID")
                    if dim is not None and attr not in {_t(a, "ID") for a in dim.findall("a:Attributes/a:Attribute", NS)}:
                        problems.append(f"cube {cube}: measure group {_t(mg, 'ID')} granularity on unknown attribute {attr!r}")
            for p in mg.findall("a:Partitions/a:Partition", NS):
                if _t(p.find("a:Source", NS), "DataSourceID") != "slc_adapter":
                    problems.append(f"cube {cube}: partition {_t(p, 'ID')} has an unknown data source")
                if _t(p, "StorageMode") not in {"Molap", "Rolap", "Holap"}:
                    problems.append(f"cube {cube}: partition {_t(p, 'ID')} has an invalid storage mode")
        script = (mdx_dir / f"{cube}.mdx").read_text() if (mdx_dir / f"{cube}.mdx").exists() else ""
        cat.calculated_measures = set(re.findall(r"CREATE\s+MEMBER\s+CURRENTCUBE\.\[Measures\]\.\[([^\]]+)\]", script, re.I))
        for perm in root.findall("a:CubePermissions/a:CubePermission", NS):
            for dp in perm.findall("a:DimensionPermissions/a:CubeDimensionPermission", NS):
                if _t(dp, "CubeDimensionID") not in cube_dims:
                    problems.append(f"cube {cube}: permission on unknown cube dimension {_t(dp, 'CubeDimensionID')!r}")
        catalogs[cube] = cat
        problems += [f"{cube}.mdx: {p}" for p in lint_mdx_text(script, cat, query=False)]
    return catalogs, problems


# --------------------------------------------------------------------------- MDX text checks

STRING = re.compile(r'"(?:[^"]|"")*"')
COMMENT = re.compile(r"//[^\n]*|--[^\n]*|/\*.*?\*/", re.S)


def strip_comments_and_strings(text: str) -> str:
    text = COMMENT.sub(" ", text)
    return STRING.sub('""', text)


def balance(text: str) -> list[str]:
    problems = []
    if len(STRING.findall(COMMENT.sub(" ", text))) and COMMENT.sub(" ", text).count('"') % 2:
        problems.append("unbalanced string literal")
    code = strip_comments_and_strings(text)
    stack = []
    pairs = {")": "(", "}": "{"}
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "[":
            end = code.find("]", i)
            if end == -1:
                problems.append("unterminated [identifier]")
                break
            i = end + 1
            continue
        if ch == "]":
            problems.append("unbalanced ]")
        if ch in "({":
            stack.append(ch)
        elif ch in ")}":
            if not stack or stack.pop() != pairs[ch]:
                problems.append(f"unbalanced {ch}")
                break
        i += 1
    if stack:
        problems.append(f"unclosed {''.join(stack)}")
    return problems


def references(code: str) -> list[list[str]]:
    """Every chain of bracketed identifiers joined by dots (".&[key]" ends a chain)."""
    out = []
    for m in re.finditer(r"(?:\[[^\]]+\])(?:\.\[[^\]]+\])*", code):
        start = m.start()
        if start > 0 and code[start - 1] in ".&":
            continue
        out.append(re.findall(r"\[([^\]]+)\]", m.group(0)))
    return out


def lint_mdx_text(text: str, cat: CubeCatalog, query: bool = True) -> list[str]:
    problems = balance(text)
    code = strip_comments_and_strings(text)
    with_members = set(re.findall(r"\bMEMBER\s+\[Measures\]\.\[([^\]]+)\]", code, re.I))
    with_dim_members = {tuple(m) for m in re.findall(r"\bMEMBER\s+(\[[^\]]+\]\.\[[^\]]+\])\.\[([^\]]+)\]", code, re.I)}
    with_sets = set(re.findall(r"\bSET\s+\[([^\]]+)\]", code, re.I))
    measures = cat.measures | with_members
    for chain in references(code):
        if chain[0] == "Measures":
            if len(chain) < 2:
                problems.append("[Measures] without a member")
            elif chain[1] not in measures:
                problems.append(f"undefined measure [Measures].[{chain[1]}]")
            continue
        if len(chain) == 1:
            if chain[0] not in with_sets and chain[0] != cat.name:
                problems.append(f"undefined set or cube [{chain[0]}]")
            continue
        hier = f"[{chain[0]}].[{chain[1]}]"
        if hier not in cat.hierarchies and hier not in cat.attributes:
            problems.append(f"unknown hierarchy {hier} in cube [{cat.name}]")
            continue
        if len(chain) >= 3:
            third = chain[2]
            ok = (third in cat.hierarchies.get(hier, set()) or third == "All" or (hier, third) in with_dim_members
                  or (hier, third) in NAMED_MEMBERS)
            if not ok:
                problems.append(f"unknown level or member {hier}.[{third}]")
    # Key references: &[k] must follow a hierarchy that exists (caught above) and be non-empty.
    for m in re.finditer(r"\.&\[([^\]]*)\]", code):
        if not m.group(1).strip():
            problems.append("empty key reference &[]")
    for m in re.finditer(r"(\[[^\]]+\]\.\[[^\]]+\])\.CurrentMember\.Properties\(\"([^\"]+)\"\)",
                         COMMENT.sub(" ", text)):
        hier, prop = m.group(1), m.group(2)
        if hier in cat.attributes and prop not in cat.attributes[hier]:
            problems.append(f"{hier} has no member property {prop!r}")
    for m in re.finditer(r"\.Properties\(\"([^\"]+)\"\)", COMMENT.sub(" ", text)):
        if not any(m.group(1) in rel for rel in cat.attributes.values()):
            problems.append(f"member property {m.group(1)!r} is not an attribute relationship in [{cat.name}]")
    if query:
        if not re.search(r"\bSELECT\b.*\bON\s+COLUMNS\b.*\bFROM\s+\[" + re.escape(cat.name) + r"\]", code, re.S | re.I):
            problems.append(f"query must be SELECT ... ON COLUMNS ... FROM [{cat.name}]")
    return problems


def axis(code: str, name: str) -> str:
    """Text of the COLUMNS or ROWS axis expression of the final SELECT."""
    select = code[code.upper().rfind("SELECT"):]
    if name == "COLUMNS":
        m = re.search(r"SELECT\s+(.*?)\s+ON\s+COLUMNS", select, re.S | re.I)
    else:
        m = re.search(r"ON\s+COLUMNS\s*,\s*(.*?)\s+ON\s+ROWS", select, re.S | re.I)
    return m.group(1) if m else ""


def column_measures(code: str) -> list[str]:
    cols = axis(code, "COLUMNS")
    return re.findall(r"\[Measures\]\.\[([^\]]+)\]", cols)


def query_cube(text: str, catalogs: dict[str, CubeCatalog]) -> CubeCatalog | None:
    m = re.search(r"\bFROM\s+\[([^\]]+)\]", strip_comments_and_strings(text), re.I)
    return catalogs.get(m.group(1)) if m else None


def parse_columns(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2).strip()) for m in re.finditer(r"^//\s*@column\s+(\w+)\s*=\s*(.+)$", text, re.M)]


def lint_question(text: str, catalogs: dict[str, CubeCatalog], header: list[str] | None, qid: str = "query") -> list[str]:
    cat = query_cube(text, catalogs)
    if cat is None:
        return [f"{qid}: FROM must name a cube of the model ({sorted(catalogs)})"]
    problems = [f"{qid}: {p}" for p in lint_mdx_text(text, cat)]
    code = strip_comments_and_strings(text)
    columns = parse_columns(text)
    if header is not None and [c for c, _ in columns] != header:
        problems.append(f"{qid}: @column names {[c for c, _ in columns]} != oracle header {header}")
    on_columns = column_measures(code)
    if not on_columns:
        problems.append(f"{qid}: COLUMNS axis must list measures explicitly")
    rows = axis(code, "ROWS")
    for name, src in columns:
        if src.startswith("[Measures]."):
            if src[len("[Measures]."):].strip("[]") not in on_columns:
                problems.append(f"{qid}: column {name} source {src} is not on the COLUMNS axis")
        else:
            if src not in cat.hierarchies:
                problems.append(f"{qid}: column {name} source {src} is not a hierarchy of [{cat.name}]")
            if src not in rows and not any(src in s for s in _set_bodies(code, rows)):
                problems.append(f"{qid}: column {name} source {src} is not on the ROWS axis")
    return problems


def _set_bodies(code: str, rows: str) -> list[str]:
    """Bodies of the WITH sets the ROWS axis refers to (rows may be a named set)."""
    bodies = []
    for name in re.findall(r"\[(q_[^\]]+)\]", rows):
        m = re.search(r"\bSET\s+\[" + re.escape(name) + r"\]\s+AS\s+(.*?)(?=\bSET\s+\[|\bMEMBER\s+\[|\bSELECT\b)", code, re.S | re.I)
        if m:
            bodies.append(m.group(1))
            bodies.extend(_set_bodies(code, m.group(1)))
    return bodies


BRANCH = re.compile(r"^//\s*@branch\s+grain=(\S+)\s+rows=(.*?)\s+values=(.+?)\s*$", re.M)


def split_branches(text: str) -> list[tuple[str, list[str], list[tuple[str, str]], str]]:
    """(grain, row hierarchies, [(measure label, measure)], statement) of each branch of a metric query file."""
    out = []
    matches = list(BRANCH.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        stmt = text[m.end():end].strip()
        rows = [r for r in m.group(2).split(";") if r]
        values = []
        for v in re.split(r",(?=[A-Z]-[A-Z0-9])", m.group(3)):
            label, sep, rest = v.partition(":[Measures]")
            values.append((label, "[Measures]" + rest if sep else ""))
        out.append((m.group(1), rows, values, stmt))
    return out


def lint_metric(text: str, catalogs: dict[str, CubeCatalog], expected: dict[str, set[str]] | None,
                qid: str = "metric") -> list[str]:
    problems = []
    branches = split_branches(text)
    if not branches:
        return [f"{qid}: no @branch statements"]
    seen = {}
    for grain, rows, values, stmt in branches:
        cat = query_cube(stmt, catalogs)
        if cat is None:
            problems.append(f"{qid}/{grain}: FROM must name a cube of the model")
            continue
        problems += [f"{qid}/{grain}: {p}" for p in lint_mdx_text(stmt, cat)]
        code = strip_comments_and_strings(stmt)
        on_columns = column_measures(code)
        for label, measure in values:
            if measure[len("[Measures]."):].strip("[]") not in on_columns:
                problems.append(f"{qid}/{grain}: value {label} {measure} is not on the COLUMNS axis")
        row_text = axis(code, "ROWS")
        for r in rows:
            if r not in cat.hierarchies:
                problems.append(f"{qid}/{grain}: row hierarchy {r} is not in [{cat.name}]")
            elif r not in row_text:
                problems.append(f"{qid}/{grain}: row hierarchy {r} is not on the ROWS axis")
        if len(rows) > 3:
            problems.append(f"{qid}/{grain}: at most 3 member columns")
        seen[grain] = {label for label, _ in values}
    if expected is not None:
        if set(seen) != set(expected):
            problems.append(f"{qid}: grains {sorted(seen)} != oracle grains {sorted(expected)}")
        for grain in set(seen) & set(expected):
            if seen[grain] != expected[grain]:
                problems.append(f"{qid}/{grain}: measure labels {sorted(seen[grain])} != oracle {sorted(expected[grain])}")
    return problems


def main() -> None:
    import csv

    oracle = HERE.parents[1] / "01-spec" / "oracle" / "expected"
    catalogs, problems = load_catalog(HERE / "model", HERE / "mdx")
    for path in sorted((HERE / "queries" / "questions").glob("*.mdx")):
        with (oracle / "questions" / f"{path.stem}.csv").open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        problems += lint_question(path.read_text(), catalogs, header, path.stem)
    for path in sorted((HERE / "queries" / "metrics").glob("*.mdx")):
        expected: dict[str, set[str]] = {}
        with (oracle / "metrics" / f"{path.stem}.csv").open(newline="", encoding="utf-8") as fh:
            for row in list(csv.reader(fh))[1:]:
                expected.setdefault(row[0], set()).add(row[1])
        problems += lint_metric(path.read_text(), catalogs, expected, path.stem)
    for p in problems:
        print(p)
    n = len(list((HERE / "queries").glob("*/*.mdx")))
    print(f"{len(catalogs)} cubes, {n} query files, {len(problems)} problems")
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
