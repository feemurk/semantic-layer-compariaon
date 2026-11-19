#!/usr/bin/env python3
"""Correctness oracle runner (SPEC § 9).

Executes the oracle SQL (metrics/*.sql, questions/*.sql) against the canonical gold tables
on one engine, then optionally writes expected-answer CSVs, compares results to stored
answers within SPEC § 9.3 tolerances, and records per-query timings.

Engines
  duckdb      local Parquet tables: <data-root>/<schema>.db/<table>/*.parquet
  spark       local Spark SQL over the same Parquet tables (Spark SQL is the Databricks SQL dialect base)
  databricks  an existing Spark session on Databricks; tables resolved in --catalog
  *-fixtures  duckdb-fixtures / spark-fixtures: the CSV fixtures under fixtures/

Examples
  python run_oracle.py --engine duckdb --data-root B0/warehouse --write-expected expected --perf perf/duckdb.json
  python run_oracle.py --engine spark  --data-root B0/warehouse --compare expected --perf perf/spark.json
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ORACLE = Path(__file__).resolve().parent
QUERY_DIRS = ("metrics", "questions")

TABLES = {
    "wwi": [
        "dim_date", "dim_stock_item", "dim_stock_group", "bridge_stock_item_group", "dim_customer",
        "dim_city", "dim_employee", "fact_sale", "fact_order", "fact_stock_movement",
        "stock_holding_current", "fact_stock_holding_daily",
    ],
    "nyctaxi": ["dim_date", "dim_zone", "dim_payment_type", "fact_trip"],
}

MONEY_TOLERANCE = Decimal("0.005")
RATIO_TOLERANCE = 1e-6


# ------------------------------------------------------------------ queries

@dataclass
class Query:
    query_id: str
    kind: str
    path: Path
    sql: str


def load_queries(select: str = "*") -> list[Query]:
    out = []
    for kind in QUERY_DIRS:
        for path in sorted((ORACLE / kind).glob("*.sql")):
            qid = path.stem
            if fnmatch.fnmatch(qid, select):
                text = path.read_text(encoding="utf-8")
                body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
                out.append(Query(qid, kind, path, body.strip().rstrip(";")))
    return out


# ------------------------------------------------------------------ engines

class Engine:
    name = "abstract"

    def execute(self, sql: str) -> tuple[list[str], list[tuple]]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class DuckDBEngine(Engine):
    name = "duckdb"

    def __init__(self, data_root: Path | None = None, fixtures: Path | None = None, threads: int | None = None):
        import duckdb

        self.con = duckdb.connect()
        if threads:
            self.con.execute(f"SET threads = {int(threads)}")
        for schema, tables in TABLES.items():
            self.con.execute(f"CREATE SCHEMA {schema}")
            for table in tables:
                if fixtures:
                    self.con.execute(
                        f"CREATE TABLE {schema}.{table} AS SELECT * FROM {fixture_select(fixtures, schema, table, 'duckdb')}"
                    )
                else:
                    self.con.execute(
                        f"CREATE VIEW {schema}.{table} AS SELECT * FROM read_parquet('{data_root}/{schema}.db/{table}/*.parquet')"
                    )

    def execute(self, sql):
        cur = self.con.execute(sql)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

    def close(self):
        self.con.close()


class SparkEngine(Engine):
    name = "spark"

    def __init__(self, data_root: Path | None = None, fixtures: Path | None = None, catalog: str | None = None,
                 spark=None):
        from pyspark.sql import SparkSession

        if spark is not None:
            self.spark = spark
        elif catalog:
            self.spark = SparkSession.builder.getOrCreate()
        else:
            self.spark = (
                SparkSession.builder.master("local[4]").appName("slc-oracle")
                .config("spark.ui.enabled", "false")
                .config("spark.sql.session.timeZone", "UTC")
                .config("spark.driver.memory", "8g")
                .config("spark.sql.shuffle.partitions", "32")
                .getOrCreate()
            )
            self.spark.sparkContext.setLogLevel("ERROR")
        if catalog:
            self.name = "databricks"
            self.spark.sql(f"USE CATALOG `{catalog}`")
            return
        for schema, tables in TABLES.items():
            self.spark.sql(f"CREATE DATABASE IF NOT EXISTS {schema}")
            for table in tables:
                self.spark.sql(f"DROP TABLE IF EXISTS {schema}.{table}")
                if fixtures:
                    raw = f"{schema}.raw_{table}"
                    self.spark.sql(f"DROP VIEW IF EXISTS {schema}.{table}")
                    self.spark.sql(f"DROP TABLE IF EXISTS {raw}")
                    self.spark.sql(
                        f"CREATE TABLE {raw} USING csv OPTIONS (path '{fixtures / schema / (table + '.csv')}', header 'true')"
                    )
                    self.spark.sql(
                        f"CREATE VIEW {schema}.{table} AS SELECT {fixture_columns(fixtures, schema, table, 'spark')} FROM {raw}"
                    )
                else:
                    self.spark.sql(
                        f"CREATE TABLE {schema}.{table} USING parquet LOCATION '{data_root}/{schema}.db/{table}'"
                    )

    def execute(self, sql):
        df = self.spark.sql(sql)
        rows = df.collect()
        return list(df.columns), [tuple(r) for r in rows]


def fixture_columns(fixtures: Path, schema: str, table: str, engine: str) -> str:
    """Typed projection of a fixture CSV (all columns read as text) per fixtures/schema.json."""
    types = json.loads((fixtures / "schema.json").read_text())[f"{schema}.{table}"]
    quote = '"' if engine == "duckdb" else "`"
    # DuckDB's TIMESTAMP is timezone-naive, the equivalent of Spark's TIMESTAMP_NTZ.
    native = (lambda t: t.replace("TIMESTAMP_NTZ", "TIMESTAMP")) if engine == "duckdb" else (lambda t: t)
    return ", ".join(f"CAST(NULLIF({quote}{c}{quote}, '') AS {native(t)}) AS {c}" for c, t in types)


def fixture_select(fixtures: Path, schema: str, table: str, engine: str) -> str:
    path = fixtures / schema / f"{table}.csv"
    return (f"(SELECT {fixture_columns(fixtures, schema, table, engine)} "
            f"FROM read_csv('{path}', header=true, all_varchar=true))")


def make_engine(args) -> Engine:
    if args.engine == "duckdb":
        return DuckDBEngine(data_root=args.data_root, threads=args.threads)
    if args.engine == "duckdb-fixtures":
        return DuckDBEngine(fixtures=args.fixtures)
    if args.engine == "spark":
        return SparkEngine(data_root=args.data_root)
    if args.engine == "spark-fixtures":
        return SparkEngine(fixtures=args.fixtures)
    if args.engine == "databricks":
        return SparkEngine(catalog=args.catalog)
    raise SystemExit(f"unknown engine {args.engine}")


# ------------------------------------------------------------------ values

def to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return str(value)


def values_match(actual, expected_text: str) -> bool:
    if actual is None or expected_text == "":
        return actual is None and expected_text == ""
    if isinstance(actual, bool):
        return to_text(actual) == expected_text
    if isinstance(actual, int):
        try:
            return actual == int(Decimal(expected_text))
        except ArithmeticError:
            return False
    if isinstance(actual, Decimal):
        try:
            return abs(actual - Decimal(expected_text)) <= MONEY_TOLERANCE
        except ArithmeticError:
            return False
    if isinstance(actual, float):
        try:
            return abs(actual - float(expected_text)) <= RATIO_TOLERANCE
        except ValueError:
            return False
    return to_text(actual) == expected_text


def compare(columns: list[str], rows: list[tuple], expected_path: Path) -> list[str]:
    with expected_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        expected = list(reader)
    problems = []
    if [c.lower() for c in columns] != [h.lower() for h in header]:
        problems.append(f"columns {columns} != expected {header}")
        return problems
    if len(rows) != len(expected):
        problems.append(f"{len(rows)} rows != expected {len(expected)}")
    for i, (row, exp) in enumerate(zip(rows, expected)):
        for col, actual, want in zip(columns, row, exp):
            if not values_match(actual, want):
                problems.append(f"row {i} {col}: {to_text(actual)!r} != expected {want!r}")
                if len(problems) > 10:
                    return problems
    return problems


def write_csv(columns: list[str], rows: list[tuple], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(columns)
        for row in rows:
            w.writerow([to_text(v) for v in row])


# ------------------------------------------------------------------ run

@dataclass
class Result:
    query_id: str
    kind: str
    rows: int = 0
    seconds: list[float] = field(default_factory=list)
    error: str | None = None
    problems: list[str] = field(default_factory=list)

    def as_dict(self):
        warm = self.seconds[1:] or self.seconds
        return {
            "query_id": self.query_id, "kind": self.kind, "rows": self.rows,
            "runs_seconds": [round(s, 4) for s in self.seconds],
            "first_run_seconds": round(self.seconds[0], 4) if self.seconds else None,
            "warm_median_seconds": round(statistics.median(warm), 4) if warm else None,
            "error": self.error, "mismatches": self.problems,
        }


def run(engine: Engine, queries: list[Query], repeat: int, write_dir: Path | None,
        compare_dir: Path | None, verbose: bool = True) -> list[Result]:
    results = []
    for q in queries:
        res = Result(q.query_id, q.kind)
        columns, rows = [], []
        try:
            for _ in range(max(1, repeat)):
                t0 = time.perf_counter()
                columns, rows = engine.execute(q.sql)
                res.seconds.append(time.perf_counter() - t0)
            res.rows = len(rows)
            if write_dir:
                write_csv(columns, rows, write_dir / q.kind / f"{q.query_id}.csv")
            if compare_dir:
                target = compare_dir / q.kind / f"{q.query_id}.csv"
                res.problems = compare(columns, rows, target) if target.exists() else [f"missing {target}"]
        except Exception as exc:  # recorded per query; the run continues
            res.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:400]}"
        results.append(res)
        if verbose:
            status = "ERROR" if res.error else ("DIFF" if res.problems else "ok")
            warm = res.as_dict()["warm_median_seconds"]
            print(f"{status:5} {q.query_id:14} rows={res.rows:<7} first={res.seconds[0] if res.seconds else 0:7.3f}s "
                  f"warm={warm if warm is not None else 0:7.3f}s {res.error or ''}", flush=True)
            for p in res.problems[:5]:
                print(f"        {p}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True,
                        choices=["duckdb", "spark", "databricks", "duckdb-fixtures", "spark-fixtures"])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--fixtures", type=Path, default=ORACLE / "fixtures")
    parser.add_argument("--catalog")
    parser.add_argument("--select", default="*")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--write-expected", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--perf", type=Path)
    args = parser.parse_args()

    engine = make_engine(args)
    started = time.time()
    results = run(engine, load_queries(args.select), args.repeat, args.write_expected, args.compare)
    engine.close()
    errors = [r for r in results if r.error]
    diffs = [r for r in results if r.problems]
    summary = {
        "engine": engine.name, "queries": len(results), "errors": len(errors), "mismatched": len(diffs),
        "repeat": args.repeat, "wall_seconds": round(time.time() - started, 1),
        "run_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }
    if args.perf:
        args.perf.parent.mkdir(parents=True, exist_ok=True)
        args.perf.write_text(json.dumps({"summary": summary, "results": [r.as_dict() for r in results]}, indent=1))
    print(json.dumps(summary))
    raise SystemExit(1 if errors or diffs else 0)


if __name__ == "__main__":
    main()
