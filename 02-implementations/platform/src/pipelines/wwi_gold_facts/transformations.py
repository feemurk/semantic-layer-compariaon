"""Lakeflow pipeline: WideWorldImporters gold facts and bridge (SPEC § 5.1, § 5.3).

Depends on wwi_gold_dimensions having published dim_date, dim_stock_item,
dim_customer, dim_city, dim_employee and dim_stock_group.
Pipeline configuration: slc.raw_schema, slc.gold_schema (see wwi_gold_dimensions).
"""

from pyspark import pipelines as dp
from pyspark.sql import SparkSession

from slc_platform import wwi
from slc_platform.schema import WWI_SNAPSHOT_WINDOW, WWI_TABLES

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


_register("fact_sale", lambda: wwi.conform("fact_sale", _bronze("sale")))
_register("fact_order", lambda: wwi.conform("fact_order", _bronze("order")))
_register("fact_stock_movement", lambda: wwi.conform("fact_stock_movement", _bronze("movement")))
_register("stock_holding_current", lambda: wwi.conform("stock_holding_current", _bronze("stock_holding")))
_register(
    "bridge_stock_item_group",
    lambda: wwi.conform("bridge_stock_item_group", _bronze("stock_item_stock_groups")),
)
_register(
    "fact_stock_holding_daily",
    lambda: wwi.fact_stock_holding_daily(
        movement=spark.read.table("fact_stock_movement"),
        holding=spark.read.table("stock_holding_current"),
        stock_item=spark.read.table(f"{GOLD}.dim_stock_item"),
        dates=spark.read.table(f"{GOLD}.dim_date"),
        window_start=WWI_SNAPSHOT_WINDOW[0],
        window_end=WWI_SNAPSHOT_WINDOW[1],
    ),
)
