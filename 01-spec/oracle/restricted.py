#!/usr/bin/env python3
"""Restricted expected answers for the SPEC § 10 security scenario.

Each role is a set of row filters on fact tables, applied the way Unity Catalog row filters apply: on the table, beneath
every query. The engine's canonical fact table is renamed to <table>__unrestricted and replaced by a view that keeps
only the role's rows, so the unchanged oracle SQL (questions/*.sql) answers as that role. Dimension tables are never
filtered: the Manhattan role still browses every dropoff zone, and the territory role still sees every territory name.

Roles and question subset (SPEC § 10: all P and D1 questions of the role's dataset)
  territory_southeast  WWI  fact_sale, fact_order: as-was city in the Southeast sales territory;
                            fact_stock_holding_daily, fact_stock_movement, stock_holding_current: no rows
  pickup_manhattan     NYC  fact_trip: pickup zone in Manhattan

Examples
  python restricted.py --engine duckdb --data-root B0/warehouse --write-expected expected/restricted
  python restricted.py --engine spark  --data-root B0/warehouse --compare expected/restricted
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ORACLE = Path(__file__).resolve().parent
if str(ORACLE) not in sys.path:
    sys.path.insert(0, str(ORACLE))

import run_oracle as ro  # noqa: E402

EXPECTED = ORACLE / "expected" / "restricted"


@dataclass(frozen=True)
class Role:
    name: str
    label: str
    dataset: str  # question prefix: W (WWI) or N (NYC)
    filters: dict[str, str]  # "schema.table" -> boolean predicate over that table's columns


DENY = "1 = 0"
ROLES = {
    "territory_southeast": Role(
        "territory_southeast", "Territory Analyst – Southeast", "W",
        {
            "wwi.fact_sale": "city_key IN (SELECT city_key FROM wwi.dim_city WHERE sales_territory = 'Southeast')",
            "wwi.fact_order": "city_key IN (SELECT city_key FROM wwi.dim_city WHERE sales_territory = 'Southeast')",
            "wwi.fact_stock_holding_daily": DENY,
            "wwi.fact_stock_movement": DENY,
            "wwi.stock_holding_current": DENY,
        },
    ),
    "pickup_manhattan": Role(
        "pickup_manhattan", "Manhattan Pickup Analyst", "N",
        {"nyctaxi.fact_trip": "pu_location_id IN (SELECT location_id FROM nyctaxi.dim_zone WHERE borough = 'Manhattan')"},
    ),
}


def role_queries(role: Role) -> list[ro.Query]:
    """The role's restricted subset: P and D1 questions of its dataset (SPEC § 10)."""
    return [q for q in ro.load_queries() if q.kind == "questions"
            and q.query_id.startswith(f"Q-{role.dataset}-") and q.query_id.endswith(("-P", "-D1"))]


def ddl(engine: ro.Engine, sql: str) -> None:
    if isinstance(engine, ro.DuckDBEngine):
        engine.con.execute(sql)
    else:
        engine.spark.sql(sql)


def apply_role(engine: ro.Engine, role: Role) -> None:
    """Replace each filtered fact table by a view over its renamed original that keeps only the role's rows."""
    for table, predicate in role.filters.items():
        schema, name = table.split(".")
        original = f"{schema}.{name}__unrestricted"
        renamed = False
        for kind in ("VIEW", "TABLE"):
            try:
                target = f"{name}__unrestricted" if isinstance(engine, ro.DuckDBEngine) else original
                ddl(engine, f"ALTER {kind} {table} RENAME TO {target}")
                renamed = True
                break
            except Exception:  # the object is the other kind on this engine
                continue
        if not renamed:
            raise RuntimeError(f"cannot rename {table} on {engine.name}")
        ddl(engine, f"CREATE VIEW {table} AS SELECT * FROM {original} WHERE {predicate}")


def remove_role(engine: ro.Engine, role: Role) -> None:
    """Undo apply_role: drop each filtered view and restore the original table under its canonical name."""
    for table in role.filters:
        schema, name = table.split(".")
        ddl(engine, f"DROP VIEW {table}")
        target = name if isinstance(engine, ro.DuckDBEngine) else table
        for kind in ("VIEW", "TABLE"):
            try:
                ddl(engine, f"ALTER {kind} {schema}.{name}__unrestricted RENAME TO {target}")
                break
            except Exception:  # the object is the other kind on this engine
                continue
        else:
            raise RuntimeError(f"cannot restore {table} on {engine.name}")


def make_engine(args, role: Role) -> ro.Engine:
    if args.engine == "duckdb":
        engine = ro.DuckDBEngine(data_root=args.data_root, threads=args.threads)
    elif args.engine == "duckdb-fixtures":
        engine = ro.DuckDBEngine(fixtures=args.fixtures)
    elif args.engine == "spark":
        engine = ro.SparkEngine(data_root=args.data_root)
    elif args.engine == "spark-fixtures":
        engine = ro.SparkEngine(fixtures=args.fixtures)
    else:
        raise SystemExit(f"unknown engine {args.engine}")
    apply_role(engine, role)
    return engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=["duckdb", "spark", "duckdb-fixtures", "spark-fixtures"])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--fixtures", type=Path, default=ORACLE / "fixtures")
    parser.add_argument("--role", default="all", choices=["all", *ROLES])
    parser.add_argument("--threads", type=int)
    parser.add_argument("--write-expected", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--perf", type=Path)
    args = parser.parse_args()

    roles = list(ROLES.values()) if args.role == "all" else [ROLES[args.role]]
    started, summary, records = time.time(), [], []
    failed = False
    for role in roles:
        engine = make_engine(args, role)
        queries = role_queries(role)
        write = args.write_expected / role.name if args.write_expected else None
        compare = args.compare / role.name if args.compare else None
        results = ro.run(engine, queries, 1, write, compare)
        engine.close()
        errors = [r for r in results if r.error]
        diffs = [r for r in results if r.problems]
        failed |= bool(errors or diffs)
        summary.append({"role": role.name, "queries": len(results), "errors": len(errors), "mismatched": len(diffs)})
        records += [{"role": role.name, **r.as_dict()} for r in results]
        if args.engine.startswith("spark"):
            from pyspark.sql import SparkSession
            SparkSession.builder.getOrCreate().stop()
    out = {"engine": args.engine, "roles": summary, "wall_seconds": round(time.time() - started, 1)}
    if args.perf:
        args.perf.parent.mkdir(parents=True, exist_ok=True)
        args.perf.write_text(json.dumps({"summary": out, "results": records}, indent=1))
    print(json.dumps(out))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
