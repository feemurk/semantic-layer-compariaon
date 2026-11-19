"""Freshness replay of December 2024 (SPEC § 9.4).

Subcommands:
  prepare  Withhold the landed 2024-12 month: move it out of the landing volume, delete its
           rows from raw_nyctaxi.trips_bronze, and write the replay plan to ops.replay_log
           (batch number, rows, sentinel trip, expected cumulative valid trip count).
  run      Land one 15-minute batch of December trips every 60 seconds into
           landing/tlc_yellow/replay/batch_<NNNN>/ and stamp landed_at in ops.replay_log.
           --start-batch resumes an interrupted run.

Run with the nyctaxi_trips pipeline in continuous mode (bundle target `freshness`).
After the last batch, the gold build equals baseline B0 (no synthetic rows are added).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from slc_platform import nyctaxi, replay  # noqa: E402

MONTH = "2024-12"
SOURCE_FILE = f"yellow_tripdata_{MONTH}.parquet"


def paths(catalog: str) -> dict[str, Path]:
    volumes = Path(f"/Volumes/{catalog}/raw_nyctaxi")
    return {
        "baseline": volumes / "landing/tlc_yellow/baseline" / MONTH,
        "replay": volumes / "landing/tlc_yellow/replay",
        "withheld": volumes / "source/withheld" / MONTH,
        "staging": volumes / "source/_staging/replay",
    }


def prepare(spark: SparkSession, catalog: str) -> None:
    p = paths(catalog)
    if p["baseline"].exists():
        p["withheld"].parent.mkdir(parents=True, exist_ok=True)
        if p["withheld"].exists():
            shutil.rmtree(p["withheld"])
        shutil.move(str(p["baseline"]), str(p["withheld"]))
    if not p["withheld"].exists():
        raise SystemExit(f"{p['withheld']} missing: run load_tlc.py for {MONTH} first")
    spark.sql(
        f"DELETE FROM `{catalog}`.raw_nyctaxi.trips_bronze WHERE source_file = :f",
        args={"f": SOURCE_FILE},
    )
    withheld = spark.read.schema(nyctaxi.LANDING_DDL).parquet(str(p["withheld"]))
    conformed = replay.assign_batches(nyctaxi.conform(withheld), ts_col="pickup_ts")
    (
        replay.replay_log(conformed)
        .withColumn("landed_at", F.lit(None).cast("timestamp"))
        .write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"`{catalog}`.ops.replay_log")
    )
    print(f"withheld {MONTH}; replay plan written to {catalog}.ops.replay_log")


def run(spark: SparkSession, catalog: str, start_batch: int) -> None:
    p = paths(catalog)
    p["replay"].mkdir(parents=True, exist_ok=True)
    p["staging"].mkdir(parents=True, exist_ok=True)
    rows = replay.assign_batches(spark.read.schema(nyctaxi.LANDING_DDL).parquet(str(p["withheld"])))
    for batch in range(start_batch, replay.LAST_BATCH + 1):
        started = time.monotonic()
        work = p["staging"] / f"batch_{batch:04d}"
        target = p["replay"] / f"batch_{batch:04d}"
        if work.exists():
            shutil.rmtree(work)
        rows.where(F.col("batch_no") == batch).drop("batch_no").write.parquet(str(work))
        shutil.move(str(work), str(target))
        landed = datetime.now(timezone.utc).replace(tzinfo=None)
        spark.sql(
            f"UPDATE `{catalog}`.ops.replay_log SET landed_at = :ts WHERE batch_no = :b",
            args={"ts": landed, "b": batch},
        )
        print(f"batch {batch:04d} landed {landed.isoformat()}")
        time.sleep(max(0.0, replay.BATCH_INTERVAL_SECONDS - (time.monotonic() - started)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--start-batch", type=int, default=0)
    args = parser.parse_args()
    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    if args.command == "prepare":
        prepare(spark, args.catalog)
    else:
        run(spark, args.catalog, args.start_batch)


if __name__ == "__main__":
    main()
