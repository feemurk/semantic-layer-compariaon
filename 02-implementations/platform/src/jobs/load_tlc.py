"""Download TLC Yellow Taxi months and land them, normalized, for Auto Loader (SPEC § 4).

For each month in [--first-month, --last-month]:
  1. download yellow_tripdata_<YYYY-MM>.parquet to /Volumes/<catalog>/raw_nyctaxi/source/
     (immutable original; skipped when already present)
  2. read that single file with its own schema, project it onto the landing schema
     (slc_platform.nyctaxi.normalize_source), write to a staging directory, then move the
     finished directory into /Volumes/<catalog>/raw_nyctaxi/landing/tlc_yellow/baseline/<YYYY-MM>/
     so Auto Loader never observes a partially written month.
Also downloads taxi_zone_lookup.csv. Idempotent: months already landed are skipped.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyspark.sql import SparkSession  # noqa: E402

from slc_platform import nyctaxi  # noqa: E402

TLC_BASE = "https://d37ci6vzurychx.cloudfront.net"
CHUNK = 8 * 1024 * 1024


def months(first: str, last: str) -> list[str]:
    fy, fm = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    y, m = fy, fm
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"present  {dest}")
        return
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=600) as response, open(part, "wb") as out:
        while chunk := response.read(CHUNK):
            out.write(chunk)
    os.replace(part, dest)
    print(f"download {url} -> {dest} ({dest.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--first-month", default="2023-01")
    parser.add_argument("--last-month", default="2024-12")
    args = parser.parse_args()

    source = Path(f"/Volumes/{args.catalog}/raw_nyctaxi/source")
    landing = Path(f"/Volumes/{args.catalog}/raw_nyctaxi/landing/tlc_yellow/baseline")
    staging = source / "_staging"
    landing.mkdir(parents=True, exist_ok=True)
    staging.mkdir(parents=True, exist_ok=True)

    spark = SparkSession.builder.getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    download(f"{TLC_BASE}/misc/taxi_zone_lookup.csv", source / "taxi_zone_lookup.csv")

    for month in months(args.first_month, args.last_month):
        name = f"yellow_tripdata_{month}.parquet"
        raw = source / name
        target = landing / month
        if (target / "_SUCCESS").exists():
            print(f"landed   {target}")
            continue
        download(f"{TLC_BASE}/trip-data/{name}", raw)
        work = staging / month
        if work.exists():
            shutil.rmtree(work)
        nyctaxi.normalize_source(spark.read.parquet(str(raw)), name).write.parquet(str(work))
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(work), str(target))
        print(f"landed   {target}")


if __name__ == "__main__":
    main()
