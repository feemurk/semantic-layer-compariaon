#!/usr/bin/env python3
"""Single source of the S1 SSAS Multidimensional model (SPEC § 3.1 S1).

Reads the definitions below, dsv/*.sql, mdx/*.mdx and 01-spec/glossary.yaml, and writes:

- model/          SSDT-style ASSL object files: slc.database, slc.ds, slc.dsv, <dimension>.dim, <cube>.cube, <role>.role
- deploy/slc.xmla one XMLA Create command holding the full database (deployed with Invoke-ASCmd)
- deploy/process_full.xmla  ProcessFull of the database
- adapter/02_external_tables.sql  SQL Server 2025 PolyBase external tables over the Databricks gold tables,
                                  generated from the canonical schema (01-spec/oracle/fixtures/schema.json)

XMLA Create reference: https://learn.microsoft.com/en-us/analysis-services/xmla/xml-elements-commands/create-element-xmla
(checked 2026-11-20). Edit this file, dsv/*.sql or mdx/*.mdx; never the generated files. `python3 build_model.py --check` exits 1 when a generated file is stale.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GLOSSARY = yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())
CANONICAL = json.loads((REPO / "01-spec" / "oracle" / "fixtures" / "schema.json").read_text())

DATABASE = "slc"
DATA_SOURCE = "slc_adapter"
DSV = "slc"
ADAPTER_SERVER = "slc-sql2025"
ADAPTER_DATABASE = "slc_adapter"
NS = "http://schemas.microsoft.com/analysisservices/2003/engine"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
XS = "http://www.w3.org/2001/XMLSchema"
MSDATA = "urn:schemas-microsoft-com:xml-msdata"
MSPROP = "urn:schemas-microsoft-com:xml-msprop"
for prefix, uri in (("", NS), ("xsi", XSI), ("xs", XS), ("msdata", MSDATA), ("msprop", MSPROP)):
    ET.register_namespace(prefix, uri)

NYC_FIRST_MONTH = (2023, 1)
NYC_LAST_MONTH = (2024, 12)

# --------------------------------------------------------------------------- DSV

# Column types of each named query: i16, i32, i64, u8 (tinyint), str, cur (2-decimal money or distance).
DSV_TABLES: dict[str, dict[str, str]] = {
    "wwi_date": {
        "date_id": "i32", "date_name": "str", "month_id": "i32", "month_name": "str", "month_end_name": "str",
        "month_of_year": "u8", "month_of_year_name": "str", "quarter_id": "i32", "quarter_name": "str",
        "quarter_end_name": "str", "quarter_of_year": "u8", "quarter_of_year_name": "str", "calendar_year": "i16",
        "calendar_year_name": "str", "fiscal_month_id": "i32", "fiscal_month_name": "str",
        "fiscal_month_of_year": "u8", "fiscal_month_of_year_name": "str", "fiscal_quarter_id": "i32",
        "fiscal_quarter_name": "str", "fiscal_quarter_of_year": "u8", "fiscal_quarter_of_year_name": "str",
        "fiscal_year": "i16", "fiscal_year_name": "str",
    },
    "wwi_customer": {"customer_key": "i32", "customer": "str", "category": "str", "buying_group": "str"},
    "wwi_city": {"city_key": "i32", "city": "str", "state_province": "str", "country": "str", "continent": "str",
                 "sales_territory": "str"},
    "wwi_stock_item": {
        "stock_item_key": "i32", "wwi_stock_item_id": "i32", "wwi_stock_item_id_name": "str", "stock_item": "str",
        "color": "str", "current_color": "str", "brand": "str", "size": "str", "selling_package": "str",
        "is_chiller_stock": "str", "balance_basis": "str",
    },
    "wwi_stock_group": {"stock_group_id": "i32", "stock_group_name": "str"},
    "wwi_employee": {"employee_key": "i32", "employee": "str"},
    "wwi_inventory_access": {"access_key": "i32", "access_name": "str"},
    "wwi_sales": {
        "sale_key": "i64", "invoice_date_id": "i32", "delivery_date_id": "i32", "customer_key": "i32",
        "bill_to_customer_key": "i32", "city_key": "i32", "stock_item_key": "i32", "salesperson_key": "i32",
        "wwi_invoice_id": "i32", "quantity": "i32", "total_excluding_tax": "cur", "total_including_tax": "cur",
        "profit": "cur",
    },
    "wwi_orders": {
        "order_key": "i64", "order_date_id": "i32", "customer_key": "i32", "city_key": "i32", "stock_item_key": "i32",
        "salesperson_key": "i32", "picker_key": "i32", "quantity": "i32",
    },
    "wwi_backorders": {
        "order_key": "i64", "order_date_id": "i32", "customer_key": "i32", "city_key": "i32", "stock_item_key": "i32",
        "salesperson_key": "i32", "picker_key": "i32",
    },
    "wwi_stock_holding": {"snapshot_date_id": "i32", "stock_item_key": "i32", "wwi_stock_item_id": "i32",
                          "quantity_on_hand": "i32", "access_key": "i32"},
    "wwi_stock_item_group": {"wwi_stock_item_id": "i32", "stock_group_id": "i32"},
    "nyc_date": {
        "date_id": "i32", "date_name": "str", "month_id": "i32", "month_name": "str", "month_end_name": "str",
        "month_of_year": "u8", "month_of_year_name": "str", "quarter_id": "i32", "quarter_name": "str",
        "calendar_year": "i16", "calendar_year_name": "str", "day_of_week": "u8", "day_of_week_name": "str",
        "day_name": "str", "day_of_month": "u8", "day_of_month_name": "str", "day_of_year": "i16",
        "day_of_year_name": "str", "stly_date_id": "i32", "stly_date_id_name": "str", "in_source_window": "i32",
        "in_source_window_name": "str",
    },
    "nyc_zone": {"location_id": "i32", "location_id_name": "str", "zone": "str", "borough": "str", "service_zone": "str"},
    "nyc_payment_type": {"payment_type": "i32", "payment_type_code_name": "str", "payment_type_name": "str"},
    "nyc_vendor": {"vendor_id": "i32", "vendor_name": "str"},
    "nyc_pickup_hour": {"pickup_hour": "u8", "pickup_hour_name": "str"},
    "nyc_trips": {
        "trip_id": "i64", "pickup_date_id": "i32", "dropoff_date_id": "i32", "pickup_hour": "u8", "pu_location_id": "i32",
        "do_location_id": "i32", "payment_type": "i32", "vendor_id": "i32", "od_pair_id": "i32", "trip_distance": "cur",
        "fare_amount": "cur", "tip_amount": "cur", "tolls_amount": "cur", "total_amount": "cur", "card_tip": "cur",
        "card_trip": "i32",
    },
}
DSV_KEYS = {
    "wwi_date": "date_id", "wwi_customer": "customer_key", "wwi_city": "city_key", "wwi_stock_item": "stock_item_key",
    "wwi_stock_group": "stock_group_id", "wwi_employee": "employee_key", "wwi_inventory_access": "access_key",
    "nyc_date": "date_id", "nyc_zone": "location_id", "nyc_payment_type": "payment_type", "nyc_vendor": "vendor_id",
    "nyc_pickup_hour": "pickup_hour", "wwi_sales": "sale_key", "wwi_orders": "order_key", "wwi_backorders": "order_key",
    "nyc_trips": "trip_id",
}
XS_TYPE = {"i16": "xs:short", "i32": "xs:int", "i64": "xs:long", "u8": "xs:unsignedByte", "str": "xs:string",
           "cur": "xs:decimal"}
ASSL_TYPE = {"i16": "SmallInt", "i32": "Integer", "i64": "BigInt", "u8": "UnsignedTinyInt", "str": "WChar",
             "cur": "Currency"}


def dsv_sql(table: str) -> str:
    text = (HERE / "dsv" / f"{table}.sql").read_text()
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--")).strip()


# --------------------------------------------------------------------------- model definitions


@dataclass
class Attr:
    name: str
    key: list[str]
    name_col: str | None = None
    related: list[str] = field(default_factory=list)
    usage: str = "Regular"
    type: str | None = None
    visible: bool = True
    enabled: bool = True
    order_by: str = "Key"


@dataclass
class Dim:
    id: str
    table: str
    attrs: list[Attr]
    hierarchies: dict[str, list[str]] = field(default_factory=dict)
    type: str = "Regular"
    description: str = ""
    unknown_member: str = "None"


DATE_HIER = {"Calendar": ["Calendar Year", "Calendar Quarter", "Month", "Date"]}

DIMENSIONS: list[Dim] = [
    Dim("Date", "wwi_date", [
        Attr("Date", ["date_id"], "date_name", ["Month"], usage="Key", type="Days"),
        Attr("Month", ["month_id"], "month_name", ["Calendar Quarter", "Fiscal Month", "Month Of Year",
                                                    "Month End Date"], type="Months"),
        Attr("Month End Date", ["month_id"], "month_end_name", enabled=False),
        Attr("Month Of Year", ["month_of_year"], "month_of_year_name", type="MonthOfYear"),
        Attr("Calendar Quarter", ["quarter_id"], "quarter_name", ["Calendar Year", "Quarter Of Year",
                                                                  "Quarter End Date"], type="Quarters"),
        Attr("Quarter End Date", ["quarter_id"], "quarter_end_name", enabled=False),
        Attr("Quarter Of Year", ["quarter_of_year"], "quarter_of_year_name", type="QuarterOfYear"),
        Attr("Calendar Year", ["calendar_year"], "calendar_year_name", type="Years"),
        Attr("Fiscal Month", ["fiscal_month_id"], "fiscal_month_name", ["Fiscal Quarter", "Fiscal Month Of Year"],
             type="FiscalMonths"),
        Attr("Fiscal Month Of Year", ["fiscal_month_of_year"], "fiscal_month_of_year_name"),
        Attr("Fiscal Quarter", ["fiscal_quarter_id"], "fiscal_quarter_name", ["Fiscal Year", "Fiscal Quarter Of Year"],
             type="FiscalQuarters"),
        Attr("Fiscal Quarter Of Year", ["fiscal_quarter_of_year"], "fiscal_quarter_of_year_name"),
        Attr("Fiscal Year", ["fiscal_year"], "fiscal_year_name", type="FiscalYears"),
    ], {**DATE_HIER, "Fiscal": ["Fiscal Year", "Fiscal Quarter", "Fiscal Month", "Date"]}, type="Time",
        description="WWI calendar (2013-2016) with a fiscal year starting 1 November, labeled by the year in which it "
                    "ends. Role-played as Date (invoice, order and snapshot date) and Delivery Date.",
        unknown_member="Visible"),
    Dim("Customer", "wwi_customer", [
        Attr("Customer Key", ["customer_key"], "customer", ["Customer"], usage="Key", visible=False),
        Attr("Customer", ["customer"], "customer", ["Category", "Buying Group"]),
        Attr("Category", ["category"], "category"),
        Attr("Buying Group", ["buying_group"], "buying_group"),
    ], description="Customer as recorded at the time of sale. Role-played as Customer and Bill To Customer."),
    Dim("City", "wwi_city", [
        Attr("City Key", ["city_key"], "city", ["City"], usage="Key", visible=False),
        Attr("City", ["state_province", "city"], "city", ["State Province"]),
        Attr("State Province", ["state_province"], "state_province", ["Country", "Sales Territory"]),
        Attr("Country", ["country"], "country", ["Continent"]),
        Attr("Continent", ["continent"], "continent"),
        Attr("Sales Territory", ["sales_territory"], "sales_territory"),
    ], {"Geography": ["Continent", "Country", "State Province", "City"],
        "Territory": ["Sales Territory", "State Province", "City"]},
        description="Delivery city as recorded at the time of sale; Sales Territory is an alternate hierarchy over "
                    "State Province."),
    Dim("Stock Item", "wwi_stock_item", [
        Attr("Stock Item Key", ["stock_item_key"], "stock_item", ["WWI Stock Item ID", "Color", "Brand", "Size"],
             usage="Key", visible=False),
        Attr("WWI Stock Item ID", ["wwi_stock_item_id"], "wwi_stock_item_id_name",
             ["Stock Item", "Current Color", "Selling Package", "Is Chiller Stock", "Balance Basis"]),
        Attr("Stock Item", ["stock_item"], "stock_item"),
        Attr("Color", ["color"], "color"),
        Attr("Current Color", ["current_color"], "current_color"),
        Attr("Brand", ["brand"], "brand"),
        Attr("Size", ["size"], "size"),
        Attr("Selling Package", ["selling_package"], "selling_package"),
        Attr("Is Chiller Stock", ["is_chiller_stock"], "is_chiller_stock"),
        Attr("Balance Basis", ["balance_basis"], "balance_basis"),
    ], description="Product as recorded at the time of sale (SCD Type 2). Color is as-was; Current Color is as-is "
                   "through the durable WWI Stock Item ID."),
    Dim("Stock Group", "wwi_stock_group", [
        Attr("Stock Group", ["stock_group_id"], "stock_group_name", usage="Key"),
    ], description="Product group; an item can belong to several groups, so group values overlap while totals are "
                   "deduplicated (many-to-many through the Stock Item Group Bridge)."),
    Dim("Employee", "wwi_employee", [
        Attr("Employee Key", ["employee_key"], "employee", ["Employee"], usage="Key", visible=False),
        Attr("Employee", ["employee"], "employee"),
    ], description="Employee. Role-played as Salesperson (sales and orders) and Picker (orders only).",
        unknown_member="Visible"),
    Dim("Inventory Access", "wwi_inventory_access", [
        Attr("Access", ["access_key"], "access_name", usage="Key", visible=False),
    ], description="Security device: related only to Stock Holdings; roles without inventory access allow none of "
                   "its members with visual totals."),
    Dim("NYC Date", "nyc_date", [
        Attr("Date", ["date_id"], "date_name", ["Month", "Day Of Week", "Day Of Month", "Day Of Year",
                                                "STLY Date ID", "In Source Window"], usage="Key", type="Days"),
        Attr("Month", ["month_id"], "month_name", ["Calendar Quarter", "Month Of Year", "Month End Date"],
             type="Months"),
        Attr("Month End Date", ["month_id"], "month_end_name", enabled=False),
        Attr("Month Of Year", ["month_of_year"], "month_of_year_name", type="MonthOfYear"),
        Attr("Calendar Quarter", ["quarter_id"], "quarter_name", ["Calendar Year"], type="Quarters"),
        Attr("Calendar Year", ["calendar_year"], "calendar_year_name", type="Years"),
        Attr("Day Of Week", ["day_of_week"], "day_of_week_name", ["Day Name"], type="DayOfWeek"),
        Attr("Day Name", ["day_of_week"], "day_name", enabled=False),
        Attr("Day Of Month", ["date_id"], "day_of_month_name", enabled=False),
        Attr("Day Of Year", ["date_id"], "day_of_year_name", enabled=False),
        Attr("STLY Date ID", ["date_id"], "stly_date_id_name", enabled=False),
        Attr("In Source Window", ["in_source_window"], "in_source_window_name", visible=False),
    ], DATE_HIER, type="Time",
        description="NYC calendar (2023-2025). Role-played as Pickup Date (anchor of YTD and pace metrics) and "
                    "Dropoff Date."),
    Dim("Zone", "nyc_zone", [
        Attr("Zone", ["location_id"], "zone", ["Location ID", "Borough", "Service Zone"], usage="Key"),
        Attr("Location ID", ["location_id"], "location_id_name"),
        Attr("Borough", ["borough"], "borough"),
        Attr("Service Zone", ["service_zone"], "service_zone"),
    ], {"Zones": ["Borough", "Zone"]},
        description="TLC taxi zone. Role-played as Pickup Zone and Dropoff Zone."),
    Dim("Payment Type", "nyc_payment_type", [
        Attr("Payment Type Code", ["payment_type"], "payment_type_code_name", ["Payment Type"], usage="Key"),
        Attr("Payment Type", ["payment_type"], "payment_type_name"),
    ], description="TLC payment type code and label."),
    Dim("Vendor", "nyc_vendor", [
        Attr("Vendor", ["vendor_id"], "vendor_name", usage="Key"),
    ], description="TLC technology provider that recorded the trip."),
    Dim("Pickup Hour", "nyc_pickup_hour", [
        Attr("Pickup Hour", ["pickup_hour"], "pickup_hour_name", usage="Key"),
    ], description="Hour of day the trip started, 0-23."),
]
DIM_BY_ID = {d.id: d for d in DIMENSIONS}


@dataclass
class Measure:
    name: str
    function: str
    column: str | None
    data_type: str
    fmt: str
    visible: bool = True
    metric: str | None = None


@dataclass
class MGDim:
    cube_dim: str
    attribute: str | None = None
    columns: list[str] = field(default_factory=list)
    unknown: bool = False
    many_to_many: str | None = None


@dataclass
class MeasureGroup:
    id: str
    table: str
    measures: list[Measure]
    dims: list[MGDim]
    ignore_unrelated: bool = False
    partitioned_by_month: bool = False
    description: str = ""


FMT_CUR = "#,##0.00"
FMT_INT = "#,##0"

CUBES: dict[str, dict] = {
    "WWI": {
        "description": "WideWorldImporters sales, orders and inventory (W-S1 to W-C2, B-W1 to B-W5).",
        "dimensions": [("Date", "Date"), ("Delivery Date", "Date"), ("Customer", "Customer"),
                       ("Bill To Customer", "Customer"), ("City", "City"), ("Stock Item", "Stock Item"),
                       ("Stock Group", "Stock Group"), ("Salesperson", "Employee"), ("Picker", "Employee"),
                       ("Inventory Access", "Inventory Access")],
        "measure_groups": [
            MeasureGroup("Sales", "wwi_sales", [
                Measure("Revenue", "Sum", "total_excluding_tax", "Currency", FMT_CUR, metric="W-S1"),
                Measure("Revenue Including Tax", "Sum", "total_including_tax", "Currency", FMT_CUR, metric="B-W1"),
                Measure("Gross Profit", "Sum", "profit", "Currency", FMT_CUR, metric="B-W2"),
                Measure("Units Sold", "Sum", "quantity", "BigInt", FMT_INT, metric="B-W3"),
                Measure("Sales Lines", "Count", None, "Integer", FMT_INT, visible=False),
            ], [
                MGDim("Date", "Date", ["invoice_date_id"]),
                MGDim("Delivery Date", "Date", ["delivery_date_id"], unknown=True),
                MGDim("Customer", "Customer Key", ["customer_key"]),
                MGDim("Bill To Customer", "Customer Key", ["bill_to_customer_key"]),
                MGDim("City", "City Key", ["city_key"]),
                MGDim("Stock Item", "Stock Item Key", ["stock_item_key"]),
                MGDim("Salesperson", "Employee Key", ["salesperson_key"]),
                MGDim("Stock Group", many_to_many="Stock Item Group Bridge"),
            ], description="Invoice lines (fact_sale)."),
            MeasureGroup("Invoices", "wwi_sales", [
                Measure("Invoice Count", "DistinctCount", "wwi_invoice_id", "Integer", FMT_INT, metric="B-W4"),
            ], [
                MGDim("Date", "Date", ["invoice_date_id"]),
                MGDim("Delivery Date", "Date", ["delivery_date_id"], unknown=True),
                MGDim("Customer", "Customer Key", ["customer_key"]),
                MGDim("Bill To Customer", "Customer Key", ["bill_to_customer_key"]),
                MGDim("City", "City Key", ["city_key"]),
                MGDim("Stock Item", "Stock Item Key", ["stock_item_key"]),
                MGDim("Salesperson", "Employee Key", ["salesperson_key"]),
                MGDim("Stock Group", many_to_many="Stock Item Group Bridge"),
            ], description="Distinct invoice count in its dedicated measure group (B-06)."),
            MeasureGroup("Orders", "wwi_orders", [
                Measure("Ordered Quantity", "Sum", "quantity", "BigInt", FMT_INT, metric="W-S2"),
                Measure("Order Lines", "Count", None, "Integer", FMT_INT, visible=False),
            ], [
                MGDim("Date", "Date", ["order_date_id"]),
                MGDim("Customer", "Customer Key", ["customer_key"]),
                MGDim("City", "City Key", ["city_key"]),
                MGDim("Stock Item", "Stock Item Key", ["stock_item_key"]),
                MGDim("Salesperson", "Employee Key", ["salesperson_key"]),
                MGDim("Picker", "Employee Key", ["picker_key"], unknown=True),
                MGDim("Stock Group", many_to_many="Stock Item Group Bridge"),
            ], description="Order lines (fact_order), dated by order date."),
            MeasureGroup("Backorders", "wwi_backorders", [
                Measure("Backordered Order Lines", "Count", None, "Integer", FMT_INT, metric="B-W5"),
            ], [
                MGDim("Date", "Date", ["order_date_id"]),
                MGDim("Customer", "Customer Key", ["customer_key"]),
                MGDim("City", "City Key", ["city_key"]),
                MGDim("Stock Item", "Stock Item Key", ["stock_item_key"]),
                MGDim("Salesperson", "Employee Key", ["salesperson_key"]),
                MGDim("Picker", "Employee Key", ["picker_key"], unknown=True),
                MGDim("Stock Group", many_to_many="Stock Item Group Bridge"),
            ], description="Order lines with a backorder id."),
            MeasureGroup("Stock Holdings", "wwi_stock_holding", [
                Measure("Closing Units", "LastNonEmpty", "quantity_on_hand", "BigInt", FMT_INT, metric="W-M2"),
                Measure("Stock Snapshot Rows", "Count", None, "Integer", FMT_INT, visible=False),
            ], [
                MGDim("Date", "Date", ["snapshot_date_id"]),
                MGDim("Stock Item", "Stock Item Key", ["stock_item_key"]),
                MGDim("Inventory Access", "Access", ["access_key"]),
                MGDim("Stock Group", many_to_many="Stock Item Group Bridge"),
            ], description="Dense daily stock snapshot (fact_stock_holding_daily)."),
            MeasureGroup("Stock Item Group Bridge", "wwi_stock_item_group", [
                Measure("Bridge Rows", "Count", None, "Integer", FMT_INT, visible=False),
            ], [
                MGDim("Stock Item", "WWI Stock Item ID", ["wwi_stock_item_id"]),
                MGDim("Stock Group", "Stock Group", ["stock_group_id"]),
            ], description="Intermediate measure group of the Stock Group many-to-many relationship."),
        ],
        "mdx": "WWI.mdx",
    },
    "NYC": {
        "description": "NYC Yellow Taxi trips 2023-2024 (N-S1 to N-C2, B-N1 to B-N5).",
        "dimensions": [("Pickup Date", "NYC Date"), ("Dropoff Date", "NYC Date"), ("Pickup Zone", "Zone"),
                       ("Dropoff Zone", "Zone"), ("Payment Type", "Payment Type"), ("Vendor", "Vendor"),
                       ("Pickup Hour", "Pickup Hour")],
        "measure_groups": [
            MeasureGroup("Trips", "nyc_trips", [
                Measure("Trip Count", "Count", None, "BigInt", FMT_INT, metric="B-N1"),
                Measure("Total Trip Distance", "Sum", "trip_distance", "Currency", FMT_CUR, metric="B-N2"),
                Measure("Fare Amount", "Sum", "fare_amount", "Currency", FMT_CUR, metric="B-N3"),
                Measure("Tip Amount", "Sum", "tip_amount", "Currency", FMT_CUR, metric="B-N4"),
                Measure("Tolls Amount", "Sum", "tolls_amount", "Currency", FMT_CUR, metric="B-N5"),
                Measure("Gross Trip Revenue", "Sum", "total_amount", "Currency", FMT_CUR, metric="N-S1"),
                Measure("Card Tips Sum", "Sum", "card_tip", "Currency", FMT_CUR, visible=False),
                Measure("Card Trips", "Sum", "card_trip", "BigInt", FMT_INT, visible=False),
            ], [
                MGDim("Pickup Date", "Date", ["pickup_date_id"]),
                MGDim("Dropoff Date", "Date", ["dropoff_date_id"]),
                MGDim("Pickup Zone", "Zone", ["pu_location_id"]),
                MGDim("Dropoff Zone", "Zone", ["do_location_id"]),
                MGDim("Payment Type", "Payment Type Code", ["payment_type"]),
                MGDim("Vendor", "Vendor", ["vendor_id"]),
                MGDim("Pickup Hour", "Pickup Hour", ["pickup_hour"]),
            ], partitioned_by_month=True, description="Valid trips (fact_trip); monthly MOLAP partitions plus a ROLAP "
                                                      "hot partition."),
            MeasureGroup("OD Pairs", "nyc_trips", [
                Measure("Distinct OD Pairs", "DistinctCount", "od_pair_id", "Integer", FMT_INT, metric="N-M1"),
            ], [
                MGDim("Pickup Date", "Date", ["pickup_date_id"]),
                MGDim("Dropoff Date", "Date", ["dropoff_date_id"]),
                MGDim("Pickup Zone", "Zone", ["pu_location_id"]),
                MGDim("Dropoff Zone", "Zone", ["do_location_id"]),
                MGDim("Payment Type", "Payment Type Code", ["payment_type"]),
                MGDim("Vendor", "Vendor", ["vendor_id"]),
                MGDim("Pickup Hour", "Pickup Hour", ["pickup_hour"]),
            ], partitioned_by_month=True, description="Distinct OD pair count in its dedicated measure group (B-06)."),
        ],
        "mdx": "NYC.mdx",
    },
}

# Calculated measures defined in mdx/*.mdx, with their glossary metric (descriptions come from the glossary).
CALCULATED = {
    "WWI": {"Gross Margin %": "W-M1", "Revenue All Stock Groups": None, "Stock Group Revenue Share": "W-C1",
            "Units Sold 91D": None, "Days of Supply": "W-C2"},
    "NYC": {"Card Tips": "N-S2", "Fare per Mile": "N-M2", "Revenue YTD": "N-C1", "Revenue STLY YTD": None,
            "Revenue YoY %": None, "Trips MTD": None, "Trips YTD": None, "Days Elapsed In Month": None,
            "Days Elapsed In Year": None, "Pace Index": "N-C2"},
}
CALC_DESCRIPTIONS = {
    "Revenue All Stock Groups": "Revenue with the Stock Group context removed (deduplicated parent total of W-C1).",
    "Units Sold 91D": "Units sold in the 91 days ending on the last snapshot date in context (W-C2 denominator).",
    "Revenue STLY YTD": "Revenue YTD for the same date one year earlier (29 February maps to 28 February).",
    "Revenue YoY %": "(Revenue YTD - Revenue STLY YTD) / Revenue STLY YTD.",
    "Trips MTD": "Trips from the first day of the anchor month to the anchor date.",
    "Trips YTD": "Trips from 1 January of the anchor year to the anchor date.",
    "Days Elapsed In Month": "Day of month of the anchor date (calendar days elapsed).",
    "Days Elapsed In Year": "Day of year of the anchor date (calendar days elapsed).",
}

ROLES = [
    {"id": "SLC Analysts", "members": ["SLC\\slc_analysts"], "cubes": {"WWI": {}, "NYC": {}},
     "description": "Unrestricted read on both cubes (E2, E7 lanes)."},
    {"id": "Territory Analyst - Southeast", "members": ["SLC\\slc_territory_southeast"],
     "description": "SPEC § 10: sales and orders restricted to the Southeast sales territory (as-was city); no "
                    "inventory access.",
     "cubes": {"WWI": {"City": [("Sales Territory", "{[City].[Sales Territory].&[Southeast]}")],
                       "Inventory Access": [("Access", "{}")]}}},
    {"id": "Manhattan Pickup Analyst", "members": ["SLC\\slc_pickup_manhattan"],
     "description": "SPEC § 10: trips restricted to Manhattan pickup zones; the dropoff role is unrestricted.",
     "cubes": {"NYC": {"Pickup Zone": [("Borough", "{[Pickup Zone].[Borough].&[Manhattan]}")]}}},
]

# --------------------------------------------------------------------------- glossary metadata

METRICS = {m["id"]: m for m in GLOSSARY["metrics"]}
GLOSSARY_DIMS = {d["name"]: d for ds in GLOSSARY["dimensions"].values() for d in ds}
CUBE_DIM_GLOSSARY = {
    "Date": "date", "Delivery Date": "delivery_date", "Customer": "customer", "Bill To Customer": "bill_to_customer",
    "City": "city", "Stock Item": "stock_item", "Stock Group": "stock_group", "Salesperson": "salesperson",
    "Picker": "picker", "Pickup Date": "pickup_date", "Dropoff Date": "dropoff_date", "Pickup Zone": "pickup_zone",
    "Dropoff Zone": "dropoff_zone", "Payment Type": "payment_type", "Vendor": "vendor", "Pickup Hour": "pickup_hour",
}

# --------------------------------------------------------------------------- XML helpers


def q(tag: str) -> str:
    if tag.startswith("xs:"):
        return f"{{{XS}}}{tag[3:]}"
    return f"{{{NS}}}{tag}"


def sub(parent: ET.Element, tag: str, text: str | None = None, **attrs) -> ET.Element:
    el = ET.SubElement(parent, q(tag), {k: v for k, v in attrs.items()})
    if text is not None:
        el.text = text
    return el


def xsi_type(el: ET.Element, value: str) -> None:
    el.set(f"{{{XSI}}}type", value)


def annotations(parent: ET.Element, values: dict[str, str]) -> None:
    if not values:
        return
    anns = sub(parent, "Annotations")
    for name, value in values.items():
        a = sub(anns, "Annotation")
        sub(a, "Name", name)
        sub(a, "Value", value)


def synonyms_of(meta: dict | None) -> dict[str, str]:
    if not meta or not meta.get("synonyms"):
        return {}
    return {"slc:synonyms": "; ".join(meta["synonyms"])}


def column_binding(parent: ET.Element, table: str, column: str) -> None:
    src = sub(parent, "Source")
    xsi_type(src, "ColumnBinding")
    sub(src, "TableID", table)
    sub(src, "ColumnID", column)


def data_item(parent: ET.Element, tag: str, table: str, column: str, null_processing: str | None = None) -> None:
    t = DSV_TABLES[table][column]
    el = sub(parent, tag)
    sub(el, "DataType", ASSL_TYPE[t] if t != "cur" else "Currency")
    if t == "str":
        sub(el, "DataSize", "255")
    if null_processing:
        sub(el, "NullProcessing", null_processing)
    column_binding(el, table, column)


# --------------------------------------------------------------------------- object builders


def data_source() -> ET.Element:
    ds = ET.Element(q("DataSource"))
    xsi_type(ds, "RelationalDataSource")
    sub(ds, "ID", DATA_SOURCE)
    sub(ds, "Name", DATA_SOURCE)
    sub(ds, "Description", "SQL Server 2025 adapter database: PolyBase ODBC external tables over the Databricks gold "
                           "tables (adapter/). ODBC sources are not supported for multidimensional models and ROLAP "
                           "requires a SQL Server relational source.")
    sub(ds, "ConnectionString", f"Provider=MSOLEDBSQL;Data Source={ADAPTER_SERVER};Initial Catalog={ADAPTER_DATABASE};"
                                "Integrated Security=SSPI;Encrypt=Mandatory")
    imp = sub(ds, "ImpersonationInfo")
    sub(imp, "ImpersonationMode", "ImpersonateServiceAccount")
    sub(ds, "Timeout", "PT0S")
    return ds


def data_source_view() -> ET.Element:
    dsv = ET.Element(q("DataSourceView"))
    sub(dsv, "ID", DSV)
    sub(dsv, "Name", DSV)
    sub(dsv, "DataSourceID", DATA_SOURCE)
    schema_holder = sub(dsv, "Schema")
    schema = ET.SubElement(schema_holder, f"{{{XS}}}schema", {"id": DSV})
    root = ET.SubElement(schema, f"{{{XS}}}element", {
        "name": DSV, f"{{{MSDATA}}}IsDataSet": "true", f"{{{MSDATA}}}UseCurrentLocale": "true"})
    ctype = ET.SubElement(root, f"{{{XS}}}complexType")
    choice = ET.SubElement(ctype, f"{{{XS}}}choice", {"minOccurs": "0", "maxOccurs": "unbounded"})
    for table, columns in DSV_TABLES.items():
        el = ET.SubElement(choice, f"{{{XS}}}element", {
            "name": table, f"{{{MSPROP}}}TableType": "View", f"{{{MSPROP}}}IsLogical": "True",
            f"{{{MSPROP}}}FriendlyName": table, f"{{{MSPROP}}}QueryBuilder": "GenericQueryBuilder",
            f"{{{MSPROP}}}QueryDefinition": dsv_sql(table), f"{{{MSPROP}}}DbTableName": table})
        seq = ET.SubElement(ET.SubElement(el, f"{{{XS}}}complexType"), f"{{{XS}}}sequence")
        for col, t in columns.items():
            attrs = {"name": col, "minOccurs": "0"} if col != DSV_KEYS.get(table) else {"name": col}
            if t == "str":
                c = ET.SubElement(seq, f"{{{XS}}}element", attrs)
                r = ET.SubElement(ET.SubElement(c, f"{{{XS}}}simpleType"), f"{{{XS}}}restriction", {"base": "xs:string"})
                ET.SubElement(r, f"{{{XS}}}maxLength", {"value": "255"})
            else:
                ET.SubElement(seq, f"{{{XS}}}element", {**attrs, "type": XS_TYPE[t]})
    for table in [t for t in DSV_TABLES if not t.startswith(("wwi_sales", "wwi_orders", "wwi_backorders",
                                                             "nyc_trips", "wwi_stock_holding", "wwi_stock_item_group"))]:
        u = ET.SubElement(root, f"{{{XS}}}unique", {"name": f"pk_{table}", f"{{{MSDATA}}}PrimaryKey": "true"})
        ET.SubElement(u, f"{{{XS}}}selector", {"xpath": f".//{table}"})
        ET.SubElement(u, f"{{{XS}}}field", {"xpath": DSV_KEYS[table]})
    ET.SubElement(schema_holder, DSV)
    return dsv


def dimension(d: Dim) -> ET.Element:
    el = ET.Element(q("Dimension"))
    sub(el, "ID", d.id)
    sub(el, "Name", d.id)
    sub(el, "Description", d.description)
    src = sub(el, "Source")
    xsi_type(src, "DataSourceViewBinding")
    sub(src, "DataSourceViewID", DSV)
    sub(el, "Type", d.type)
    sub(el, "UnknownMember", d.unknown_member)
    sub(el, "Language", "1033")
    sub(el, "Collation", "Latin1_General_CI_AS")
    sub(el, "UnknownMemberName", "Unknown")
    attrs = sub(el, "Attributes")
    for a in d.attrs:
        ae = sub(attrs, "Attribute")
        sub(ae, "ID", a.name)
        sub(ae, "Name", a.name)
        if a.type:
            sub(ae, "Type", a.type)
        sub(ae, "Usage", a.usage)
        kcs = sub(ae, "KeyColumns")
        for c in a.key:
            data_item(kcs, "KeyColumn", d.table, c, "ZeroOrBlank" if DSV_TABLES[d.table][c] == "str" else None)
        if a.name_col:
            nc = sub(ae, "NameColumn")
            sub(nc, "DataType", "WChar")
            sub(nc, "DataSize", "255")
            sub(nc, "NullProcessing", "ZeroOrBlank")
            column_binding(nc, d.table, a.name_col)
        if a.related:
            rels = sub(ae, "AttributeRelationships")
            for r in a.related:
                re_ = sub(rels, "AttributeRelationship")
                sub(re_, "AttributeID", r)
                sub(re_, "RelationshipType", "Rigid")
                sub(re_, "Name", r)
        sub(ae, "OrderBy", a.order_by)
        if not a.enabled:
            sub(ae, "AttributeHierarchyEnabled", "false")
        if not a.visible:
            sub(ae, "AttributeHierarchyVisible", "false")
    if d.hierarchies:
        hs = sub(el, "Hierarchies")
        for h, levels in d.hierarchies.items():
            he = sub(hs, "Hierarchy")
            sub(he, "ID", h)
            sub(he, "Name", h)
            ls = sub(he, "Levels")
            for lv in levels:
                le = sub(ls, "Level")
                sub(le, "ID", lv)
                sub(le, "Name", lv)
                sub(le, "SourceAttributeID", lv)
    return el


def mdx_script_text(cube: str) -> str:
    return (HERE / "mdx" / CUBES[cube]["mdx"]).read_text()


def month_ranges() -> list[tuple[str, str, str]]:
    """(partition suffix, inclusive start, exclusive end) for every NYC month in the source window."""
    out = []
    y, m = NYC_FIRST_MONTH
    while (y, m) <= NYC_LAST_MONTH:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"{y:04d}-{m:02d}", f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"))
        y, m = ny, nm
    return out


def hot_start() -> str:
    y, m = NYC_LAST_MONTH
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{ny:04d}-{nm:02d}-01"


def partition_query(table: str, start: str | None, end: str | None) -> str:
    base = dsv_sql(table)
    preds = []
    if start:
        preds.append(f"t.pickup_date >= '{start}'")
    if end:
        preds.append(f"t.pickup_date < '{end}'")
    return base + ("\nWHERE " + " AND ".join(preds) if preds else "")


def partitions(mg: MeasureGroup) -> list[tuple[str, str, str]]:
    """(name, storage mode, query) of each partition of a measure group."""
    if not mg.partitioned_by_month:
        return [(mg.id, "Molap", dsv_sql(mg.table))]
    out = [(f"{mg.id} {suffix}", "Molap", partition_query(mg.table, start, end)) for suffix, start, end in month_ranges()]
    out.append((f"{mg.id} Hot", "Rolap", partition_query(mg.table, hot_start(), None)))
    return out


def partition_element(parent: ET.Element, name: str, storage: str, query: str) -> ET.Element:
    p = sub(parent, "Partition")
    sub(p, "ID", name)
    sub(p, "Name", name)
    src = sub(p, "Source")
    xsi_type(src, "QueryBinding")
    sub(src, "DataSourceID", DATA_SOURCE)
    sub(src, "QueryDefinition", query)
    sub(p, "StorageMode", storage)
    return p


def cube(cube_id: str) -> ET.Element:
    spec = CUBES[cube_id]
    el = ET.Element(q("Cube"))
    sub(el, "ID", cube_id)
    sub(el, "Name", cube_id)
    sub(el, "Description", spec["description"])
    sub(el, "Language", "1033")
    sub(el, "Collation", "Latin1_General_CI_AS")
    dims = sub(el, "Dimensions")
    for cube_dim, db_dim in spec["dimensions"]:
        cd = sub(dims, "Dimension")
        sub(cd, "ID", cube_dim)
        sub(cd, "Name", cube_dim)
        meta = GLOSSARY_DIMS.get(CUBE_DIM_GLOSSARY.get(cube_dim, ""))
        if meta:
            sub(cd, "Description", meta["description"])
            annotations(cd, synonyms_of(meta))
        sub(cd, "DimensionID", db_dim)
    perms = [r for r in ROLES if cube_id in r["cubes"]]
    if perms:
        cps = sub(el, "CubePermissions")
        for r in perms:
            cp = sub(cps, "CubePermission")
            sub(cp, "ID", f"{r['id']} - {cube_id}")
            sub(cp, "Name", f"{r['id']} - {cube_id}")
            sub(cp, "RoleID", r["id"])
            sub(cp, "Read", "Allowed")
            restrictions = r["cubes"][cube_id]
            if restrictions:
                dps = sub(cp, "DimensionPermissions")
                for cube_dim, attr_perms in restrictions.items():
                    dp = sub(dps, "CubeDimensionPermission")
                    sub(dp, "CubeDimensionID", cube_dim)
                    sub(dp, "Read", "Allowed")
                    aps = sub(dp, "AttributePermissions")
                    for attr, allowed in attr_perms:
                        ap = sub(aps, "AttributePermission")
                        sub(ap, "AttributeID", attr)
                        sub(ap, "AllowedSet", allowed)
                        sub(ap, "VisualTotals", "1")
    scripts = sub(el, "MdxScripts")
    ms = sub(scripts, "MdxScript")
    sub(ms, "ID", "MdxScript")
    sub(ms, "Name", "MdxScript")
    cmd = sub(sub(ms, "Commands"), "Command")
    sub(cmd, "Text", mdx_script_text(cube_id))
    props = sub(ms, "CalculationProperties")
    for calc, metric in CALCULATED[cube_id].items():
        cpr = sub(props, "CalculationProperty")
        sub(cpr, "CalculationReference", f"[Measures].[{calc}]")
        sub(cpr, "CalculationType", "Member")
        meta = METRICS.get(metric) if metric else None
        sub(cpr, "Description", meta["description"] if meta else CALC_DESCRIPTIONS[calc])
        if meta:
            annotations(cpr, synonyms_of(meta))
    mgs = sub(el, "MeasureGroups")
    for mg in spec["measure_groups"]:
        me = sub(mgs, "MeasureGroup")
        sub(me, "ID", mg.id)
        sub(me, "Name", mg.id)
        sub(me, "Description", mg.description)
        measures = sub(me, "Measures")
        for m in mg.measures:
            mm = sub(measures, "Measure")
            sub(mm, "ID", m.name)
            sub(mm, "Name", m.name)
            meta = METRICS.get(m.metric) if m.metric else None
            if meta:
                sub(mm, "Description", meta["description"])
                annotations(mm, synonyms_of(meta))
            sub(mm, "AggregateFunction", m.function)
            sub(mm, "DataType", m.data_type)
            src = sub(mm, "Source")
            if m.column is None:
                sub(src, "DataType", "Integer")
                sub(src, "DataSize", "4")
                rb = sub(src, "Source")
                xsi_type(rb, "RowBinding")
                sub(rb, "TableID", mg.table)
            else:
                t = DSV_TABLES[mg.table][m.column]
                sub(src, "DataType", ASSL_TYPE[t])
                sub(src, "NullProcessing", "Preserve")
                column_binding(src, mg.table, m.column)
            if not m.visible:
                sub(mm, "Visible", "false")
            sub(mm, "FormatString", m.fmt)
        sub(me, "StorageMode", "Molap")
        sub(me, "IgnoreUnrelatedDimensions", "true" if mg.ignore_unrelated else "false")
        mds = sub(me, "Dimensions")
        for d in mg.dims:
            de = sub(mds, "Dimension")
            if d.many_to_many:
                xsi_type(de, "ManyToManyMeasureGroupDimension")
                sub(de, "CubeDimensionID", d.cube_dim)
                sub(de, "MeasureGroupID", d.many_to_many)
                continue
            xsi_type(de, "RegularMeasureGroupDimension")
            sub(de, "CubeDimensionID", d.cube_dim)
            attrs = sub(de, "Attributes")
            ae = sub(attrs, "Attribute")
            sub(ae, "AttributeID", d.attribute)
            kcs = sub(ae, "KeyColumns")
            for c in d.columns:
                data_item(kcs, "KeyColumn", mg.table, c, "UnknownMember" if d.unknown else None)
            sub(ae, "Type", "Granularity")
        parts = sub(me, "Partitions")
        for name, storage, query in partitions(mg):
            partition_element(parts, name, storage, query)
    src = sub(el, "Source")
    sub(src, "DataSourceViewID", DSV)
    return el


def role(r: dict) -> ET.Element:
    el = ET.Element(q("Role"))
    sub(el, "ID", r["id"])
    sub(el, "Name", r["id"])
    sub(el, "Description", r["description"])
    members = sub(el, "Members")
    for m in r["members"]:
        sub(sub(members, "Member"), "Name", m)
    return el


def database_shell() -> ET.Element:
    db = ET.Element(q("Database"))
    sub(db, "ID", DATABASE)
    sub(db, "Name", DATABASE)
    sub(db, "Description", "Enterprise semantic layer comparison study, stack S1 (SSAS Multidimensional, SPEC § 3.1).")
    sub(db, "Language", "1033")
    sub(db, "Collation", "Latin1_General_CI_AS")
    imp = sub(db, "DataSourceImpersonationInfo")
    sub(imp, "ImpersonationMode", "Default")
    return db


def full_database() -> ET.Element:
    db = database_shell()
    dims = sub(db, "Dimensions")
    for d in DIMENSIONS:
        dims.append(dimension(d))
    cubes = sub(db, "Cubes")
    for c in CUBES:
        cubes.append(cube(c))
    roles = sub(db, "Roles")
    for r in ROLES:
        roles.append(role(r))
    sub(db, "DataSources").append(data_source())
    sub(db, "DataSourceViews").append(data_source_view())
    perms = sub(db, "DatabasePermissions")
    for r in ROLES:
        p = sub(perms, "DatabasePermission")
        sub(p, "ID", f"{r['id']} - database")
        sub(p, "Name", f"{r['id']} - database")
        sub(p, "RoleID", r["id"])
        sub(p, "Read", "Allowed")
    return db


def xml_text(el: ET.Element) -> str:
    ET.indent(el, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(el, encoding="unicode") + "\n"


def create_command() -> str:
    create = ET.Element(q("Create"), {"AllowOverwrite": "true"})
    obj = sub(create, "ObjectDefinition")
    obj.append(full_database())
    return xml_text(create)


def process_command() -> str:
    batch = ET.Element(q("Batch"), {"Transaction": "true"})
    par = sub(batch, "Parallel")
    proc = sub(par, "Process")
    obj = sub(proc, "Object")
    sub(obj, "DatabaseID", DATABASE)
    sub(proc, "Type", "ProcessFull")
    sub(proc, "WriteBackTableCreation", "UseExisting")
    return xml_text(batch)


# --------------------------------------------------------------------------- adapter DDL

SQLSERVER_TYPE = {"DATE": "DATE", "SMALLINT": "SMALLINT", "TINYINT": "TINYINT", "INT": "INT", "BIGINT": "BIGINT",
                  "STRING": "NVARCHAR(400)", "BOOLEAN": "BIT", "TIMESTAMP": "DATETIME2(6)",
                  "TIMESTAMP_NTZ": "DATETIME2(6)"}
ADAPTER_TABLES = ["wwi.dim_date", "wwi.dim_city", "wwi.dim_customer", "wwi.dim_employee", "wwi.dim_stock_item",
                  "wwi.dim_stock_group", "wwi.bridge_stock_item_group", "wwi.fact_sale", "wwi.fact_order",
                  "wwi.fact_stock_holding_daily", "nyctaxi.dim_date", "nyctaxi.dim_zone", "nyctaxi.dim_payment_type",
                  "nyctaxi.fact_trip"]


def sqlserver_type(t: str) -> str:
    return t if t.startswith("DECIMAL") else SQLSERVER_TYPE[t]


def external_tables() -> str:
    lines = [
        "-- SQL Server 2025 adapter for S1: one PolyBase external table per canonical gold table read by the cube.",
        "-- Generated by build_model.py from 01-spec/oracle/fixtures/schema.json (SPEC § 5); run after",
        "-- 01_polybase.sql in database slc_adapter. Types follow the canonical schema; STRING maps to NVARCHAR(400).",
        "USE slc_adapter;",
        "GO",
        "IF SCHEMA_ID(N'wwi') IS NULL EXEC (N'CREATE SCHEMA wwi');",
        "GO",
        "IF SCHEMA_ID(N'nyctaxi') IS NULL EXEC (N'CREATE SCHEMA nyctaxi');",
        "GO",
    ]
    for t in ADAPTER_TABLES:
        cols = CANONICAL[t]
        lines.append(f"IF OBJECT_ID(N'{t}') IS NOT NULL DROP EXTERNAL TABLE {t};")
        lines.append("GO")
        lines.append(f"CREATE EXTERNAL TABLE {t} (")
        lines.append(",\n".join(f"  [{c}] {sqlserver_type(ty)} NULL" for c, ty in cols))
        lines.append(f") WITH (DATA_SOURCE = slc_databricks, LOCATION = 'slc.{t}');")
        lines.append("GO")
    return "\n".join(lines) + "\n"


def statistics() -> str:
    targets = {
        "wwi.fact_sale": ["invoice_date", "stock_item_key", "city_key"],
        "wwi.fact_order": ["order_date", "stock_item_key"],
        "wwi.fact_stock_holding_daily": ["snapshot_date", "wwi_stock_item_id"],
        "nyctaxi.fact_trip": ["pickup_date", "pu_location_id"],
    }
    lines = ["-- Statistics on the PolyBase external tables for the columns partition queries and joins filter on",
             "-- (PolyBase guidance: create statistics on columns used for joins, filters and aggregates).",
             "-- Generated by build_model.py.", "USE slc_adapter;", "GO"]
    for t, cols in targets.items():
        for c in cols:
            name = f"st_{t.split('.')[1]}_{c}"
            lines.append(f"IF NOT EXISTS (SELECT 1 FROM sys.stats WHERE name = N'{name}' AND object_id = OBJECT_ID(N'{t}'))")
            lines.append(f"  CREATE STATISTICS {name} ON {t} ([{c}]) WITH FULLSCAN;")
            lines.append("GO")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- outputs


def outputs() -> dict[Path, str]:
    files: dict[Path, str] = {}
    files[HERE / "model" / "slc.database"] = xml_text(database_shell())
    files[HERE / "model" / "slc.ds"] = xml_text(data_source())
    files[HERE / "model" / "slc.dsv"] = xml_text(data_source_view())
    for d in DIMENSIONS:
        files[HERE / "model" / f"{d.id}.dim"] = xml_text(dimension(d))
    for c in CUBES:
        files[HERE / "model" / f"{c}.cube"] = xml_text(cube(c))
    for r in ROLES:
        files[HERE / "model" / f"{r['id']}.role"] = xml_text(role(r))
    files[HERE / "deploy" / "slc.xmla"] = create_command()
    files[HERE / "deploy" / "process_full.xmla"] = process_command()
    files[HERE / "adapter" / "02_external_tables.sql"] = external_tables()
    files[HERE / "adapter" / "03_statistics.sql"] = statistics()
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    expected = outputs()
    for path, text in expected.items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(HERE)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if not args.check:
        for path in (HERE / "model").glob("*"):
            if path not in expected:
                path.unlink()
    if stale:
        print(f"stale generated files: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
