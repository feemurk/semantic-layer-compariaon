"""NYC Yellow Taxi transforms (SPEC § 5.2, § 5.3).

Two stages:

1. normalize_source(): applied once per downloaded TLC monthly file before it
   lands for Auto Loader. TLC files drift in type and case between months
   (2023-01: BIGINT ids, DOUBLE passenger_count, `airport_fee`; 2023-02 onward:
   INT ids, BIGINT passenger_count, `Airport_fee`). Spark cannot read an INT64
   Parquet column as DOUBLE, and Auto Loader schema hints would rescue those
   values into `_rescued_data`, leaving NULLs. Normalizing each file with its
   own inferred schema to one landing schema removes the drift losslessly.
2. conform(): bronze rows to canonical trips, with deterministic trip_id and the
   first failed rule of the valid trip predicate as reject_reason.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from slc_platform.schema import NYC_PICKUP_WINDOW, NYC_TABLES

# Canonical landing schema: every TLC Yellow column present in 2023-2024, widest type.
LANDING_COLUMNS: list[tuple[str, str]] = [
    ("VendorID", "BIGINT"),
    ("tpep_pickup_datetime", "TIMESTAMP_NTZ"),
    ("tpep_dropoff_datetime", "TIMESTAMP_NTZ"),
    ("passenger_count", "DOUBLE"),
    ("trip_distance", "DOUBLE"),
    ("RatecodeID", "DOUBLE"),
    ("store_and_fwd_flag", "STRING"),
    ("PULocationID", "BIGINT"),
    ("DOLocationID", "BIGINT"),
    ("payment_type", "BIGINT"),
    ("fare_amount", "DOUBLE"),
    ("extra", "DOUBLE"),
    ("mta_tax", "DOUBLE"),
    ("tip_amount", "DOUBLE"),
    ("tolls_amount", "DOUBLE"),
    ("improvement_surcharge", "DOUBLE"),
    ("total_amount", "DOUBLE"),
    ("congestion_surcharge", "DOUBLE"),
    ("airport_fee", "DOUBLE"),
    ("source_file", "STRING"),
]
LANDING_DDL = ", ".join(f"{n} {t}" for n, t in LANDING_COLUMNS)

REJECT_RULES: list[tuple[str, str]] = [
    # (reason, predicate that must hold), evaluated in SPEC § 5.3 rule 1 order.
    ("pickup_not_before_dropoff", "pickup_ts < dropoff_ts"),
    ("trip_distance_out_of_range", "trip_distance > 0 AND trip_distance <= 200"),
    ("negative_fare_amount", "fare_amount >= 0"),
    ("negative_total_amount", "total_amount >= 0"),
    (
        "pickup_outside_window",
        f"pickup_date BETWEEN DATE'{NYC_PICKUP_WINDOW[0]}' AND DATE'{NYC_PICKUP_WINDOW[1]}'",
    ),
]

# TLC Yellow Taxi data dictionary payment type codes.
PAYMENT_TYPES: list[tuple[int, str]] = [
    (0, "Flex Fare trip"),
    (1, "Credit card"),
    (2, "Cash"),
    (3, "No charge"),
    (4, "Dispute"),
    (5, "Unknown"),
    (6, "Voided trip"),
]

# Ordinal slots per pickup second in trip_id; profiled maximum is 17 trips per second.
TRIP_ID_SLOTS = 100


def normalize_source(df: DataFrame, source_file: str) -> DataFrame:
    """Project one TLC file, read with its own schema, onto the landing schema."""
    by_lower = {c.lower(): c for c in df.columns}
    cols = []
    for name, dtype in LANDING_COLUMNS:
        if name == "source_file":
            cols.append(F.lit(source_file).alias(name))
        elif name.lower() in by_lower:
            cols.append(F.col(f"`{by_lower[name.lower()]}`").cast(dtype).alias(name))
        else:
            cols.append(F.lit(None).cast(dtype).alias(name))
    return df.select(*cols)


def _money(c: str, precision: int) -> Column:
    return F.round(F.col(c), 2).cast(f"decimal({precision},2)")


def conform(bronze: DataFrame) -> DataFrame:
    """Return every bronze row with canonical columns, trip_id and reject_reason (NULL = valid)."""
    seconds = F.expr("timestampdiff(SECOND, TIMESTAMP_NTZ'1970-01-01 00:00:00', tpep_pickup_datetime)")
    ordinal_window = Window.partitionBy("tpep_pickup_datetime").orderBy(
        *[F.col(n).asc_nulls_first() for n, _ in LANDING_COLUMNS if n not in ("tpep_pickup_datetime", "source_file")]
    )
    staged = bronze.select(
        "*",
        (seconds * TRIP_ID_SLOTS + F.row_number().over(ordinal_window) - 1).alias("trip_id"),
    )
    trips = staged.select(
        F.col("trip_id").cast("bigint"),
        F.col("VendorID").cast("int").alias("vendor_id"),
        F.col("tpep_pickup_datetime").cast("timestamp_ntz").alias("pickup_ts"),
        F.col("tpep_dropoff_datetime").cast("timestamp_ntz").alias("dropoff_ts"),
        F.to_date("tpep_pickup_datetime").alias("pickup_date"),
        F.to_date("tpep_dropoff_datetime").alias("dropoff_date"),
        F.hour("tpep_pickup_datetime").cast("tinyint").alias("pickup_hour"),
        F.col("PULocationID").cast("int").alias("pu_location_id"),
        F.col("DOLocationID").cast("int").alias("do_location_id"),
        (F.col("PULocationID") * 1000 + F.col("DOLocationID")).cast("int").alias("od_pair_id"),
        F.col("passenger_count").cast("int").alias("passenger_count"),
        _money("trip_distance", 9).alias("trip_distance"),
        F.col("payment_type").cast("int").alias("payment_type"),
        _money("fare_amount", 10).alias("fare_amount"),
        _money("tip_amount", 10).alias("tip_amount"),
        _money("tolls_amount", 10).alias("tolls_amount"),
        _money("total_amount", 10).alias("total_amount"),
    )
    # A NULL predicate is a failure: coalesce(..., false).
    reason = F.lit(None).cast("string")
    for rule, predicate in reversed(REJECT_RULES):
        reason = F.when(~F.coalesce(F.expr(predicate), F.lit(False)), F.lit(rule)).otherwise(reason)
    return trips.withColumn("reject_reason", reason)


def fact_trip(conformed: DataFrame) -> DataFrame:
    return conformed.where(F.col("reject_reason").isNull()).select(*NYC_TABLES["fact_trip"].column_names)


def fact_trip_quarantine(conformed: DataFrame) -> DataFrame:
    return conformed.where(F.col("reject_reason").isNotNull()).select(
        *NYC_TABLES["fact_trip_quarantine"].column_names
    )


def dim_zone(zone_csv: DataFrame) -> DataFrame:
    """TLC taxi_zone_lookup.csv (LocationID, Borough, Zone, service_zone) to dim_zone.

    Source labels are kept verbatim, including 264 'Unknown' and 265 'Outside of NYC'.
    """
    return zone_csv.select(
        F.col("LocationID").cast("int").alias("location_id"),
        F.col("Borough").alias("borough"),
        F.col("Zone").alias("zone"),
        F.col("service_zone").alias("service_zone"),
    )


def dim_payment_type(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(PAYMENT_TYPES, "payment_type INT, payment_type_name STRING")
