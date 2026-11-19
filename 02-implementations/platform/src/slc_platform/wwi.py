"""WideWorldImporters gold transforms (SPEC § 5.1, § 5.3).

Inputs are the bronze tables written by the Lakeflow Connect SQL Server
ingestion pipeline. Bronze keeps the source column names, including spaces
(for example `Sale Key`), so every source reference is backtick-quoted.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from slc_platform.schema import WWI_TABLES

# Bronze table names (Lakeflow Connect destination_table values).
BRONZE = {
    "sale": "dw_fact_sale",
    "order": "dw_fact_order",
    "movement": "dw_fact_movement",
    "stock_holding": "dw_fact_stock_holding",
    "stock_item": "dw_dimension_stock_item",
    "customer": "dw_dimension_customer",
    "city": "dw_dimension_city",
    "employee": "dw_dimension_employee",
    "date": "dw_dimension_date",
    "stock_groups": "oltp_warehouse_stockgroups",
    "stock_item_stock_groups": "oltp_warehouse_stockitemstockgroups",
}

# Gold column <- bronze source column.
MAPPINGS: dict[str, list[tuple[str, str]]] = {
    "fact_sale": [
        ("sale_key", "Sale Key"),
        ("invoice_date", "Invoice Date Key"),
        ("delivery_date", "Delivery Date Key"),
        ("city_key", "City Key"),
        ("customer_key", "Customer Key"),
        ("bill_to_customer_key", "Bill To Customer Key"),
        ("stock_item_key", "Stock Item Key"),
        ("salesperson_key", "Salesperson Key"),
        ("wwi_invoice_id", "WWI Invoice ID"),
        ("quantity", "Quantity"),
        ("unit_price", "Unit Price"),
        ("total_excluding_tax", "Total Excluding Tax"),
        ("tax_amount", "Tax Amount"),
        ("profit", "Profit"),
        ("total_including_tax", "Total Including Tax"),
    ],
    "fact_order": [
        ("order_key", "Order Key"),
        ("order_date", "Order Date Key"),
        ("city_key", "City Key"),
        ("customer_key", "Customer Key"),
        ("stock_item_key", "Stock Item Key"),
        ("salesperson_key", "Salesperson Key"),
        ("picker_key", "Picker Key"),
        ("wwi_order_id", "WWI Order ID"),
        ("wwi_backorder_id", "WWI Backorder ID"),
        ("quantity", "Quantity"),
        ("total_excluding_tax", "Total Excluding Tax"),
    ],
    "fact_stock_movement": [
        ("movement_key", "Movement Key"),
        ("movement_date", "Date Key"),
        ("stock_item_key", "Stock Item Key"),
        ("transaction_type_key", "Transaction Type Key"),
        ("quantity", "Quantity"),
    ],
    "stock_holding_current": [
        ("stock_item_key", "Stock Item Key"),
        ("quantity_on_hand", "Quantity On Hand"),
    ],
    "dim_stock_item": [
        ("stock_item_key", "Stock Item Key"),
        ("wwi_stock_item_id", "WWI Stock Item ID"),
        ("stock_item", "Stock Item"),
        ("brand", "Brand"),
        ("color", "Color"),
        ("size", "Size"),
        ("selling_package", "Selling Package"),
        ("is_chiller_stock", "Is Chiller Stock"),
        ("unit_price", "Unit Price"),
        ("valid_from", "Valid From"),
        ("valid_to", "Valid To"),
    ],
    "dim_customer": [
        ("customer_key", "Customer Key"),
        ("wwi_customer_id", "WWI Customer ID"),
        ("customer", "Customer"),
        ("bill_to_customer", "Bill To Customer"),
        ("category", "Category"),
        ("buying_group", "Buying Group"),
        ("valid_from", "Valid From"),
        ("valid_to", "Valid To"),
    ],
    "dim_city": [
        ("city_key", "City Key"),
        ("wwi_city_id", "WWI City ID"),
        ("city", "City"),
        ("state_province", "State Province"),
        ("country", "Country"),
        ("continent", "Continent"),
        ("sales_territory", "Sales Territory"),
        ("region", "Region"),
        ("subregion", "Subregion"),
        ("valid_from", "Valid From"),
        ("valid_to", "Valid To"),
    ],
    "dim_employee": [
        ("employee_key", "Employee Key"),
        ("wwi_employee_id", "WWI Employee ID"),
        ("employee", "Employee"),
        ("is_salesperson", "Is Salesperson"),
        ("valid_from", "Valid From"),
        ("valid_to", "Valid To"),
    ],
    "dim_stock_group": [
        ("stock_group_id", "StockGroupID"),
        ("stock_group_name", "StockGroupName"),
    ],
    "bridge_stock_item_group": [
        ("wwi_stock_item_id", "StockItemID"),
        ("stock_group_id", "StockGroupID"),
    ],
}

# SCD Type 2 open-ended rows carry [Valid To] = 9999-12-31 23:59:59.9999999.
OPEN_ENDED_FROM = "9999-12-31 00:00:00"

# SCD Type 2 tables: (surrogate key, durable key).
SCD2_KEYS = {
    "dim_stock_item": ("stock_item_key", "wwi_stock_item_id"),
    "dim_customer": ("customer_key", "wwi_customer_id"),
    "dim_city": ("city_key", "wwi_city_id"),
    "dim_employee": ("employee_key", "wwi_employee_id"),
}

BASIS_BACKCAST = "holding_backcast"
BASIS_FLOW = "flow_min_opening"


def _types(table: str) -> dict[str, str]:
    return {name: dtype for name, dtype, _ in WWI_TABLES[table].columns}


def conform(table: str, bronze: DataFrame) -> DataFrame:
    """Rename and cast a bronze table to its gold schema.

    SCD Type 2 tables get is_current: the open-ended row ([Valid To] = 9999-12-31) with the
    latest valid_from, ties broken by the highest surrogate key. The tie-break matters:
    [Dimension].[City] has 4,612 durable keys with two open-ended rows that share valid_from
    and every attribute; marking both current would fan out as-is attribution (SPEC § 5.3 rule 4).
    """
    types = _types(table)
    cols = [F.col(f"`{src}`").cast(types[gold]).alias(gold) for gold, src in MAPPINGS[table]]
    out = bronze.select(*cols)
    if table in SCD2_KEYS:
        surrogate, durable = SCD2_KEYS[table]
        open_ended = F.col("valid_to") >= F.to_timestamp(F.lit(OPEN_ENDED_FROM))
        latest = Window.partitionBy(durable, open_ended).orderBy(
            F.col("valid_from").desc(), F.col(surrogate).desc()
        )
        out = out.withColumn("is_current", open_ended & (F.row_number().over(latest) == 1))
    return out.select(*WWI_TABLES[table].column_names)


def fact_stock_holding_daily(
    movement: DataFrame,
    holding: DataFrame,
    stock_item: DataFrame,
    dates: DataFrame,
    window_start: str,
    window_end: str,
) -> DataFrame:
    """Dense daily stock snapshot per durable stock item (SPEC § 5.3 rule 6).

    Inputs are gold-conformed frames: fact_stock_movement, stock_holding_current,
    dim_stock_item and dim_date. For each item with a current holding:

    * cum(t)  = sum of movement quantity with movement_date <= t (all history)
    * B(t)    = QOH_current - (cum(+inf) - cum(t))            (holding back-cast)
    * if B(t) >= 0 for every t in the window: quantity_on_hand = B(t),
      balance_basis = 'holding_backcast'
    * else the movement history cannot be reconciled with the current holding:
      quantity_on_hand = O + cum(t), O = max(0, -min_t cum(t)),
      balance_basis = 'flow_min_opening'
    """
    item_versions = stock_item.select("stock_item_key", "wwi_stock_item_id", "valid_from", "valid_to")
    keyed = item_versions.select("stock_item_key", "wwi_stock_item_id")

    daily_net = (
        movement.join(keyed, "stock_item_key")
        .groupBy("wwi_stock_item_id", F.col("movement_date").alias("d"))
        .agg(F.sum(F.col("quantity").cast("bigint")).alias("net"))
    )
    totals = daily_net.groupBy("wwi_stock_item_id").agg(F.sum("net").alias("total_net"))
    before_window = (
        daily_net.where(F.col("d") < F.to_date(F.lit(window_start)))
        .groupBy("wwi_stock_item_id")
        .agg(F.sum("net").alias("pre_net"))
    )
    qoh = (
        holding.join(keyed, "stock_item_key")
        .groupBy("wwi_stock_item_id")
        .agg(F.sum(F.col("quantity_on_hand").cast("bigint")).alias("qoh"))
    )
    days = dates.where(
        F.col("date_key").between(F.to_date(F.lit(window_start)), F.to_date(F.lit(window_end)))
    ).select(F.col("date_key").alias("snapshot_date"))

    grid = (
        qoh.crossJoin(days)
        .join(daily_net.withColumnRenamed("d", "snapshot_date"), ["wwi_stock_item_id", "snapshot_date"], "left")
        .join(totals, "wwi_stock_item_id", "left")
        .join(before_window, "wwi_stock_item_id", "left")
        .fillna(0, subset=["net", "total_net", "pre_net"])
    )
    running = Window.partitionBy("wwi_stock_item_id").orderBy("snapshot_date").rowsBetween(
        Window.unboundedPreceding, Window.currentRow
    )
    per_item = Window.partitionBy("wwi_stock_item_id")
    balances = (
        grid.withColumn("cum", F.col("pre_net") + F.sum("net").over(running))
        .withColumn("backcast", F.col("qoh") - (F.col("total_net") - F.col("cum")))
        .withColumn("min_backcast", F.min("backcast").over(per_item))
        .withColumn("opening", F.greatest(F.lit(0), -F.min("cum").over(per_item)))
        .withColumn(
            "balance_basis",
            F.when(F.col("min_backcast") >= 0, F.lit(BASIS_BACKCAST)).otherwise(F.lit(BASIS_FLOW)),
        )
        .withColumn(
            "quantity_on_hand",
            F.when(F.col("balance_basis") == BASIS_BACKCAST, F.col("backcast"))
            .otherwise(F.col("opening") + F.col("cum"))
            .cast("int"),
        )
    )

    # stock_item_key = version valid at the start of snapshot_date, else the earliest version.
    snapshot_ts = F.to_timestamp(F.col("b.snapshot_date"))
    valid = (
        balances.alias("b")
        .join(
            item_versions.alias("v"),
            (F.col("b.wwi_stock_item_id") == F.col("v.wwi_stock_item_id"))
            & (F.col("v.valid_from") <= snapshot_ts)
            & (F.col("v.valid_to") > snapshot_ts),
            "left",
        )
        .select("b.*", F.col("v.stock_item_key").alias("valid_key"))
    )
    earliest = (
        item_versions.withColumn(
            "rn",
            F.row_number().over(
                Window.partitionBy("wwi_stock_item_id").orderBy("valid_from", "stock_item_key")
            ),
        )
        .where("rn = 1")
        .select("wwi_stock_item_id", F.col("stock_item_key").alias("earliest_key"))
    )
    return (
        valid.join(earliest, "wwi_stock_item_id", "left")
        .select(
            "snapshot_date",
            F.col("wwi_stock_item_id").cast("int").alias("wwi_stock_item_id"),
            F.coalesce("valid_key", "earliest_key").cast("int").alias("stock_item_key"),
            "quantity_on_hand",
            "balance_basis",
        )
    )
