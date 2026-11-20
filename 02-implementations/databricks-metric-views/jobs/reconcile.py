"""E1 reconciliation and E3 baseline timings for the metric views (SPEC § 8, § 9.2, § 9.3).

Runs queries/metrics/*.sql (22 metrics at the oracle grains) and queries/questions/*.sql (70 questions) through
slc.semantic, compares each result with 01-spec/oracle/expected/<kind>/<id>.csv under the oracle's tolerances
(run_oracle.values_match), and appends one row per query to slc.ops.mv_reconciliation. Metric results are compared
keyed on (grain, measure, member_1, member_2, member_3), so a missing member is reported once instead of shifting every
later row; question results are compared positionally with run_oracle.compare, as the oracle itself does. Timings are sequential (concurrency 1):
the first run is reported as cold, the median of the remaining runs as warm. Concurrency-10 timings belong to the
E3 load runner, not this job.

Exit status: 1 when any query errors, or when --fail-on-mismatch is set and any result differs from the oracle.
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
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
ORACLE = REPO / "01-spec" / "oracle"
if str(ORACLE) not in sys.path:
    sys.path.insert(0, str(ORACLE))

import run_oracle  # noqa: E402

KINDS = ("metrics", "questions")
RESULT_TABLE = "slc.ops.mv_reconciliation"
METRIC_KEY = ["grain", "measure", "member_1", "member_2", "member_3"]
MAX_PROBLEMS = 25


@dataclass
class Outcome:
    query_id: str
    kind: str
    rows: int = 0
    seconds: list[float] = field(default_factory=list)
    error: str | None = None
    missing: int = 0
    extra: int = 0
    different: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def matches(self) -> bool:
        return self.error is None and not (self.missing or self.extra or self.different or self.problems)

    def timings(self) -> tuple[float | None, float | None]:
        if not self.seconds:
            return None, None
        warm = self.seconds[1:] or self.seconds
        return round(self.seconds[0], 4), round(statistics.median(warm), 4)


def compare_keyed(columns: list[str], rows: list[tuple], expected_path: Path, out: Outcome) -> None:
    """Keyed comparison of a metric result (oracle contract) with its expected CSV."""
    with expected_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        expected = list(reader)
    if [c.lower() for c in columns] != [h.lower() for h in header] or header[:5] != METRIC_KEY:
        out.problems.append(f"columns {columns} != expected {header}")
        return
    want = {tuple(r[:5]): r[5] for r in expected}
    got = {}
    for r in rows:
        got[tuple(run_oracle.to_text(v) for v in r[:5])] = r[5]
    for key in want.keys() - got.keys():
        out.missing += 1
        if len(out.problems) < MAX_PROBLEMS:
            out.problems.append(f"missing {key} expected {want[key]!r}")
    for key in got.keys() - want.keys():
        out.extra += 1
        if len(out.problems) < MAX_PROBLEMS:
            out.problems.append(f"extra {key} value {run_oracle.to_text(got[key])!r}")
    for key in want.keys() & got.keys():
        if not run_oracle.values_match(got[key], want[key]):
            out.different += 1
            if len(out.problems) < MAX_PROBLEMS:
                out.problems.append(f"{key}: {run_oracle.to_text(got[key])!r} != expected {want[key]!r}")
    if len(got) != len(rows):
        out.problems.append(f"{len(rows) - len(got)} duplicate keys in result")


def execute(engine, query: run_oracle.Query, repeat: int) -> Outcome:
    out = Outcome(query.query_id, query.kind)
    try:
        columns, rows = [], []
        for _ in range(max(1, repeat)):
            t0 = time.perf_counter()
            columns, rows = engine.execute(query.sql)
            out.seconds.append(time.perf_counter() - t0)
        out.rows = len(rows)
        expected = ORACLE / "expected" / query.kind / f"{query.query_id}.csv"
        if not expected.exists():
            out.problems.append(f"missing {expected}")
        elif query.kind == "metrics":
            compare_keyed(columns, rows, expected, out)
        else:
            out.problems = run_oracle.compare(columns, rows, expected)
            out.different = len(out.problems)
    except Exception as exc:  # recorded per query; the run continues
        out.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:400]}"
    return out


def load_queries(select: str = "*") -> list[run_oracle.Query]:
    """The stack-native queries, comment lines removed as the oracle runner does."""
    out = []
    for kind in KINDS:
        for path in sorted((HERE / "queries" / kind).glob("*.sql")):
            if fnmatch.fnmatch(path.stem, select):
                text = path.read_text(encoding="utf-8")
                body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))
                out.append(run_oracle.Query(path.stem, kind, path, body.strip().rstrip(";")))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, choices=["governed", "accelerated"],
                        help="deployed profile, recorded with each result")
    parser.add_argument("--select", default="*", help="glob over query ids")
    parser.add_argument("--repeat", type=int, default=4, help="runs per query; the first is the cold run")
    parser.add_argument("--fail-on-mismatch", action="store_true")
    parser.add_argument("--no-record", action="store_true", help=f"do not append to {RESULT_TABLE}")
    args = parser.parse_args()

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    engine = run_oracle.SparkEngine(spark=spark, catalog="slc")
    queries = load_queries(args.select)
    run_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    results = []
    for query in queries:
        out = execute(engine, query, args.repeat)
        results.append(out)
        cold, warm = out.timings()
        status = "ERROR" if out.error else ("ok" if out.matches else "DIFF")
        print(f"{status:5} {out.query_id:14} rows={out.rows:<7} cold={cold or 0:7.3f}s warm={warm or 0:7.3f}s "
              f"missing={out.missing} extra={out.extra} different={out.different} {out.error or ''}", flush=True)
        for problem in out.problems[:5]:
            print(f"        {problem}")

    errors = [r for r in results if r.error]
    diffs = [r for r in results if not r.error and not r.matches]
    summary = {
        "stack": "databricks-metric-views", "profile": args.profile, "queries": len(results),
        "errors": len(errors), "mismatched": len(diffs), "matched": len(results) - len(errors) - len(diffs),
        "repeat": args.repeat, "run_at_utc": run_at.isoformat(),
    }
    print(json.dumps(summary))

    if not args.no_record:
        schema = ("run_at TIMESTAMP, profile STRING, kind STRING, query_id STRING, row_count BIGINT, cold_seconds DOUBLE, "
                  "warm_median_seconds DOUBLE, error STRING, missing_rows INT, extra_rows INT, different_rows INT, "
                  "problems STRING, matches_oracle BOOLEAN")
        rows = [(run_at, args.profile, r.kind, r.query_id, r.rows, *r.timings(), r.error, r.missing, r.extra,
                 r.different, json.dumps(r.problems), r.matches) for r in results]
        spark.sql(f"CREATE TABLE IF NOT EXISTS {RESULT_TABLE} ({schema}) "
                  "COMMENT 'Metric view E1 reconciliation and sequential timings, one row per query per run.'")
        spark.createDataFrame(rows, schema).write.mode("append").saveAsTable(RESULT_TABLE)

    if errors or (args.fail_on_mismatch and diffs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
