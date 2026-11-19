"""Lakeflow pipeline: NYC Taxi gold dimensions (SPEC § 5.2, § 5.4).

Runs before nyctaxi_trips so that fact_trip foreign keys reference published parents.
Pipeline configuration:
  slc.gold_schema    fully qualified gold schema (e.g. slc.nyctaxi)
  slc.zone_csv_path  Unity Catalog volume path of taxi_zone_lookup.csv
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from slc_platform import calendar, nyctaxi
from slc_platform.schema import NYC_CALENDAR, NYC_TABLES

spark = SparkSession.getActiveSession()
GOLD = spark.conf.get("slc.gold_schema")
ZONE_CSV = spark.conf.get("slc.zone_csv_path")


def _register(table: str, build) -> None:
    spec = NYC_TABLES[table]
    dp.materialized_view(name=table, comment=spec.comment, schema=spec.ddl(GOLD))(build)


_register("dim_date", lambda: calendar.dim_date(spark, *NYC_CALENDAR))
_register(
    "dim_zone",
    lambda: nyctaxi.dim_zone(
        spark.read.option("header", "true")
        .schema("LocationID INT, Borough STRING, Zone STRING, service_zone STRING")
        .csv(ZONE_CSV)
    ),
)
_register("dim_payment_type", lambda: nyctaxi.dim_payment_type(spark))
