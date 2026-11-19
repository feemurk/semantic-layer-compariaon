"""Build baseline B0 locally from the real sources and run the profiling assertions.

Local stand-in for the Databricks build, executing the same slc_platform code:

  WWI  bronze: Spark JDBC reads of the restored SQL Server copy, written with the same
       destination table names and source column names that Lakeflow Connect produces.
  NYC  landing: every TLC monthly file normalized with nyctaxi.normalize_source;
       bronze: the union of landing files (what Auto Loader appends).
  gold: slc_platform transforms; then src/sql/profiling + generated PK/FK checks.

Tables are written to a local Spark warehouse as Parquet tables in databases raw_wwi,
wwi, raw_nyctaxi and nyctaxi. Requires Java 17+, pyspark (scripts/requirements-test.txt)
and the Microsoft JDBC driver, fetched from Maven Central via spark.jars.packages.

Usage:
  python tools/local_b0.py --warehouse DIR --tlc-dir DIR \
      --jdbc-url 'jdbc:sqlserver://localhost:1433;encrypt=true;trustServerCertificate=true' \
      --jdbc-user sa --jdbc-password-env SLC_SQLSERVER_PASSWORD [--months 2023-01..2024-12]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM / "src"))

from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from slc_platform import calendar, nyctaxi, profiling, wwi  # noqa: E402
from slc_platform.schema import (  # noqa: E402
    NYC_CALENDAR,
    NYC_TABLES,
    WWI_CALENDAR,
    WWI_SNAPSHOT_WINDOW,
    WWI_TABLES,
)

JDBC_DRIVER = "com.microsoft.sqlserver.jdbc.SQLServerDriver"
JDBC_PACKAGE = "com.microsoft.sqlserver:mssql-jdbc:12.10.1.jre11"

# Lakeflow Connect destination table -> (source database, source table).
WWI_SOURCES = {
    "dw_fact_sale": ("WideWorldImportersDW", "[Fact].[Sale]"),
    "dw_fact_order": ("WideWorldImportersDW", "[Fact].[Order]"),
    "dw_fact_movement": ("WideWorldImportersDW", "[Fact].[Movement]"),
    "dw_fact_stock_holding": ("WideWorldImportersDW", "[Fact].[Stock Holding]"),
    "dw_dimension_stock_item": ("WideWorldImportersDW", "[Dimension].[Stock Item]"),
    "dw_dimension_customer": ("WideWorldImportersDW", "[Dimension].[Customer]"),
    "dw_dimension_city": ("WideWorldImportersDW", "[Dimension].[City]"),
    "dw_dimension_employee": ("WideWorldImportersDW", "[Dimension].[Employee]"),
    "dw_dimension_date": ("WideWorldImportersDW", "[Dimension].[Date]"),
    "oltp_warehouse_stockgroups": ("WideWorldImporters", "[Warehouse].[StockGroups]"),
    "oltp_warehouse_stockitemstockgroups": ("WideWorldImporters", "[Warehouse].[StockItemStockGroups]"),
}
# Binary and spatial columns Lakeflow Connect would carry but no transform reads.
WWI_DROP = {"Photo", "Location"}


def spark_session(warehouse: Path) -> SparkSession:
    spark = (
        SparkSession.builder.master("local[4]")
        .appName("slc-local-b0")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.warehouse.dir", str(warehouse / "warehouse"))
        .config("spark.driver.memory", "10g")
        .config("spark.sql.shuffle.partitions", "64")
        .config("spark.jars.packages", JDBC_PACKAGE)
        .config("spark.jars.ivy", str(warehouse / "ivy"))
        .config("javax.jdo.option.ConnectionURL", f"jdbc:derby:;databaseName={warehouse / 'metastore'};create=true")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def save(df, name: str) -> None:
    df.write.mode("overwrite").format("parquet").saveAsTable(name)


def build_wwi(spark: SparkSession, url: str, user: str, password: str) -> None:
    for db in ("raw_wwi", "wwi"):
        spark.sql(f"CREATE DATABASE IF NOT EXISTS {db}")
    for target, (database, table) in WWI_SOURCES.items():
        df = (
            spark.read.format("jdbc")
            .option("driver", JDBC_DRIVER)
            .option("url", f"{url};databaseName={database}")
            .option("user", user)
            .option("password", password)
            .option("dbtable", table)
            .load()
        )
        save(df.drop(*[c for c in df.columns if c in WWI_DROP]), f"raw_wwi.{target}")

    def bronze(key: str):
        return spark.table(f"raw_wwi.{wwi.BRONZE[key]}")

    save(calendar.dim_date(spark, *WWI_CALENDAR), "wwi.dim_date")
    for table, key in [
        ("dim_stock_item", "stock_item"),
        ("dim_customer", "customer"),
        ("dim_city", "city"),
        ("dim_employee", "employee"),
        ("dim_stock_group", "stock_groups"),
        ("fact_sale", "sale"),
        ("fact_order", "order"),
        ("fact_stock_movement", "movement"),
        ("stock_holding_current", "stock_holding"),
        ("bridge_stock_item_group", "stock_item_stock_groups"),
    ]:
        save(wwi.conform(table, bronze(key)), f"wwi.{table}")
    save(
        wwi.fact_stock_holding_daily(
            movement=spark.table("wwi.fact_stock_movement"),
            holding=spark.table("wwi.stock_holding_current"),
            stock_item=spark.table("wwi.dim_stock_item"),
            dates=spark.table("wwi.dim_date"),
            window_start=WWI_SNAPSHOT_WINDOW[0],
            window_end=WWI_SNAPSHOT_WINDOW[1],
        ),
        "wwi.fact_stock_holding_daily",
    )


def month_range(spec: str) -> list[str]:
    first, last = spec.split("..")
    fy, fm = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out, y, m = [], fy, fm
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build_nyc(spark: SparkSession, tlc_dir: Path, warehouse: Path, months: list[str]) -> None:
    for db in ("raw_nyctaxi", "nyctaxi"):
        spark.sql(f"CREATE DATABASE IF NOT EXISTS {db}")
    landing = warehouse / "landing" / "tlc_yellow" / "baseline"
    for month in months:
        name = f"yellow_tripdata_{month}.parquet"
        out = landing / month
        if not (out / "_SUCCESS").exists():
            nyctaxi.normalize_source(spark.read.parquet(str(tlc_dir / name)), name).write.mode(
                "overwrite"
            ).parquet(str(out))
    save(spark.read.schema(nyctaxi.LANDING_DDL).parquet(*[str(landing / m) for m in months]), "raw_nyctaxi.trips_bronze")

    save(calendar.dim_date(spark, *NYC_CALENDAR), "nyctaxi.dim_date")
    zones = spark.read.option("header", "true").schema(
        "LocationID INT, Borough STRING, Zone STRING, service_zone STRING"
    ).csv(str(tlc_dir / "taxi_zone_lookup.csv"))
    save(nyctaxi.dim_zone(zones), "nyctaxi.dim_zone")
    save(nyctaxi.dim_payment_type(spark), "nyctaxi.dim_payment_type")

    save(nyctaxi.conform(spark.table("raw_nyctaxi.trips_bronze")), "nyctaxi.trips_conformed")
    save(nyctaxi.fact_trip(spark.table("nyctaxi.trips_conformed")), "nyctaxi.fact_trip")
    save(nyctaxi.fact_trip_quarantine(spark.table("nyctaxi.trips_conformed")), "nyctaxi.fact_trip_quarantine")


def summary(spark: SparkSession) -> dict:
    out = {}
    for schema, tables in (("wwi", WWI_TABLES), ("nyctaxi", NYC_TABLES)):
        for name in tables:
            if spark.catalog.tableExists(f"{schema}.{name}"):
                out[f"{schema}.{name}"] = spark.table(f"{schema}.{name}").count()
    if spark.catalog.tableExists("wwi.fact_stock_holding_daily"):
        out["wwi.balance_basis_items"] = {
            r["balance_basis"]: r["items"]
            for r in spark.table("wwi.fact_stock_holding_daily")
            .groupBy("balance_basis")
            .agg(F.countDistinct("wwi_stock_item_id").alias("items"))
            .collect()
        }
    if spark.catalog.tableExists("nyctaxi.fact_trip_quarantine"):
        out["nyctaxi.reject_reasons"] = {
            r["reject_reason"]: r["n"]
            for r in spark.table("nyctaxi.fact_trip_quarantine").groupBy("reject_reason").agg(F.count("*").alias("n")).collect()
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--tlc-dir", type=Path)
    parser.add_argument("--jdbc-url")
    parser.add_argument("--jdbc-user", default="sa")
    parser.add_argument("--jdbc-password-env", default="SLC_SQLSERVER_PASSWORD")
    parser.add_argument("--months", default="2023-01..2024-12")
    parser.add_argument("--skip-wwi", action="store_true")
    parser.add_argument("--skip-nyc", action="store_true")
    parser.add_argument("--profile-only", action="store_true")
    args = parser.parse_args()

    args.warehouse.mkdir(parents=True, exist_ok=True)
    spark = spark_session(args.warehouse)
    started = time.time()
    if not args.profile_only:
        if not args.skip_wwi:
            build_wwi(spark, args.jdbc_url, args.jdbc_user, os.environ[args.jdbc_password_env])
            print(f"wwi built in {time.time() - started:.0f}s", flush=True)
        if not args.skip_nyc:
            build_nyc(spark, args.tlc_dir, args.warehouse, month_range(args.months))
            print(f"nyc built in {time.time() - started:.0f}s", flush=True)

    checks = profiling.all_checks(PLATFORM / "src" / "sql" / "profiling")
    failures = profiling.run(spark, checks)
    failed = {c.check_id for c, _ in failures}
    for check in checks:
        print(f"{'FAIL' if check.check_id in failed else 'pass'}  {check.check_id}")
    for check, rows in failures:
        print(f"{check.check_id}: {[r.asDict() for r in rows]}")
    result = {
        "checks": len(checks),
        "failed": sorted(failed),
        "summary": summary(spark),
        "seconds": round(time.time() - started),
    }
    (args.warehouse / "local_b0_result.json").write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps(result, indent=2, default=str))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
