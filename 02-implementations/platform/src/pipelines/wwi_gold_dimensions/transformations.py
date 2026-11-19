"""Lakeflow pipeline: WideWorldImporters gold dimensions (SPEC § 5.1, § 5.4).

Runs before wwi_gold_facts so that fact foreign keys reference published parents.
Pipeline configuration:
  slc.raw_schema   fully qualified bronze schema written by Lakeflow Connect (e.g. slc.raw_wwi)
  slc.gold_schema  fully qualified gold schema (e.g. slc.wwi); the pipeline's default schema
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from slc_platform import calendar, wwi
from slc_platform.schema import WWI_CALENDAR, WWI_TABLES

spark = SparkSession.getActiveSession()
RAW = spark.conf.get("slc.raw_schema")
GOLD = spark.conf.get("slc.gold_schema")


def _register(table: str, build) -> None:
    spec = WWI_TABLES[table]
    options = {"name": table, "comment": spec.comment, "schema": spec.ddl(GOLD)}
    if spec.cluster_by:
        options["cluster_by"] = list(spec.cluster_by)
    dp.materialized_view(**options)(build)


def _bronze(key: str):
    return spark.read.table(f"{RAW}.{wwi.BRONZE[key]}")


_register("dim_date", lambda: calendar.dim_date(spark, *WWI_CALENDAR))
_register("dim_stock_item", lambda: wwi.conform("dim_stock_item", _bronze("stock_item")))
_register("dim_customer", lambda: wwi.conform("dim_customer", _bronze("customer")))
_register("dim_city", lambda: wwi.conform("dim_city", _bronze("city")))
_register("dim_employee", lambda: wwi.conform("dim_employee", _bronze("employee")))
_register("dim_stock_group", lambda: wwi.conform("dim_stock_group", _bronze("stock_groups")))
