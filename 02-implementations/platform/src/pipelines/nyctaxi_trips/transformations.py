"""Lakeflow pipeline: NYC Taxi bronze (Auto Loader) and gold trips (SPEC § 4, § 5.2, § 5.3).

Depends on nyctaxi_dimensions having published dim_date, dim_zone and dim_payment_type.
Pipeline configuration:
  slc.raw_schema     fully qualified bronze schema (e.g. slc.raw_nyctaxi)
  slc.gold_schema    fully qualified gold schema (e.g. slc.nyctaxi); the pipeline's default schema
  slc.landing_path   volume directory that load_tlc.py and replay_tlc.py write normalized Parquet to
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from slc_platform import nyctaxi
from slc_platform.schema import NYC_TABLES

spark = SparkSession.getActiveSession()
RAW = spark.conf.get("slc.raw_schema")
GOLD = spark.conf.get("slc.gold_schema")
LANDING = spark.conf.get("slc.landing_path")


@dp.table(
    name=f"{RAW}.trips_bronze",
    comment="TLC Yellow Taxi rows in the canonical landing schema, ingested by Auto Loader.",
)
def trips_bronze():
    # Landing files are pre-normalized (nyctaxi.normalize_source), so the schema is fixed.
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .schema(nyctaxi.LANDING_DDL)
        .load(LANDING)
    )


@dp.materialized_view(
    name="trips_conformed",
    comment="Every bronze row with canonical columns, trip_id and reject_reason.",
    private=True,
)
def trips_conformed():
    return nyctaxi.conform(spark.read.table(f"{RAW}.trips_bronze"))


_trip = NYC_TABLES["fact_trip"]


@dp.materialized_view(
    name="fact_trip",
    comment=_trip.comment,
    schema=_trip.ddl(GOLD),
    cluster_by=list(_trip.cluster_by),
)
def fact_trip():
    return nyctaxi.fact_trip(spark.read.table("trips_conformed"))


_quarantine = NYC_TABLES["fact_trip_quarantine"]


@dp.materialized_view(
    name="fact_trip_quarantine",
    comment=_quarantine.comment,
    schema=_quarantine.ddl(GOLD),
)
def fact_trip_quarantine():
    return nyctaxi.fact_trip_quarantine(spark.read.table("trips_conformed"))
