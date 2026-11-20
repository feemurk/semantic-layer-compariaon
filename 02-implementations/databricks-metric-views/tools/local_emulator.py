"""Local emulation of the study's metric views on Apache Spark, for definition checks without a workspace.

Apache Spark 4.3.0 implements metric views only at YAML 0.1 (no window measures, joins or composed measures), so the
1.1 definitions cannot run locally as metric views. This emulator rewrites them instead:

- each view becomes a temporary view: the source, LEFT OUTER JOINed to every join (nested joins flattened to
  parent__child), projecting every field by name, every source column a field does not shadow, and one struct per
  table alias (source, each join), so measure expressions resolve exactly as written;
- in a query, slc.semantic.<view> becomes that temporary view and MEASURE(m) becomes m's expression, with nested
  MEASURE() calls expanded recursively.

Non-window measures are emulated exactly: a metric view evaluates them as the aggregate over the joined rows that pass
the query filters, and many-to-one joins cannot fan out. Window measures are not emulated: execute() raises
WindowMeasureError, while analyze() substitutes each window measure's base aggregate so names and types still resolve.
The emulator therefore proves that definitions and queries resolve against the canonical schema and that every
non-window result equals the oracle; it is no evidence of Databricks behavior (SPEC § 9.2 reconciliation runs there).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
ORACLE = REPO / "01-spec" / "oracle"
if str(ORACLE) not in sys.path:
    sys.path.insert(0, str(ORACLE))

import run_oracle  # noqa: E402

MEASURE_CALL = re.compile(r"\bMEASURE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.I)
VIEW_REF = re.compile(r"\bslc\.semantic\.([A-Za-z_][A-Za-z0-9_]*)\b")


class WindowMeasureError(Exception):
    """The query uses a window measure, which the emulator does not evaluate."""


def _flatten_joins(joins, parent: str | None = None) -> list[tuple[str, str, str, str, str | None]]:
    """(flat alias, child name, source, on, parent flat alias) for every join, parents before children."""
    out = []
    for j in joins or []:
        flat = f"{parent}__{j['name']}" if parent else j["name"]
        out.append((flat, j["name"], j["source"], j["on"], parent))
        out.extend(_flatten_joins(j.get("joins"), flat))
    return out


def _local(sql: str) -> str:
    """Unity Catalog three-part names to the local two-part tables (slc.wwi.x -> wwi.x)."""
    return re.sub(r"\bslc\.(wwi|nyctaxi)\.", r"\1.", sql)


class Emulator:
    def __init__(self, engine: run_oracle.SparkEngine, views: dict[str, dict] | None = None):
        self.engine = engine
        self.spark = engine.spark
        self.views = views if views is not None else {
            p.stem: yaml.safe_load(p.read_text()) for p in sorted((HERE / "metric_views").glob("*.yaml"))
        }
        self.measures = {v: {m["name"]: m for m in d.get("measures", [])} for v, d in self.views.items()}
        for view in self.views:
            self.spark.sql(f"CREATE OR REPLACE TEMPORARY VIEW __mv_{view} AS {self.relation_sql(view)}")

    def relation_sql(self, view: str) -> str:
        doc = self.views[view]
        joins = _flatten_joins(doc.get("joins"))

        def rewrite(expr: str) -> str:
            # parent.child.column (nested join path) -> parent__child.column, deepest paths first.
            for flat, _child, _src, _on, parent in sorted(joins, key=lambda j: -j[0].count("__")):
                if parent:
                    expr = re.sub(rf"\b{flat.replace('__', r'\.')}\.", f"{flat}.", expr)
            return _local(expr)

        source = doc["source"].strip()
        from_sql = f"({_local(source)}) AS source" if re.search(r"\s", source) else f"{_local(source)} AS source"
        for flat, child, src, on, parent in joins:
            on_sql = rewrite(on)
            if parent:  # inside a nested join's on clause the child is named without its path
                on_sql = re.sub(rf"(?<![\w.]){child}\.", f"{flat}.", on_sql)
            from_sql += f"\nLEFT OUTER JOIN {_local(src)} AS {flat} ON {on_sql}"
        source_cols = self.spark.sql(f"SELECT source.* FROM {from_sql} LIMIT 0").columns
        field_names = [f["name"] for f in doc.get("fields", [])]
        select = [f"{rewrite(f['expr'])} AS {f['name']}" for f in doc.get("fields", [])]
        select += [f"source.`{c}` AS `{c}`" for c in source_cols if c not in field_names]
        select += ["struct(source.*) AS source"] + [f"struct({flat}.*) AS {flat}" for flat, *_ in joins]
        return "SELECT " + ",\n  ".join(select) + f"\nFROM {from_sql}"

    def expand(self, view_names: list[str], name: str, allow_window: bool, depth: int = 0) -> str:
        if depth > 20:
            raise ValueError(f"MEASURE({name}) nests too deeply")
        for view in view_names:
            m = self.measures[view].get(name)
            if m is None:
                continue
            if m.get("window") and not allow_window:
                raise WindowMeasureError(f"{view}.{name} is a window measure")
            expr = MEASURE_CALL.sub(lambda c: self.expand([view], c.group(1), allow_window, depth + 1), m["expr"])
            joins = _flatten_joins(self.views[view].get("joins"))
            for flat, _child, _src, _on, parent in sorted(joins, key=lambda j: -j[0].count("__")):
                if parent:
                    expr = re.sub(rf"\b{flat.replace('__', r'\.')}\.", f"{flat}.", expr)
            return f"({expr})"
        raise KeyError(f"MEASURE({name}) is not defined in {view_names}")

    def rewrite_query(self, sql: str, allow_window: bool = False) -> str:
        used = VIEW_REF.findall(sql)
        unknown = [v for v in used if v not in self.views]
        if unknown:
            raise KeyError(f"unknown metric views {unknown}")
        out = MEASURE_CALL.sub(lambda c: self.expand(used, c.group(1), allow_window), sql)
        return VIEW_REF.sub(lambda m: f"__mv_{m.group(1)}", out)

    def uses_window(self, sql: str) -> bool:
        try:
            self.rewrite_query(sql)
            return False
        except WindowMeasureError:
            return True

    def analyze(self, sql: str) -> list[tuple[str, str]]:
        """Resolve the query (window measures replaced by their base aggregates); return (column, type) pairs."""
        df = self.spark.sql(self.rewrite_query(sql, allow_window=True))
        return [(f.name, f.dataType.simpleString()) for f in df.schema.fields]

    def execute(self, sql: str) -> tuple[list[str], list[tuple]]:
        """Run a query that uses no window measure; raises WindowMeasureError otherwise."""
        return self.engine.execute(self.rewrite_query(sql))
