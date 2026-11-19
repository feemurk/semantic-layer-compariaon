"""Gap-free date dimension (SPEC § 5.4).

Fiscal calendar: the fiscal year starts on 1 November and is labeled by the
calendar year in which it ends (FY2014 = 2013-11-01 .. 2014-10-31). This matches
WideWorldImportersDW [Dimension].[Date], verified against the restored source.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql import functions as F

FISCAL_YEAR_START_MONTH = 11


def _fiscal_year(d: Column) -> Column:
    return F.year(d) + F.when(F.month(d) >= FISCAL_YEAR_START_MONTH, 1).otherwise(0)


def _fiscal_month(d: Column) -> Column:
    return F.pmod(F.month(d) - FISCAL_YEAR_START_MONTH, F.lit(12)) + 1


def dim_date(spark: SparkSession, start: str, end: str) -> DataFrame:
    """Return one row per calendar day in [start, end] (ISO date strings)."""
    days = spark.range(1).select(
        F.explode(
            F.sequence(F.to_date(F.lit(start)), F.to_date(F.lit(end)), F.expr("INTERVAL 1 DAY"))
        ).alias("date_key")
    )
    d = F.col("date_key")
    fiscal_year = _fiscal_year(d)
    fiscal_month = _fiscal_month(d)
    fiscal_year_start = F.make_date(fiscal_year - 1, F.lit(FISCAL_YEAR_START_MONTH), F.lit(1))
    return days.select(
        d.alias("date_key"),
        F.year(d).cast("smallint").alias("calendar_year"),
        F.quarter(d).cast("tinyint").alias("calendar_quarter"),
        F.month(d).cast("tinyint").alias("calendar_month"),
        F.date_format(d, "MMMM").alias("month_name"),
        F.trunc(d, "month").alias("month_start_date"),
        F.dayofmonth(d).cast("tinyint").alias("day_of_month"),
        F.dayofyear(d).cast("smallint").alias("day_of_year"),
        # Spark dayofweek: Sunday = 1 .. Saturday = 7. ISO: Monday = 1 .. Sunday = 7.
        (F.pmod(F.dayofweek(d) + 5, F.lit(7)) + 1).cast("tinyint").alias("day_of_week"),
        F.date_format(d, "EEEE").alias("day_name"),
        F.weekofyear(d).cast("tinyint").alias("iso_week_number"),
        fiscal_year.cast("smallint").alias("fiscal_year"),
        (F.floor((fiscal_month - 1) / 3) + 1).cast("tinyint").alias("fiscal_quarter"),
        fiscal_month.cast("tinyint").alias("fiscal_month"),
        (fiscal_year * 12 + fiscal_month).cast("int").alias("fiscal_period_index"),
        (F.datediff(d, fiscal_year_start) + 1).cast("smallint").alias("day_of_fiscal_year"),
    )
