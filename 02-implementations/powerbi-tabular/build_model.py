#!/usr/bin/env python3
"""Generate the S2 Power BI / Tabular semantic models as Fabric Git items (TMDL).

One definition per dataset (WWI, NYC) rendered in three storage-mode variants (SPEC § 3.1 S2):

  import       Azure Databricks connector (ADBC) in Import mode. NYC Trips carries an incremental refresh policy
               (24 monthly partitions) in hybrid mode: the newest day is a real-time DirectQuery partition.
  directlake   Direct Lake on OneLake over the Fabric mirrored Azure Databricks catalog. 'Stock Item (Current)'
               is an Import table (composite model), because a Direct Lake one-side column must be unique and
               the gold schema has no current-row table.
  directquery  DirectQuery over the Azure Databricks connector; dimensions are Dual.

Tables, columns, relationships, measures, roles and linguistic metadata are identical in all variants; only
partitions, shared expressions and storage modes differ. Agent metadata (descriptions, synonyms, formats) comes
from 01-spec/glossary.yaml. Output: models/<Model>.SemanticModel/{.platform, definition.pbism, definition/}.

    python build_model.py          # write models/
    python build_model.py --check  # exit 1 when committed files differ from the generator
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "models"
GLOSSARY = yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())
METRICS = {m["id"]: m for m in GLOSSARY["metrics"]}
DIMS = {d["name"]: d for ds in GLOSSARY["dimensions"].values() for d in ds}
NS = uuid.UUID("8f1c2a3e-5d4b-4c6a-9e7f-0a1b2c3d4e5f")  # lineage tags and logical ids are deterministic
COMPATIBILITY_LEVEL = 1604  # Direct Lake minimum (hybrid tables need 1565)
CATALOG = "slc"
# Environment bindings: committed as tokens, replaced per target environment by fabric-cicd (deploy/parameter.yml).
TOKENS = {
    "host": "SLC_DATABRICKS_HOST",
    "http_path": "SLC_DATABRICKS_HTTP_PATH",
    "onelake": "SLC_ONELAKE_SOURCE_URL",
}
MODES = ("import", "directlake", "directquery")
FORMATS = {
    "currency": "\\$#,0.00;(\\$#,0.00);\\$#,0.00",
    "units": "#,0",
    "count": "#,0",
    "ratio_pct": "0.00%;-0.00%;0.00%",
    "decimal_2": "#,0.00",
    "days": "#,0.0",
    "index": "0.000",
}
DATA_TYPES = {"int": "int64", "str": "string", "date": "dateTime", "dec": "decimal", "bool": "boolean", "ts": "dateTime"}


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def q(name: str) -> str:
    """TMDL object name, quoted when it contains a dot, equals, colon, quote or whitespace."""
    if any(c in name for c in ".=:' \t") or any(c in name for c in "()-%&/"):
        return "'" + name.replace("'", "''") + "'"
    return name


# --------------------------------------------------------------------------- model description


@dataclass
class Column:
    name: str
    source: str
    kind: str  # int | str | date | dec | bool | ts
    description: str = ""
    hidden: bool = False
    fmt: str | None = None
    sort_by: str | None = None
    key: bool = False
    data_category: str | None = None


@dataclass
class Measure:
    name: str
    expression: str
    description: str
    fmt: str
    folder: str
    hidden: bool = False
    metric_id: str | None = None
    synonyms: list[str] = field(default_factory=list)


@dataclass
class Hierarchy:
    name: str
    levels: list[str]


@dataclass
class Table:
    name: str
    schema: str
    entity: str
    columns: list[Column]
    description: str
    role: str  # fact | dim
    measures: list[Measure] = field(default_factory=list)
    hierarchies: list[Hierarchy] = field(default_factory=list)
    hidden: bool = False
    row_filter_m: str | None = None  # Power Query row filter (Import / DirectQuery / composite Import table)
    import_in_directlake: bool = False
    synonyms: list[str] = field(default_factory=list)
    date_table: bool = False


@dataclass
class Relationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    many_to_many: bool = False


@dataclass
class Role:
    name: str
    description: str
    filters: dict[str, str]
    entra_group: str


@dataclass
class Model:
    key: str
    display: str
    description: str
    tables: list[Table]
    relationships: list[Relationship]
    roles: list[Role]
    hybrid_table: str | None = None


def date_columns(prefix: str, role: str, date_name: str, with_fiscal: bool) -> list[Column]:
    p = f"{prefix} " if prefix else ""
    cols = [
        Column(date_name, "date_key", "date", f"Calendar date of the {role}.", fmt="yyyy-MM-dd", key=True),
        Column(f"{p}Calendar Year" if prefix else "Calendar Year", "calendar_year", "int", "Calendar year.", fmt="0"),
        Column(f"{p}Calendar Quarter" if prefix else "Calendar Quarter", "calendar_quarter", "int", "Calendar quarter 1-4.", fmt="0"),
        Column(f"{p}Calendar Month" if prefix else "Calendar Month", "calendar_month", "int", "Calendar month 1-12.", fmt="0"),
        Column(f"{p}Month Name" if prefix else "Month Name", "month_name", "str", "Month name.",
               sort_by=f"{p}Calendar Month" if prefix else "Calendar Month"),
        Column(f"{p}Month Start" if prefix else "Month Start", "month_start_date", "date", "First day of the calendar month.", fmt="yyyy-MM-dd"),
        Column(f"{p}Day of Month" if prefix else "Day of Month", "day_of_month", "int", "Day of the month.", fmt="0"),
        Column(f"{p}Day of Year" if prefix else "Day of Year", "day_of_year", "int", "Day of the year.", fmt="0"),
        Column(f"{p}Day of Week" if prefix else "Day of Week", "day_of_week", "int", "ISO day of week, Monday = 1.", fmt="0"),
        Column(f"{p}Day Name" if prefix else "Day Name", "day_name", "str", "Day name.",
               sort_by=f"{p}Day of Week" if prefix else "Day of Week"),
        Column(f"{p}ISO Week" if prefix else "ISO Week", "iso_week_number", "int", "ISO week number.", fmt="0"),
    ]
    if with_fiscal:
        cols += [
            Column("Fiscal Year", "fiscal_year", "int", "Fiscal year starting 1 November, labeled by the year in which it ends.", fmt="0"),
            Column("Fiscal Quarter", "fiscal_quarter", "int", "Fiscal quarter 1-4 (Q1 = November-January).", fmt="0"),
            Column("Fiscal Month", "fiscal_month", "int", "Fiscal month 1-12 (November = 1).", fmt="0"),
            Column("Fiscal Period", "fiscal_period_index", "int", "fiscal_year * 12 + fiscal_month; consecutive across years.", fmt="0", hidden=True),
            Column("Day of Fiscal Year", "day_of_fiscal_year", "int", "Day of the fiscal year.", fmt="0"),
        ]
    return cols


def meta(metric_id: str) -> tuple[str, str, list[str]]:
    m = METRICS[metric_id]
    return m["description"], FORMATS[m["format"]], m["synonyms"][:10]


def measure(name: str, expr: str, folder: str, metric_id: str | None = None, description: str | None = None,
            fmt: str | None = None, hidden: bool = False, synonyms: list[str] | None = None) -> Measure:
    if metric_id:
        d, f, s = meta(metric_id)
        return Measure(name, expr, description or d, fmt or f, folder, hidden, metric_id, synonyms if synonyms is not None else s)
    return Measure(name, expr, description or "", fmt or "#,0", folder, hidden, None, synonyms or [])


# --------------------------------------------------------------------------- WWI

SALES_NA = "ISCROSSFILTERED ( 'Picker' )"
ORDERS_NA = "ISCROSSFILTERED ( 'Delivery Date' ) || ISCROSSFILTERED ( 'Bill-To Customer' )"
STOCK_NA = ("ISCROSSFILTERED ( 'Delivery Date' ) || ISCROSSFILTERED ( 'Customer' ) || ISCROSSFILTERED ( 'Bill-To Customer' )"
            " || ISCROSSFILTERED ( 'City' ) || ISCROSSFILTERED ( 'Salesperson' ) || ISCROSSFILTERED ( 'Picker' )")


def guarded(guard: str, expr: str) -> str:
    return f"IF ( {guard}, BLANK (), {expr} )"


WWI_SALES_MEASURES = [
    measure("Revenue (Excl. Tax)", guarded(SALES_NA, "SUM ( Sales[total_excluding_tax] )"), "Sales", "W-S1"),
    measure("Revenue Including Tax", guarded(SALES_NA, "SUM ( Sales[total_including_tax] )"), "Sales", "B-W1"),
    measure("Gross Profit", guarded(SALES_NA, "SUM ( Sales[profit] )"), "Sales", "B-W2"),
    measure("Units Sold", guarded(SALES_NA, "SUM ( Sales[quantity] )"), "Sales", "B-W3"),
    measure("Invoice Count", guarded(SALES_NA, "DISTINCTCOUNT ( Sales[wwi_invoice_id] )"), "Sales", "B-W4"),
    measure("Gross Margin %", "DIVIDE ( [Gross Profit], [Revenue (Excl. Tax)] )", "Sales", "W-M1"),
    measure("Stock Group Revenue Share",
            "DIVIDE (\n    [Revenue (Excl. Tax)],\n    CALCULATE ( [Revenue (Excl. Tax)], REMOVEFILTERS ( 'Stock Group' ), "
            "REMOVEFILTERS ( 'Stock Item Group' ) )\n)", "Sales", "W-C1"),
]

WWI_ORDER_MEASURES = [
    measure("Ordered Quantity", guarded(ORDERS_NA, "SUM ( Orders[quantity] )"), "Orders", "W-S2"),
    measure("Backordered Order Lines",
            guarded(ORDERS_NA, "VAR n = COUNT ( Orders[wwi_backorder_id] ) RETURN IF ( n = 0, BLANK (), n )"), "Orders", "B-W5"),
]

WWI_STOCK_MEASURES = [
    measure("Snapshot Anchor Date",
            "CALCULATE (\n    MAX ( 'Stock Holding'[snapshot_date] ),\n    REMOVEFILTERS ( 'Stock Item' ),\n"
            "    REMOVEFILTERS ( 'Stock Item (Current)' ),\n    REMOVEFILTERS ( 'Stock Item Group' ),\n"
            "    REMOVEFILTERS ( 'Stock Group' )\n)", "Stock", hidden=True, fmt="yyyy-MM-dd",
            description="d* of SPEC W-M2: the last snapshot date in the period, over all stock items."),
    measure("Closing Stock On Hand",
            guarded(STOCK_NA, "VAR d = [Snapshot Anchor Date]\nRETURN\n    IF (\n        ISBLANK ( d ),\n        BLANK (),\n"
                    "        CALCULATE ( SUM ( 'Stock Holding'[quantity_on_hand] ), REMOVEFILTERS ( 'Date' ), 'Date'[Date] = d )\n    )"),
            "Stock", "W-M2"),
    measure("Units Sold 91D",
            guarded(STOCK_NA, "VAR d = [Snapshot Anchor Date]\nRETURN\n    IF (\n        ISBLANK ( d ),\n        BLANK (),\n"
                    "        CALCULATE (\n            SUM ( Sales[quantity] ),\n            REMOVEFILTERS ( 'Date' ),\n"
                    "            DATESBETWEEN ( 'Date'[Date], d - 90, d )\n        )\n    )"),
            "Stock", description="Units sold in the 91 days ending on the closing snapshot date (invoice dates t-90 to t), "
            "for the stock items and groups in context.", fmt=FORMATS["units"], synonyms=["trailing 91 day sales", "91 day units"]),
    measure("Days of Supply",
            "VAR oh = [Closing Stock On Hand]\nVAR u = [Units Sold 91D]\nRETURN IF ( ISBLANK ( oh ), BLANK (), DIVIDE ( oh * 91.0, u ) )",
            "Stock", "W-C2"),
]

WWI_TABLES = [
    Table("Date", "wwi", "dim_date", date_columns("", "invoice, order or stock snapshot", "Date", True),
          DIMS["date"]["description"], "dim",
          hierarchies=[Hierarchy("Calendar", ["Calendar Year", "Calendar Quarter", "Month Start", "Date"]),
                       Hierarchy("Fiscal", ["Fiscal Year", "Fiscal Quarter", "Fiscal Month", "Date"])],
          synonyms=DIMS["date"]["synonyms"], date_table=True),
    Table("Delivery Date", "wwi", "dim_date", [
        Column("Delivery Date", "date_key", "date", "Date the invoice line was delivered.", fmt="yyyy-MM-dd", key=True),
        Column("Delivery Year", "calendar_year", "int", "Calendar year of delivery.", fmt="0"),
        Column("Delivery Month", "calendar_month", "int", "Calendar month of delivery.", fmt="0"),
        Column("Delivery Month Start", "month_start_date", "date", "First day of the delivery month.", fmt="yyyy-MM-dd"),
    ], DIMS["delivery_date"]["description"], "dim", synonyms=DIMS["delivery_date"]["synonyms"]),
    Table("Customer", "wwi", "dim_customer", [
        Column("Customer Key", "customer_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("WWI Customer ID", "wwi_customer_id", "int", "Durable customer id.", fmt="0"),
        Column("Customer", "customer", "str", "Customer name as recorded at the time of sale."),
        Column("Customer Category", "category", "str", "Customer category as recorded at the time of sale."),
        Column("Buying Group", "buying_group", "str", "Buying group as recorded at the time of sale."),
    ], DIMS["customer"]["description"], "dim", synonyms=DIMS["customer"]["synonyms"]),
    Table("Bill-To Customer", "wwi", "dim_customer", [
        Column("Bill-To Customer Key", "customer_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("Bill-To Customer", "customer", "str", "Customer responsible for payment."),
        Column("Bill-To Category", "category", "str", "Category of the bill-to customer."),
    ], DIMS["bill_to_customer"]["description"], "dim", synonyms=DIMS["bill_to_customer"]["synonyms"]),
    Table("City", "wwi", "dim_city", [
        Column("City Key", "city_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("WWI City ID", "wwi_city_id", "int", "Durable city id.", fmt="0"),
        Column("City", "city", "str", "Delivery city as recorded at the time of sale."),
        Column("State Province", "state_province", "str", "State or province."),
        Column("Country", "country", "str", "Country."),
        Column("Continent", "continent", "str", "Continent."),
        Column("Sales Territory", "sales_territory", "str", "Sales territory (alternate hierarchy over State Province)."),
        Column("Region", "region", "str", "Region."),
        Column("Subregion", "subregion", "str", "Subregion."),
    ], DIMS["city"]["description"], "dim",
        hierarchies=[Hierarchy("Geography", ["Continent", "Country", "State Province", "City"]),
                     Hierarchy("Sales Territory Hierarchy", ["Sales Territory", "State Province", "City"])],
        synonyms=DIMS["city"]["synonyms"]),
    Table("Stock Item", "wwi", "dim_stock_item", [
        Column("Stock Item Key", "stock_item_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("WWI Stock Item ID", "wwi_stock_item_id", "int", "Durable stock item id.", fmt="0"),
        Column("Stock Item", "stock_item", "str", "Stock item name as recorded at the time of sale."),
        Column("Brand", "brand", "str", "Brand."),
        Column("Color", "color", "str", "Color as recorded at the time of sale (as-was)."),
        Column("Size", "size", "str", "Size."),
        Column("Selling Package", "selling_package", "str", "Selling package."),
        Column("Is Chiller Stock", "is_chiller_stock", "bool", "True for chiller (refrigerated) items."),
        Column("Unit Price", "unit_price", "dec", "List unit price of the version.", fmt=FORMATS["currency"]),
        Column("Valid From", "valid_from", "ts", "Version start.", fmt="yyyy-MM-dd HH:mm:ss"),
        Column("Valid To", "valid_to", "ts", "Version end.", fmt="yyyy-MM-dd HH:mm:ss"),
        Column("Is Current Version", "is_current", "bool", "True for the current version of the item."),
    ], DIMS["stock_item"]["description"], "dim", synonyms=DIMS["stock_item"]["synonyms"]),
    Table("Stock Item (Current)", "wwi", "dim_stock_item", [
        Column("Current WWI Stock Item ID", "wwi_stock_item_id", "int", "Durable stock item id.", fmt="0", key=True, hidden=True),
        Column("Current Stock Item", "stock_item", "str", "Stock item name in its current version (as-is)."),
        Column("Current Color", "color", "str", "Color in the item's current version (as-is)."),
        Column("Current Selling Package", "selling_package", "str", "Selling package in the item's current version (as-is)."),
        Column("Current Brand", "brand", "str", "Brand in the item's current version (as-is)."),
    ], "Current version of each stock item, for as-is attribution of facts recorded against older versions (SPEC § 5.3 rule 4).",
        "dim", row_filter_m="each [is_current] = true", import_in_directlake=True,
        synonyms=["current product", "item today", "as-is item"]),
    Table("Stock Group", "wwi", "dim_stock_group", [
        Column("Stock Group ID", "stock_group_id", "int", "Stock group id.", hidden=True, key=True),
        Column("Stock Group", "stock_group_name", "str", "Stock group name. Groups overlap: an item can belong to several."),
    ], DIMS["stock_group"]["description"], "dim", synonyms=DIMS["stock_group"]["synonyms"]),
    Table("Stock Item Group", "wwi", "bridge_stock_item_group", [
        Column("wwi_stock_item_id", "wwi_stock_item_id", "int", "Durable stock item id.", hidden=True),
        Column("stock_group_id", "stock_group_id", "int", "Stock group id.", hidden=True),
    ], "Bridge between stock items (durable id) and stock groups (many-to-many).", "dim", hidden=True),
    Table("Salesperson", "wwi", "dim_employee", [
        Column("Salesperson Key", "employee_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("Salesperson", "employee", "str", "Employee credited with the sale or order."),
    ], DIMS["salesperson"]["description"], "dim", synonyms=DIMS["salesperson"]["synonyms"]),
    Table("Picker", "wwi", "dim_employee", [
        Column("Picker Key", "employee_key", "int", "Surrogate key (SCD2 version).", hidden=True, key=True),
        Column("Picker", "employee", "str", "Employee who picked the order."),
    ], DIMS["picker"]["description"], "dim", synonyms=DIMS["picker"]["synonyms"]),
    Table("Sales", "wwi", "fact_sale", [
        Column("sale_key", "sale_key", "int", "Invoice line key.", hidden=True),
        Column("invoice_date", "invoice_date", "date", "Invoice date (relates to Date).", hidden=True, fmt="yyyy-MM-dd"),
        Column("delivery_date", "delivery_date", "date", "Delivery date; blank when undelivered.", hidden=True, fmt="yyyy-MM-dd"),
        Column("city_key", "city_key", "int", "City surrogate key.", hidden=True),
        Column("customer_key", "customer_key", "int", "Customer surrogate key.", hidden=True),
        Column("bill_to_customer_key", "bill_to_customer_key", "int", "Bill-to customer surrogate key.", hidden=True),
        Column("stock_item_key", "stock_item_key", "int", "Stock item surrogate key.", hidden=True),
        Column("salesperson_key", "salesperson_key", "int", "Salesperson surrogate key.", hidden=True),
        Column("wwi_invoice_id", "wwi_invoice_id", "int", "Invoice id.", hidden=True),
        Column("quantity", "quantity", "int", "Invoiced quantity.", hidden=True),
        Column("unit_price", "unit_price", "dec", "Unit price.", hidden=True),
        Column("total_excluding_tax", "total_excluding_tax", "dec", "Line total excluding tax.", hidden=True),
        Column("tax_amount", "tax_amount", "dec", "Tax amount.", hidden=True),
        Column("profit", "profit", "dec", "Line profit.", hidden=True),
        Column("total_including_tax", "total_including_tax", "dec", "Line total including tax.", hidden=True),
    ], "WideWorldImporters invoice lines (fact_sale), dated by invoice date.", "fact", measures=WWI_SALES_MEASURES,
        synonyms=["sales", "invoices", "invoice lines"]),
    Table("Orders", "wwi", "fact_order", [
        Column("order_key", "order_key", "int", "Order line key.", hidden=True),
        Column("order_date", "order_date", "date", "Order date (relates to Date).", hidden=True, fmt="yyyy-MM-dd"),
        Column("city_key", "city_key", "int", "City surrogate key.", hidden=True),
        Column("customer_key", "customer_key", "int", "Customer surrogate key.", hidden=True),
        Column("stock_item_key", "stock_item_key", "int", "Stock item surrogate key.", hidden=True),
        Column("salesperson_key", "salesperson_key", "int", "Salesperson surrogate key.", hidden=True),
        Column("picker_key", "picker_key", "int", "Picker surrogate key; blank when not picked.", hidden=True),
        Column("wwi_order_id", "wwi_order_id", "int", "Order id.", hidden=True),
        Column("wwi_backorder_id", "wwi_backorder_id", "int", "Backorder id; blank when the line is not backordered.", hidden=True),
        Column("quantity", "quantity", "int", "Ordered quantity.", hidden=True),
        Column("total_excluding_tax", "total_excluding_tax", "dec", "Order line total excluding tax.", hidden=True),
    ], "WideWorldImporters order lines (fact_order), dated by order date.", "fact", measures=WWI_ORDER_MEASURES,
        synonyms=["orders", "order lines"]),
    Table("Stock Holding", "wwi", "fact_stock_holding_daily", [
        Column("snapshot_date", "snapshot_date", "date", "Snapshot date (relates to Date).", hidden=True, fmt="yyyy-MM-dd"),
        Column("wwi_stock_item_id", "wwi_stock_item_id", "int", "Durable stock item id.", hidden=True),
        Column("stock_item_key", "stock_item_key", "int", "Stock item version valid on the snapshot date.", hidden=True),
        Column("quantity_on_hand", "quantity_on_hand", "int", "Units on hand at end of day.", hidden=True),
        Column("Balance Basis", "balance_basis", "str", "holding_backcast or flow_min_opening (SPEC § 5.3 rule 6)."),
    ], "Daily stock on hand per stock item (derived snapshot). Semi-additive: sum across items, last value across time.",
        "fact", measures=WWI_STOCK_MEASURES, synonyms=["stock", "inventory", "stock on hand"]),
]

WWI_RELATIONSHIPS = [
    Relationship("Sales", "invoice_date", "Date", "Date"),
    Relationship("Sales", "delivery_date", "Delivery Date", "Delivery Date"),
    Relationship("Sales", "customer_key", "Customer", "Customer Key"),
    Relationship("Sales", "bill_to_customer_key", "Bill-To Customer", "Bill-To Customer Key"),
    Relationship("Sales", "city_key", "City", "City Key"),
    Relationship("Sales", "stock_item_key", "Stock Item", "Stock Item Key"),
    Relationship("Sales", "salesperson_key", "Salesperson", "Salesperson Key"),
    Relationship("Orders", "order_date", "Date", "Date"),
    Relationship("Orders", "customer_key", "Customer", "Customer Key"),
    Relationship("Orders", "city_key", "City", "City Key"),
    Relationship("Orders", "stock_item_key", "Stock Item", "Stock Item Key"),
    Relationship("Orders", "salesperson_key", "Salesperson", "Salesperson Key"),
    Relationship("Orders", "picker_key", "Picker", "Picker Key"),
    Relationship("Stock Holding", "snapshot_date", "Date", "Date"),
    Relationship("Stock Holding", "stock_item_key", "Stock Item", "Stock Item Key"),
    Relationship("Stock Item", "WWI Stock Item ID", "Stock Item (Current)", "Current WWI Stock Item ID"),
    # Many-to-many on the durable item id, filtered by the bridge only: a group selection becomes a set of items,
    # so totals across groups are deduplicated by construction (W-C1).
    Relationship("Stock Item", "WWI Stock Item ID", "Stock Item Group", "wwi_stock_item_id", many_to_many=True),
    Relationship("Stock Item Group", "stock_group_id", "Stock Group", "Stock Group ID"),
]

WWI_ROLES = [
    Role("Territory Analyst - Southeast",
         "SPEC § 10: sales and order rows restricted to cities in the Southeast sales territory (as-was city); no inventory access.",
         {"City": "'City'[Sales Territory] = \"Southeast\"", "Stock Holding": "FALSE ()"}, "slc_territory_southeast"),
]

# --------------------------------------------------------------------------- NYC

NYC_CAP = "DATE ( 2024, 12, 31 )"
TI_NA = "ISCROSSFILTERED ( 'Dropoff Date' )"


def ti(expr: str) -> str:
    return f"IF (\n    {TI_NA},\n    BLANK (),\n    VAR t = [Pickup Anchor Date]\n    RETURN\n        IF ( ISBLANK ( t ), BLANK (), {expr} )\n)"


NYC_MEASURES = [
    measure("Trip Count", "COUNTROWS ( Trips )", "Trips", "B-N1"),
    measure("Total Trip Distance", "SUM ( Trips[trip_distance] )", "Trips", "B-N2"),
    measure("Fare Amount", "SUM ( Trips[fare_amount] )", "Trips", "B-N3"),
    measure("Tip Amount (All Payment Types)", "SUM ( Trips[tip_amount] )", "Trips", "B-N4"),
    measure("Tolls Amount", "SUM ( Trips[tolls_amount] )", "Trips", "B-N5"),
    measure("Gross Trip Revenue", "SUM ( Trips[total_amount] )", "Trips", "N-S1"),
    measure("Card Tips", "CALCULATE ( SUM ( Trips[tip_amount] ), KEEPFILTERS ( Trips[payment_type] = 1 ) )", "Trips", "N-S2"),
    measure("Distinct OD Pairs", "DISTINCTCOUNT ( Trips[od_pair_id] )", "Trips", "N-M1"),
    measure("Fare per Mile", "DIVIDE ( [Fare Amount], [Total Trip Distance] )", "Trips", "N-M2"),
    measure("Pickup Anchor Date",
            f"VAR lo = MIN ( 'Pickup Date'[Pickup Date] )\nVAR hi = MAX ( 'Pickup Date'[Pickup Date] )\n"
            f"VAR t = MIN ( hi, {NYC_CAP} )\nRETURN IF ( ISBLANK ( hi ) || t < lo, BLANK (), t )",
            "Time Intelligence", hidden=True, fmt="yyyy-MM-dd",
            description="t(P) of SPEC § 6.1: the last calendar date of the pickup period in context, capped at 2024-12-31."),
    measure("Revenue YTD",
            ti("CALCULATE ( [Gross Trip Revenue], REMOVEFILTERS ( 'Pickup Date' ), "
               "DATESBETWEEN ( 'Pickup Date'[Pickup Date], DATE ( YEAR ( t ), 1, 1 ), t ) )"),
            "Time Intelligence", "N-C1", description="Gross Trip Revenue from 1 January of the anchor year to the anchor date "
            "(last calendar day of the pickup period, capped at 2024-12-31).", synonyms=["year to date revenue", "YTD revenue"]),
    measure("Revenue STLY YTD",
            ti("CALCULATE ( [Gross Trip Revenue], REMOVEFILTERS ( 'Pickup Date' ), "
               "DATESBETWEEN ( 'Pickup Date'[Pickup Date], DATE ( YEAR ( t ) - 1, 1, 1 ), EDATE ( t, -12 ) ) )"),
            "Time Intelligence", description="Revenue YTD for the same period one year earlier; 29 February maps to 28 February.",
            fmt=FORMATS["currency"], synonyms=["STLY revenue", "last year YTD", "prior year to date revenue", "same time last year"]),
    measure("Revenue YoY % vs STLY",
            "VAR y = [Revenue YTD]\nVAR s = [Revenue STLY YTD]\nRETURN IF ( ISBLANK ( y ) || ISBLANK ( s ), BLANK (), DIVIDE ( y - s, s ) )",
            "Time Intelligence", description="(Revenue YTD - Revenue STLY YTD) / Revenue STLY YTD; blank for 2023 anchors.",
            fmt=FORMATS["ratio_pct"], synonyms=["YoY growth", "year over year", "growth vs last year"]),
    measure("Trips MTD",
            ti("CALCULATE ( [Trip Count], REMOVEFILTERS ( 'Pickup Date' ), "
               "DATESBETWEEN ( 'Pickup Date'[Pickup Date], DATE ( YEAR ( t ), MONTH ( t ), 1 ), t ) )"),
            "Time Intelligence", description="Trips from the first day of the anchor month to the anchor date.",
            fmt=FORMATS["count"], synonyms=["month to date trips"]),
    measure("Trips YTD",
            ti("CALCULATE ( [Trip Count], REMOVEFILTERS ( 'Pickup Date' ), "
               "DATESBETWEEN ( 'Pickup Date'[Pickup Date], DATE ( YEAR ( t ), 1, 1 ), t ) )"),
            "Time Intelligence", description="Trips from 1 January of the anchor year to the anchor date.",
            fmt=FORMATS["count"], synonyms=["year to date trips"]),
    measure("Days Elapsed in Month", ti("DAY ( t )"), "Time Intelligence",
            description="Calendar days elapsed in the anchor month (day of month of the anchor date).", fmt="0"),
    measure("Days Elapsed in Year", ti("INT ( t - DATE ( YEAR ( t ), 1, 1 ) ) + 1"), "Time Intelligence",
            description="Calendar days elapsed in the anchor year (day of year of the anchor date).", fmt="0"),
    measure("MTD-to-YTD Daily Pace Index",
            "VAR m = [Trips MTD]\nVAR y = [Trips YTD]\nRETURN\n    IF (\n        ISBLANK ( y ),\n        BLANK (),\n"
            "        DIVIDE ( DIVIDE ( m + 0, [Days Elapsed in Month] ), DIVIDE ( y, [Days Elapsed in Year] ) )\n    )",
            "Time Intelligence", "N-C2"),
]


def zone_columns(role: str) -> list[Column]:
    return [
        Column(f"{role} Location ID", "location_id", "int", f"TLC location id of the {role.lower()} zone.", fmt="0", key=True),
        Column(f"{role} Borough", "borough", "str", f"Borough of the {role.lower()} zone."),
        Column(f"{role} Zone", "zone", "str", f"TLC taxi zone of the {role.lower()}."),
        Column(f"{role} Service Zone", "service_zone", "str", f"TLC service zone of the {role.lower()} (Yellow Zone, Boro Zone, Airports, EWR)."),
    ]


def nyc_date_columns(role: str) -> list[Column]:
    cols = date_columns(role, f"trip {role.lower()}", f"{role} Date", False)
    return cols


NYC_TABLES = [
    Table("Pickup Date", "nyctaxi", "dim_date", nyc_date_columns("Pickup"), DIMS["pickup_date"]["description"], "dim",
          hierarchies=[Hierarchy("Pickup Calendar", ["Pickup Calendar Year", "Pickup Calendar Quarter", "Pickup Month Start", "Pickup Date"])],
          synonyms=DIMS["pickup_date"]["synonyms"], date_table=True),
    Table("Dropoff Date", "nyctaxi", "dim_date", nyc_date_columns("Dropoff"), DIMS["dropoff_date"]["description"], "dim",
          synonyms=DIMS["dropoff_date"]["synonyms"]),
    Table("Pickup Zone", "nyctaxi", "dim_zone", zone_columns("Pickup"), DIMS["pickup_zone"]["description"], "dim",
          hierarchies=[Hierarchy("Pickup Geography", ["Pickup Borough", "Pickup Zone"])],
          synonyms=[s for s in DIMS["pickup_zone"]["synonyms"] if s != "pickup borough"]),
    Table("Dropoff Zone", "nyctaxi", "dim_zone", zone_columns("Dropoff"), DIMS["dropoff_zone"]["description"], "dim",
          hierarchies=[Hierarchy("Dropoff Geography", ["Dropoff Borough", "Dropoff Zone"])],
          synonyms=[s for s in DIMS["dropoff_zone"]["synonyms"] if s != "dropoff borough"]),
    Table("Payment Type", "nyctaxi", "dim_payment_type", [
        Column("Payment Type", "payment_type", "int", "TLC payment type code.", fmt="0", key=True),
        Column("Payment Type Name", "payment_type_name", "str", DIMS["payment_type"]["description"]),
    ], DIMS["payment_type"]["description"], "dim", synonyms=DIMS["payment_type"]["synonyms"]),
    Table("Trips", "nyctaxi", "fact_trip", [
        Column("trip_id", "trip_id", "int", "Deterministic trip surrogate.", hidden=True),
        Column("Vendor ID", "vendor_id", "int", DIMS["vendor"]["description"], fmt="0"),
        Column("pickup_ts", "pickup_ts", "ts", "Pickup timestamp (incremental refresh column).", hidden=True, fmt="yyyy-MM-dd HH:mm:ss"),
        Column("dropoff_ts", "dropoff_ts", "ts", "Dropoff timestamp.", hidden=True, fmt="yyyy-MM-dd HH:mm:ss"),
        Column("pickup_date", "pickup_date", "date", "Pickup date (relates to Pickup Date).", hidden=True, fmt="yyyy-MM-dd"),
        Column("dropoff_date", "dropoff_date", "date", "Dropoff date (relates to Dropoff Date).", hidden=True, fmt="yyyy-MM-dd"),
        Column("Pickup Hour", "pickup_hour", "int", DIMS["pickup_hour"]["description"], fmt="0"),
        Column("pu_location_id", "pu_location_id", "int", "Pickup location id.", hidden=True),
        Column("do_location_id", "do_location_id", "int", "Dropoff location id.", hidden=True),
        Column("od_pair_id", "od_pair_id", "int", "pu_location_id * 1000 + do_location_id.", hidden=True),
        Column("passenger_count", "passenger_count", "int", "Passenger count (NULL for payment type 0).", hidden=True),
        Column("trip_distance", "trip_distance", "dec", "Trip distance in miles.", hidden=True),
        Column("payment_type", "payment_type", "int", "Payment type code.", hidden=True),
        Column("fare_amount", "fare_amount", "dec", "Metered fare.", hidden=True),
        Column("tip_amount", "tip_amount", "dec", "Tip amount.", hidden=True),
        Column("tolls_amount", "tolls_amount", "dec", "Tolls.", hidden=True),
        Column("total_amount", "total_amount", "dec", "Total amount charged.", hidden=True),
    ], "NYC Yellow Taxi valid trips, 2023-2024 pickups (fact_trip).", "fact", measures=NYC_MEASURES,
        synonyms=["trips", "rides", "taxi trips"]),
]

NYC_RELATIONSHIPS = [
    Relationship("Trips", "pickup_date", "Pickup Date", "Pickup Date"),
    Relationship("Trips", "dropoff_date", "Dropoff Date", "Dropoff Date"),
    Relationship("Trips", "pu_location_id", "Pickup Zone", "Pickup Location ID"),
    Relationship("Trips", "do_location_id", "Dropoff Zone", "Dropoff Location ID"),
    Relationship("Trips", "payment_type", "Payment Type", "Payment Type"),
]

NYC_ROLES = [
    Role("Manhattan Pickup Analyst",
         "SPEC § 10: trips restricted to pickups in Manhattan; the Dropoff Zone role stays unrestricted for browsing.",
         {"Pickup Zone": "'Pickup Zone'[Pickup Borough] = \"Manhattan\""}, "slc_pickup_manhattan"),
]

MODELS = [
    Model("WWI", "SLC WWI", "WideWorldImporters semantic model of the semantic layer comparison study (SPEC § 3.1 S2).",
          WWI_TABLES, WWI_RELATIONSHIPS, WWI_ROLES),
    Model("NYC", "SLC NYC", "NYC Yellow Taxi semantic model of the semantic layer comparison study (SPEC § 3.1 S2).",
          NYC_TABLES, NYC_RELATIONSHIPS, NYC_ROLES, hybrid_table="Trips"),
]

# --------------------------------------------------------------------------- rendering


def desc(text: str, indent: str) -> list[str]:
    return [f"{indent}/// {line}" for line in text.splitlines() if line] if text else []


def expr_block(expr: str, indent: str) -> list[str]:
    return [f"{indent}{line}" if line.strip() else "" for line in expr.splitlines()]


def m_source(table: Table, mode: str, model: Model) -> str:
    steps = [
        "let",
        "    Source = Databricks.Catalogs(DatabricksHost, DatabricksHttpPath, "
        "[Catalog = null, Database = null, EnableAutomaticProxyDiscovery = null, Implementation = \"2.0\"]),",
        f"    CatalogData = Source{{[Name = UnityCatalog, Kind = \"Database\"]}}[Data],",
        f"    SchemaData = CatalogData{{[Name = \"{table.schema}\", Kind = \"Schema\"]}}[Data],",
        f"    TableData = SchemaData{{[Name = \"{table.entity}\", Kind = \"Table\"]}}[Data],",
    ]
    last = "TableData"
    if table.row_filter_m:
        steps.append(f"    Filtered = Table.SelectRows({last}, {table.row_filter_m}),")
        last = "Filtered"
    if model.hybrid_table == table.name and mode == "import":
        steps.append(f"    Incremental = Table.SelectRows({last}, each [pickup_ts] >= RangeStart and [pickup_ts] < RangeEnd),")
        last = "Incremental"
    cols = ", ".join(f'"{c}"' for c in dict.fromkeys(col.source for col in table.columns))
    steps.append(f"    Selected = Table.SelectColumns({last}, {{{cols}}})")
    steps += ["in", "    Selected"]
    return "\n".join(steps)


def storage(table: Table, mode: str, model: Model) -> str:
    if mode == "import":
        # Tables related to a hybrid table are Dual, so queries that reach its real-time partition stay single-source.
        return "dual" if model.hybrid_table and table.role == "dim" else "import"
    if mode == "directquery":
        return "dual" if table.role == "dim" else "directQuery"
    return "import" if table.import_in_directlake else "directLake"


def render_table(model: Model, table: Table, mode: str) -> str:
    t = table.name
    lines = desc(table.description, "")
    lines.append(f"table {q(t)}")
    if table.hidden:
        lines.append("\tisHidden")
    if table.date_table:
        lines.append("\tdataCategory: Time")
    lines.append(f"\tlineageTag: {tag(model.key, t)}")
    lines.append("")
    for m in table.measures:
        lines += desc(m.description, "\t")
        body = m.expression
        if "\n" in body:
            lines.append(f"\tmeasure {q(m.name)} =")
            lines += expr_block(body, "\t\t\t")
        else:
            lines.append(f"\tmeasure {q(m.name)} = {body}")
        lines.append(f"\t\tformatString: {m.fmt}")
        lines.append(f"\t\tdisplayFolder: {m.folder}")
        if m.hidden:
            lines.append("\t\tisHidden")
        lines.append(f"\t\tlineageTag: {tag(model.key, t, 'measure', m.name)}")
        if m.metric_id:
            lines.append(f"\t\tannotation SLC_MetricId = {m.metric_id}")
        lines.append("")
    for c in table.columns:
        lines += desc(c.description, "\t")
        lines.append(f"\tcolumn {q(c.name)}")
        lines.append(f"\t\tdataType: {DATA_TYPES[c.kind]}")
        if c.key and (table.date_table or table.role == "dim"):
            lines.append("\t\tisKey")
        if c.hidden:
            lines.append("\t\tisHidden")
        if c.fmt:
            lines.append(f"\t\tformatString: {c.fmt}")
        lines.append(f"\t\tlineageTag: {tag(model.key, t, 'column', c.name)}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {c.source}")
        if c.sort_by:
            lines.append(f"\t\tsortByColumn: {q(c.sort_by)}")
        lines.append("")
    for h in table.hierarchies:
        lines.append(f"\thierarchy {q(h.name)}")
        lines.append(f"\t\tlineageTag: {tag(model.key, t, 'hierarchy', h.name)}")
        lines.append("")
        for level in h.levels:
            lines.append(f"\t\tlevel {q(level)}")
            lines.append(f"\t\t\tlineageTag: {tag(model.key, t, 'hierarchy', h.name, level)}")
            lines.append(f"\t\t\tcolumn: {q(level)}")
            lines.append("")
    if model.hybrid_table == t and mode == "import":
        lines.append("\trefreshPolicy")
        lines.append("\t\tpolicyType: basic")
        lines.append("\t\trollingWindowGranularity: month")
        lines.append("\t\trollingWindowPeriods: 24")
        lines.append("\t\tincrementalGranularity: day")
        lines.append("\t\tincrementalPeriods: 3")
        lines.append("\t\tmode: hybrid")
        lines.append("\t\tsourceExpression =")
        lines += expr_block(m_source(table, mode, model), "\t\t\t\t")
        lines.append("")
    smode = storage(table, mode, model)
    if smode == "directLake":
        lines.append(f"\tpartition {q(t)} = entity")
        lines.append("\t\tmode: directLake")
        lines.append("\t\tsource")
        lines.append(f"\t\t\tentityName: {table.entity}")
        lines.append(f"\t\t\tschemaName: {table.schema}")
        lines.append("\t\t\texpressionSource: 'DirectLake - slc'")
    else:
        lines.append(f"\tpartition {q(t)} = m")
        lines.append(f"\t\tmode: {smode}")
        lines.append("\t\tsource =")
        lines += expr_block(m_source(table, mode, model), "\t\t\t\t")
    lines.append("")
    if table.synonyms:
        lines.append(f"\tannotation SLC_Synonyms = {json.dumps(table.synonyms[:10])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_relationships(model: Model) -> str:
    lines = []
    for r in model.relationships:
        lines.append(f"relationship {tag(model.key, 'rel', r.from_table, r.from_column, r.to_table, r.to_column)}")
        if r.many_to_many:
            lines.append("\tfromCardinality: many")
            lines.append("\ttoCardinality: many")
            lines.append("\tcrossFilteringBehavior: oneDirection")
        lines.append(f"\tfromColumn: {q(r.from_table)}.{q(r.from_column)}")
        lines.append(f"\ttoColumn: {q(r.to_table)}.{q(r.to_column)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_expressions(model: Model, mode: str) -> str:
    def param(name: str, value: str, kind: str = "Text") -> str:
        return (f"expression {name} = {value} meta [IsParameterQuery = true, Type = \"{kind}\", IsParameterQueryRequired = true]\n"
                f"\tlineageTag: {tag(model.key, 'expression', name)}\n")

    parts = []
    if mode != "directlake" or any(t.import_in_directlake for t in model.tables):
        parts += [
            param("DatabricksHost", f'"{TOKENS["host"]}"'),
            param("DatabricksHttpPath", f'"{TOKENS["http_path"]}"'),
            param("UnityCatalog", f'"{CATALOG}"'),
        ]
    if mode == "import" and model.hybrid_table:
        parts += [
            param("RangeStart", "#datetime(2024, 12, 1, 0, 0, 0)", "DateTime"),
            param("RangeEnd", "#datetime(2025, 1, 1, 0, 0, 0)", "DateTime"),
        ]
    if mode == "directlake":
        parts += [
            param("OneLakeSourceUrl", f'"{TOKENS["onelake"]}"'),
            "expression 'DirectLake - slc' =\n\t\tlet\n\t\t    Source = AzureStorage.DataLake(OneLakeSourceUrl, [HierarchicalNavigation = true])\n"
            "\t\tin\n\t\t    Source\n"
            f"\tlineageTag: {tag(model.key, 'expression', 'DirectLake - slc')}\n",
        ]
    return "\n".join(parts)


def render_roles(model: Model) -> dict[str, str]:
    out = {}
    for r in model.roles:
        lines = desc(r.description + f" Members: Microsoft Entra group {r.entra_group} (assigned in the service).", "")
        lines.append(f"role {q(r.name)}")
        lines.append("\tmodelPermission: read")
        lines.append("")
        for table, expr in r.filters.items():
            lines.append(f"\ttablePermission {q(table)} = {expr}")
            lines.append("")
        lines.append(f"\tannotation SLC_EntraGroup = {r.entra_group}")
        out[r.name] = "\n".join(lines).rstrip() + "\n"
    return out


def linguistic(model: Model) -> str:
    entities: dict[str, dict] = {}

    def key(*parts: str) -> str:
        return ".".join(p.lower().replace(" ", "_") for p in parts)

    def entry(binding: dict, terms: list[str]) -> dict:
        return {"Definition": {"Binding": binding}, "State": "Generated",
                "Terms": [{t: {"State": "Authored"}} for t in terms[:10]]}

    for t in model.tables:
        if t.hidden:
            continue
        if t.synonyms:
            entities[key(t.name)] = entry({"ConceptualEntity": t.name}, [t.name.lower()] + t.synonyms[:9])
        for m in t.measures:
            if m.synonyms and not m.hidden:
                entities[key(t.name, m.name)] = entry({"ConceptualEntity": t.name, "ConceptualProperty": m.name},
                                                      [m.name.lower()] + m.synonyms[:9])
    doc = {"Version": "1.0.0", "Language": "en-US", "Entities": entities}
    body = json.dumps(doc, indent=2, sort_keys=True)
    return ("cultureInfo en-US\n\n\tlinguisticMetadata =\n" + "\n".join(f"\t\t\t{l}" for l in body.splitlines())
            + "\n\t\tcontentType: json\n")


def render_model(model: Model, mode: str) -> dict[str, str]:
    name = f"SLC_{model.key}_{ {'import': 'Import', 'directlake': 'DirectLake', 'directquery': 'DirectQuery'}[mode] }".replace(" ", "")
    root = f"{name}.SemanticModel"
    files: dict[str, str] = {}
    files[f"{root}/.platform"] = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": name,
                     "description": f"{model.description} Storage mode variant: {mode}."},
        "config": {"version": "2.0", "logicalId": tag(model.key, mode, "logicalId")},
    }, indent=2) + "\n"
    files[f"{root}/definition.pbism"] = json.dumps({"version": "4.2", "settings": {}}, indent=2) + "\n"
    d = f"{root}/definition"
    files[f"{d}/database.tmdl"] = f"database {name}\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n"
    model_lines = desc(model.description, "") + [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "",
        f"\tannotation SLC_StorageVariant = {mode}",
        "",
    ]
    model_lines += [f"ref table {q(t.name)}" for t in model.tables]
    model_lines += [""] + [f"ref role {q(r.name)}" for r in model.roles]
    model_lines += ["", "ref cultureInfo en-US"]
    files[f"{d}/model.tmdl"] = "\n".join(model_lines) + "\n"
    files[f"{d}/relationships.tmdl"] = render_relationships(model)
    files[f"{d}/expressions.tmdl"] = render_expressions(model, mode)
    for t in model.tables:
        files[f"{d}/tables/{t.name}.tmdl"] = render_table(model, t, mode)
    for role, text in render_roles(model).items():
        files[f"{d}/roles/{role}.tmdl"] = text
    files[f"{d}/cultures/en-US.tmdl"] = linguistic(model)
    return files


def outputs() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for model in MODELS:
        for mode in MODES:
            for rel, text in render_model(model, mode).items():
                out[OUT / rel] = text
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = outputs()
    if args.check:
        stale = [str(p.relative_to(HERE)) for p, t in files.items() if not p.exists() or p.read_text() != t]
        existing = {p for p in OUT.rglob("*") if p.is_file()} if OUT.exists() else set()
        stale += [str(p.relative_to(HERE)) for p in existing - set(files)]
        if stale:
            print(f"stale generated files: {stale}")
            sys.exit(1)
        return
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


if __name__ == "__main__":
    main()
