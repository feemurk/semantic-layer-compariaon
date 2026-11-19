"""Run every B0 profiling assertion; exit non-zero when any is violated (SPEC § 13).

Checks: src/sql/profiling/*.sql plus PK/FK checks generated from slc_platform.schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyspark.sql import SparkSession  # noqa: E402

from slc_platform import profiling  # noqa: E402

CHECK_DIR = SRC / "sql" / "profiling"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args()
    spark = SparkSession.builder.getOrCreate()
    spark.sql(f"USE CATALOG `{args.catalog}`")
    checks = profiling.all_checks(CHECK_DIR)
    failures = profiling.run(spark, checks)
    for check in checks:
        status = "FAIL" if any(f[0] is check for f in failures) else "pass"
        print(f"{status}  {check.check_id}  {check.description}")
    for check, rows in failures:
        print(f"\n{check.check_id} sample violations:")
        for row in rows:
            print(f"  {row.asDict()}")
    print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
