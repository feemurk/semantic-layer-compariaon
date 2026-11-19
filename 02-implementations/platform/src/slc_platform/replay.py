"""Freshness replay planning (SPEC § 9.4).

December 2024 is withheld from the baseline load and replayed into the landing
volume in micro-batches: one batch every 60 seconds of wall-clock time, each
carrying the next 15 minutes of trips in pickup_ts order.

Detection without synthetic rows: each batch's sentinel is its last trip
(highest trip_id). The replay log records, per batch, the landing timestamp and
the cumulative count of *valid* trips for the sentinel's pickup_date. A stack
has caught up with batch k when its Trip Count for that Pickup Date reaches the
logged count. Because no synthetic rows are added, the gold build after replay
equals the baseline B0.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

REPLAY_MONTH_START = "2024-12-01 00:00:00"
REPLAY_MONTH_END = "2025-01-01 00:00:00"
BATCH_MINUTES = 15
BATCH_INTERVAL_SECONDS = 60
LAST_BATCH = 31 * 24 * 60 // BATCH_MINUTES - 1  # 2975


def assign_batches(df: DataFrame, ts_col: str = "tpep_pickup_datetime") -> DataFrame:
    """Add batch_no: 15-minute pickup windows from 2024-12-01; strays clamp to the edges.

    ts_col is `tpep_pickup_datetime` for landing rows and `pickup_ts` for conform() output;
    both carry the same value, so a row gets the same batch either way.
    """
    minutes = F.expr(f"timestampdiff(MINUTE, TIMESTAMP_NTZ'{REPLAY_MONTH_START}', `{ts_col}`)")
    raw = F.floor(minutes / BATCH_MINUTES)
    return df.withColumn(
        "batch_no",
        F.when(F.col(ts_col).isNull(), F.lit(0))
        .otherwise(F.least(F.greatest(raw, F.lit(0)), F.lit(LAST_BATCH)))
        .cast("int"),
    )


def replay_log(conformed_with_batch: DataFrame) -> DataFrame:
    """Per batch: sentinel trip and cumulative valid trips for the sentinel's pickup_date.

    Input: slc_platform.nyctaxi.conform() output with batch_no attached.
    """
    valid = conformed_with_batch.where(F.col("reject_reason").isNull())
    sentinel_window = Window.partitionBy("batch_no").orderBy(F.col("trip_id").desc())
    sentinels = (
        valid.withColumn("rn", F.row_number().over(sentinel_window))
        .where("rn = 1")
        .select(
            "batch_no",
            F.col("trip_id").alias("sentinel_trip_id"),
            F.col("pickup_date").alias("sentinel_pickup_date"),
        )
    )
    per_batch_date = valid.groupBy("batch_no", "pickup_date").agg(F.count("*").alias("n"))
    cumulative = per_batch_date.withColumn(
        "cum",
        F.sum("n").over(
            Window.partitionBy("pickup_date").orderBy("batch_no").rowsBetween(
                Window.unboundedPreceding, Window.currentRow
            )
        ),
    )
    batch_rows = conformed_with_batch.groupBy("batch_no").agg(F.count("*").alias("rows_landed"))
    return (
        sentinels.join(
            cumulative.withColumnRenamed("pickup_date", "sentinel_pickup_date"),
            ["batch_no", "sentinel_pickup_date"],
        )
        .join(batch_rows, "batch_no")
        .select(
            "batch_no",
            "rows_landed",
            "sentinel_trip_id",
            "sentinel_pickup_date",
            F.col("cum").alias("expected_trip_count_for_date"),
        )
    )
