#!/usr/bin/env python3
"""Build the Databricks Unity Catalog Metric Views for the study (SPEC § 3.1 S4).

Single source of the metric view definitions. Writes:
  metric_views/<view>.yaml          YAML 1.1 definitions (the reviewable artifact)
  sql/governed/<view>.sql           CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML, no materialization
  sql/accelerated/<view>.sql        same, plus the materialization block (no row-level security possible, SPEC B-01)
Agent metadata (comment, display_name, synonyms, format) comes from 01-spec/glossary.yaml so every
stack carries the same metadata (SPEC § 11.2).

Syntax verified 2026-11-20 against:
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference        (updated 2026-11-16)
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques   (window measures, composability)
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/level-of-detail       (range: all)
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/joins                  (snowflake, cardinality, rely)
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/materialization
  https://docs.databricks.com/aws/en/uc-semantics/metric-views/feature-availability   (updated 2026-11-09)

    python build_metric_views.py          # write all generated files
    python build_metric_views.py --check  # exit 1 if any committed file is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GLOSSARY = yaml.safe_load((REPO / "01-spec" / "glossary.yaml").read_text())
CATALOG = "slc"
SCHEMA = f"{CATALOG}.semantic"
SPEC_VERSION = 1.1  # emitted unquoted, as in the YAML reference examples

# --------------------------------------------------------------------------- metadata

METRICS = {m["id"]: m for m in GLOSSARY["metrics"]}
DIMS = {d["name"]: d for ds in GLOSSARY["dimensions"].values() for d in ds}


def fmt(key: str) -> dict:
    f = GLOSSARY["formats"][key]
    out = {"type": f["type"]}
    if "currency_code" in f:
        out["currency_code"] = f["currency_code"]
    out["decimal_places"] = {"type": "exact", "places": f["decimal_places"]}
    return out


def title(name: str) -> str:
    return " ".join(w.upper() if w in {"id", "od", "ytd", "stly", "mtd", "wwi"} else w.capitalize() for w in name.split("_"))


def field(name, expr, dim=None, comment=None, display=None):
    f = {"name": name, "expr": expr}
    meta_comment = comment or (DIMS[dim]["description"] if dim else None)
    if meta_comment:
        f["comment"] = meta_comment
    f["display_name"] = display or (DIMS[dim]["display_name"] if dim and name == dim else title(name))
    if dim and name == dim:
        f["synonyms"] = DIMS[dim]["synonyms"][:10]
    return f


def measure(name, expr, metric_id=None, comment=None, display=None, fmt_key=None, window=None, synonyms=None):
    m = {"name": name, "expr": expr}
    meta = METRICS.get(metric_id) if metric_id else None
    if comment or meta:
        m["comment"] = comment or meta["description"]
    m["display_name"] = display or (meta["display_name"] if meta else title(name))
    key = fmt_key or (meta["format"] if meta else None)
    if key:
        m["format"] = fmt(key)
    syn = synonyms if synonyms is not None else (meta["synonyms"] if meta else None)
    if syn:
        m["synonyms"] = syn[:10]
    if window:
        m["window"] = window
    return m


def join(name, source, on, joins=None, cardinality=None, rely=True):
    j = {"name": name, "source": source, "on": on}
    if cardinality:
        j["cardinality"] = cardinality
    if rely:
        j["rely"] = {"at_most_one_match": True}
    if joins:
        j["joins"] = joins
    return j


def ratio(num: str, den: str) -> str:
    return f"CAST(MEASURE({num}) AS DOUBLE) / NULLIF(CAST(MEASURE({den}) AS DOUBLE), 0)"


# --------------------------------------------------------------------------- shared WWI pieces

def wwi_calendar_fields(prefix: str, date_field: str, role_dim: str) -> list[dict]:
    """Calendar attributes from a dim_date join (used only in views without window measures)."""
    return [
        field(date_field, f"source.{date_field}", dim=role_dim if role_dim == date_field else None,
              comment=DIMS["date"]["description"] if role_dim == "date" else None),
        field("calendar_year", f"{prefix}.calendar_year"),
        field("calendar_quarter", f"{prefix}.calendar_quarter"),
        field("calendar_month", f"{prefix}.calendar_month"),
        field("month_name", f"{prefix}.month_name"),
        field("month_start_date", f"{prefix}.month_start_date"),
        field("fiscal_year", f"{prefix}.fiscal_year", comment="Fiscal year starting 1 November, labeled by the year in which it ends."),
        field("fiscal_quarter", f"{prefix}.fiscal_quarter"),
        field("fiscal_month", f"{prefix}.fiscal_month", comment="Fiscal month, November = 1."),
        field("day_of_week", f"{prefix}.day_of_week", comment="ISO day of week, Monday = 1."),
    ]


def customer_fields() -> list[dict]:
    return [
        field("customer", "cust.customer", dim="customer"),
        field("customer_category", "cust.category"),
        field("buying_group", "cust.buying_group"),
    ]


def city_fields() -> list[dict]:
    return [
        field("city", "geo.city", dim="city"),
        field("state_province", "geo.state_province"),
        field("country", "geo.country"),
        field("continent", "geo.continent"),
        field("sales_territory", "geo.sales_territory", comment="Sales territory of the delivery city at the time of sale."),
        field("region", "geo.region"),
        field("subregion", "geo.subregion"),
    ]


def item_fields(prefix: str = "item", current: str | None = None) -> list[dict]:
    out = [
        field("stock_item", f"{prefix}.stock_item", dim="stock_item"),
        field("wwi_stock_item_id", f"{prefix}.wwi_stock_item_id", comment="Durable stock item id (stable across SCD Type 2 versions)."),
        field("brand", f"{prefix}.brand"),
        field("color", f"{prefix}.color", comment="Color as recorded at the time of the fact (as-was)."),
        field("size", f"{prefix}.size"),
        field("selling_package", f"{prefix}.selling_package"),
        field("is_chiller_stock", f"{prefix}.is_chiller_stock"),
    ]
    if current:
        out.append(field("current_color", f"{current}.color", comment="Color of the current version of the stock item (as-is)."))
    return out


def dim(table: str) -> str:
    return f"{CATALOG}.wwi.{table}"


ITEM_JOIN = join(
    "item", dim("dim_stock_item"), "source.stock_item_key = item.stock_item_key",
    joins=[join("item_current", dim("dim_stock_item"),
                "item.wwi_stock_item_id = item_current.wwi_stock_item_id AND item_current.is_current")],
)

SALE_JOINS = [
    join("inv_cal", dim("dim_date"), "source.invoice_date = inv_cal.date_key"),
    join("dlv_cal", dim("dim_date"), "source.delivery_date = dlv_cal.date_key"),
    join("cust", dim("dim_customer"), "source.customer_key = cust.customer_key"),
    join("bill_cust", dim("dim_customer"), "source.bill_to_customer_key = bill_cust.customer_key"),
    join("geo", dim("dim_city"), "source.city_key = geo.city_key"),
    ITEM_JOIN,
    join("rep", dim("dim_employee"), "source.salesperson_key = rep.employee_key"),
]

SALE_FIELDS = (
    wwi_calendar_fields("inv_cal", "invoice_date", "date")
    + [
        field("delivery_date", "source.delivery_date", dim="delivery_date"),
        field("delivery_year", "dlv_cal.calendar_year"),
        field("delivery_month_start_date", "dlv_cal.month_start_date"),
    ]
    + customer_fields()
    + [field("bill_to_customer", "bill_cust.customer", dim="bill_to_customer")]
    + city_fields()
    + item_fields("item", "item.item_current")
    + [field("salesperson", "rep.employee", dim="salesperson")]
)

SALE_MEASURES = [
    measure("revenue", "SUM(total_excluding_tax)", "W-S1"),
    measure("revenue_including_tax", "SUM(total_including_tax)", "B-W1"),
    measure("gross_profit", "SUM(profit)", "B-W2"),
    measure("units_sold", "SUM(quantity)", "B-W3"),
    measure("invoice_count", "COUNT(DISTINCT wwi_invoice_id)", "B-W4"),
    measure("gross_margin_pct", ratio("gross_profit", "revenue"), "W-M1"),
]

ORDER_JOINS = [
    join("ord_cal", dim("dim_date"), "source.order_date = ord_cal.date_key"),
    join("cust", dim("dim_customer"), "source.customer_key = cust.customer_key"),
    join("geo", dim("dim_city"), "source.city_key = geo.city_key"),
    ITEM_JOIN,
    join("rep", dim("dim_employee"), "source.salesperson_key = rep.employee_key"),
    join("picker_emp", dim("dim_employee"), "source.picker_key = picker_emp.employee_key"),
]

ORDER_FIELDS = (
    wwi_calendar_fields("ord_cal", "order_date", "date")
    + customer_fields()
    + city_fields()
    + item_fields("item", "item.item_current")
    + [
        field("salesperson", "rep.employee", dim="salesperson"),
        field("picker", "picker_emp.employee", dim="picker"),
    ]
)

ORDER_MEASURES = [
    measure("ordered_quantity", "SUM(quantity)", "W-S2"),
    measure("backordered_order_lines", "NULLIF(COUNT(wwi_backorder_id), 0)", "B-W5"),
]

GROUP_FIELD = field("stock_group", "grp.stock_group_name", dim="stock_group")
GROUP_JOIN = join("grp", dim("dim_stock_group"), "source.stock_group_id = grp.stock_group_id")
ALL_GROUPS = [{"order": "stock_group", "range": "all"}]


def bridged_source(fact: str, key: str) -> str:
    """Fact lines expanded to one row per stock group of the line's item; is_first_group marks one row per line."""
    return (
        f"SELECT f.*, b.stock_group_id,\n"
        f"  b.stock_group_id = MIN(b.stock_group_id) OVER (PARTITION BY f.{key}) AS is_first_group\n"
        f"FROM {dim(fact)} f\n"
        f"JOIN {dim('dim_stock_item')} si ON si.stock_item_key = f.stock_item_key\n"
        f"JOIN {dim('bridge_stock_item_group')} b ON b.wwi_stock_item_id = si.wwi_stock_item_id\n"
    )


# --------------------------------------------------------------------------- stock (window) pieces

SNAP_DAILY = (
    f"SELECT h.snapshot_date, h.wwi_stock_item_id, h.stock_item_key, h.quantity_on_hand, h.balance_basis,\n"
    f"  s.units_sold\n"
    f"FROM {dim('fact_stock_holding_daily')} h\n"
    f"LEFT JOIN (\n"
    f"  SELECT si.wwi_stock_item_id, f.invoice_date, SUM(f.quantity) AS units_sold\n"
    f"  FROM {dim('fact_sale')} f\n"
    f"  JOIN {dim('dim_stock_item')} si ON si.stock_item_key = f.stock_item_key\n"
    f"  GROUP BY si.wwi_stock_item_id, f.invoice_date\n"
    f") s ON s.wwi_stock_item_id = h.wwi_stock_item_id AND s.invoice_date = h.snapshot_date\n"
)


def snapshot_time_fields() -> list[dict]:
    # Window hierarchy levels are expressions over the order field (snapshot_date), never over dim columns.
    return [
        field("snapshot_date", "source.snapshot_date", comment="Snapshot date; the order field of every window measure in this view."),
        field("snapshot_year", "CAST(DATE_TRUNC('YEAR', snapshot_date) AS DATE)", comment="First day of the snapshot's calendar year."),
        field("snapshot_quarter", "CAST(DATE_TRUNC('QUARTER', snapshot_date) AS DATE)", comment="First day of the snapshot's calendar quarter."),
        field("snapshot_month", "CAST(DATE_TRUNC('MONTH', snapshot_date) AS DATE)", comment="First day of the snapshot's calendar month."),
        field("snapshot_fiscal_year", "YEAR(snapshot_date) + CASE WHEN MONTH(snapshot_date) >= 11 THEN 1 ELSE 0 END",
              comment="Fiscal year (starting 1 November) of the snapshot date."),
    ]


CLOSING = [{"order": "snapshot_date", "range": "current", "semiadditive": "last"}]
TRAILING_91 = [{"order": "snapshot_date", "range": "trailing 91 day inclusive", "semiadditive": "last"}]

STOCK_MEASURES = [
    measure("closing_units", "SUM(quantity_on_hand)", "W-M2", window=CLOSING),
    measure("units_sold_91d", "SUM(units_sold)", comment="Units sold in the 91 days ending on the period end (t - 90 .. t).",
            display="Units Sold (Trailing 91 Days)", fmt_key="units", window=TRAILING_91, synonyms=["91 day sales", "trailing quarter sales"]),
    measure("days_of_supply", "CAST(MEASURE(closing_units) AS DOUBLE) / NULLIF(CAST(MEASURE(units_sold_91d) AS DOUBLE) / 91, 0)", "W-C2"),
]

# --------------------------------------------------------------------------- NYC pieces

def zone_join(name: str, column: str) -> dict:
    return join(name, f"{CATALOG}.nyctaxi.dim_zone", f"source.{column} = {name}.location_id")


TRIP_FIELDS = [
    field("pickup_date", "source.pickup_date", dim="pickup_date"),
    field("pickup_year", "CAST(DATE_TRUNC('YEAR', pickup_date) AS DATE)", comment="First day of the pickup calendar year; YTD windows reset here."),
    field("pickup_quarter", "CAST(DATE_TRUNC('QUARTER', pickup_date) AS DATE)", comment="First day of the pickup calendar quarter."),
    field("pickup_month", "CAST(DATE_TRUNC('MONTH', pickup_date) AS DATE)", comment="First day of the pickup calendar month; MTD windows reset here."),
    field("pickup_day_of_week", "pickup_cal.day_of_week", comment="ISO day of week of the pickup date, Monday = 1."),
    field("pickup_day_name", "pickup_cal.day_name"),
    field("pickup_hour", "source.pickup_hour", dim="pickup_hour"),
    field("dropoff_date", "source.dropoff_date", dim="dropoff_date"),
    field("dropoff_year", "YEAR(dropoff_date)", comment="Calendar year of the dropoff date."),
    field("dropoff_month", "CAST(DATE_TRUNC('MONTH', dropoff_date) AS DATE)", comment="First day of the dropoff calendar month."),
    field("pickup_zone_id", "source.pu_location_id", comment="TLC location id of the pickup zone."),
    field("pickup_zone", "pu.zone", dim="pickup_zone"),
    field("pickup_borough", "pu.borough", comment="Borough of the pickup zone."),
    field("pickup_service_zone", "pu.service_zone", comment="TLC service zone of the pickup zone (Yellow Zone, Boro Zone, Airports, EWR)."),
    field("dropoff_zone_id", "source.do_location_id", comment="TLC location id of the dropoff zone."),
    field("dropoff_zone", "dz.zone", dim="dropoff_zone"),
    field("dropoff_borough", "dz.borough", comment="Borough of the dropoff zone."),
    field("dropoff_service_zone", "dz.service_zone"),
    field("payment_type", "source.payment_type", comment="TLC payment type code.", display="Payment Type Code"),
    field("payment_type_name", "pay.payment_type_name", dim="payment_type", display="Payment Type"),
    field("vendor_id", "source.vendor_id", dim="vendor", display="Vendor"),
]
# payment_type_name and vendor_id carry their dimension's metadata.
for f_ in TRIP_FIELDS:
    if f_["name"] == "payment_type_name":
        f_["comment"], f_["synonyms"] = DIMS["payment_type"]["description"], DIMS["payment_type"]["synonyms"]
    if f_["name"] == "vendor_id":
        f_["comment"], f_["synonyms"] = DIMS["vendor"]["description"], DIMS["vendor"]["synonyms"]

YTD = [{"order": "pickup_date", "range": "cumulative"}, {"order": "pickup_year", "range": "current"}]
STLY = [
    {"order": "pickup_date", "range": "cumulative", "offset": "-1 year"},
    {"order": "pickup_year", "range": "current", "offset": "-1 year"},
]
MTD = [{"order": "pickup_date", "range": "cumulative"}, {"order": "pickup_month", "range": "current"}]
AT_PERIOD_END = [{"order": "pickup_date", "range": "current", "semiadditive": "last"}]

TRIP_MEASURES = [
    measure("trip_count", "COUNT(1)", "B-N1"),
    measure("total_trip_distance", "SUM(trip_distance)", "B-N2"),
    measure("fare_amount", "SUM(source.fare_amount)", "B-N3"),
    measure("tip_amount", "SUM(source.tip_amount)", "B-N4"),
    measure("tolls_amount", "SUM(source.tolls_amount)", "B-N5"),
    measure("gross_trip_revenue", "SUM(total_amount)", "N-S1"),
    measure("card_tips", "SUM(source.tip_amount) FILTER (WHERE source.payment_type = 1)", "N-S2"),
    measure("distinct_od_pairs", "COUNT(DISTINCT od_pair_id)", "N-M1"),
    measure("fare_per_mile", ratio("fare_amount", "total_trip_distance"), "N-M2"),
    measure("revenue_ytd", "SUM(total_amount)", "N-C1", display="Revenue YTD", window=YTD,
            comment="Gross Trip Revenue from 1 January of the pickup year to the last pickup date in context.",
            synonyms=["year to date revenue", "YTD revenue"]),
    measure("revenue_stly_ytd", "SUM(total_amount)", display="Revenue YTD Same Time Last Year", fmt_key="currency", window=STLY,
            comment="Revenue YTD shifted back one year along the pickup date (29 February maps to 28 February).",
            synonyms=["STLY revenue", "last year YTD", "prior year to date revenue", "same time last year"]),
    measure("revenue_yoy_pct", "(CAST(MEASURE(revenue_ytd) AS DOUBLE) - CAST(MEASURE(revenue_stly_ytd) AS DOUBLE)) "
            "/ NULLIF(CAST(MEASURE(revenue_stly_ytd) AS DOUBLE), 0)", display="Revenue YoY % vs STLY", fmt_key="ratio_pct",
            comment="Year-over-year change of Revenue YTD against the same period last year.",
            synonyms=["YoY growth", "year over year", "growth vs last year"]),
    measure("trips_mtd", "COUNT(1)", display="Trips MTD", fmt_key="count", window=MTD,
            comment="Trips from the first day of the pickup month to the last pickup date in context.", synonyms=["month to date trips"]),
    measure("trips_ytd", "COUNT(1)", display="Trips YTD", fmt_key="count", window=YTD,
            comment="Trips from 1 January of the pickup year to the last pickup date in context.", synonyms=["year to date trips"]),
    measure("days_elapsed_in_month", "MAX(DAYOFMONTH(pickup_date))", display="Days Elapsed in Month", fmt_key="count",
            window=AT_PERIOD_END, comment="Day of month of the last pickup date in context (calendar days elapsed).", synonyms=[]),
    measure("days_elapsed_in_year", "MAX(DAYOFYEAR(pickup_date))", display="Days Elapsed in Year", fmt_key="count",
            window=AT_PERIOD_END, comment="Day of year of the last pickup date in context (calendar days elapsed).", synonyms=[]),
    measure("pace_index", "(CAST(MEASURE(trips_mtd) AS DOUBLE) / MEASURE(days_elapsed_in_month)) "
            "/ NULLIF(CAST(MEASURE(trips_ytd) AS DOUBLE) / MEASURE(days_elapsed_in_year), 0)", "N-C2"),
]

# --------------------------------------------------------------------------- views

VIEWS: dict[str, dict] = {
    "wwi_sales": {
        "version": SPEC_VERSION,
        "comment": "WideWorldImporters sales at invoice line grain (W-S1, W-M1, B-W1 to B-W4). Stock group analysis: wwi_sales_by_stock_group.",
        "source": dim("fact_sale"),
        "joins": SALE_JOINS,
        "fields": SALE_FIELDS,
        "measures": SALE_MEASURES,
    },
    "wwi_sales_by_stock_group": {
        "version": SPEC_VERSION,
        "comment": "Sales expanded to one row per stock group of each line's item (W-C1). Group revenues overlap; "
                   "revenue_all_groups and revenue_deduplicated count each line once.",
        "source": bridged_source("fact_sale", "sale_key"),
        "joins": SALE_JOINS + [GROUP_JOIN],
        "fields": SALE_FIELDS + [GROUP_FIELD],
        "measures": SALE_MEASURES + [
            measure("revenue_deduplicated", "SUM(total_excluding_tax) FILTER (WHERE is_first_group)",
                    display="Revenue (Deduplicated Across Groups)", fmt_key="currency",
                    comment="Revenue counting each sale line once; use without grouping by stock group for the true total.",
                    synonyms=["total revenue", "deduplicated revenue"]),
            measure("revenue_all_groups", "SUM(total_excluding_tax) FILTER (WHERE is_first_group)",
                    display="Revenue (All Groups in Context)", fmt_key="currency", window=ALL_GROUPS,
                    comment="Deduplicated revenue of the context with the stock group removed (coarser level of detail).",
                    synonyms=[]),
            measure("stock_group_revenue_share", ratio("revenue", "revenue_all_groups"), "W-C1"),
        ],
    },
    "wwi_orders": {
        "version": SPEC_VERSION,
        "comment": "WideWorldImporters orders at order line grain (W-S2, B-W5), dated by order date.",
        "source": dim("fact_order"),
        "joins": ORDER_JOINS,
        "fields": ORDER_FIELDS,
        "measures": ORDER_MEASURES,
    },
    "wwi_orders_by_stock_group": {
        "version": SPEC_VERSION,
        "comment": "Orders expanded to one row per stock group of each line's item. backordered_lines_deduplicated counts each line once.",
        "source": bridged_source("fact_order", "order_key"),
        "joins": ORDER_JOINS + [GROUP_JOIN],
        "fields": ORDER_FIELDS + [GROUP_FIELD],
        "measures": ORDER_MEASURES + [
            measure("backordered_lines_deduplicated", "NULLIF(COUNT(wwi_backorder_id) FILTER (WHERE is_first_group), 0)",
                    display="Backordered Order Lines (Deduplicated)", fmt_key="count",
                    comment="Backordered order lines counting each line once across stock groups.", synonyms=[]),
            measure("backordered_lines_all_groups", "NULLIF(COUNT(wwi_backorder_id) FILTER (WHERE is_first_group), 0)",
                    display="Backordered Order Lines (All Groups in Context)", fmt_key="count", window=ALL_GROUPS,
                    comment="Deduplicated backordered lines of the context with the stock group removed.", synonyms=[]),
        ],
    },
    "wwi_stock": {
        "version": SPEC_VERSION,
        "comment": "Daily stock snapshot per stock item with same-day units sold (W-M2, W-C2). The source pre-joins the two facts "
                   "at their shared grain (date, item); dimensions without a stock relationship are not exposed.",
        "source": SNAP_DAILY,
        "joins": [join("item", dim("dim_stock_item"), "source.stock_item_key = item.stock_item_key")],
        "fields": snapshot_time_fields() + item_fields("item") + [
            field("balance_basis", "source.balance_basis",
                  comment="holding_backcast: reconciled to the current holding; flow_min_opening: derived from movements only (SPEC § 5.3 rule 6)."),
        ],
        "measures": STOCK_MEASURES,
    },
    "wwi_stock_by_stock_group": {
        "version": SPEC_VERSION,
        "comment": "Daily stock snapshot expanded to one row per stock group of each item (W-M2, W-C2 by stock group). Group values overlap.",
        "source": (
            "SELECT d.*, b.stock_group_id\nFROM (\n" + "\n".join("  " + l for l in SNAP_DAILY.strip().splitlines()) +
            f"\n) d\nJOIN {dim('bridge_stock_item_group')} b ON b.wwi_stock_item_id = d.wwi_stock_item_id\n"
        ),
        "joins": [join("item", dim("dim_stock_item"), "source.stock_item_key = item.stock_item_key"), GROUP_JOIN],
        "fields": snapshot_time_fields() + item_fields("item") + [GROUP_FIELD],
        "measures": STOCK_MEASURES,
    },
    "nyc_trips": {
        "version": SPEC_VERSION,
        "comment": "NYC Yellow Taxi trips (B-N1 to B-N5, N-S1, N-S2, N-M1, N-M2, N-C1, N-C2). Pickup and dropoff zones and dates are role-played.",
        "source": f"{CATALOG}.nyctaxi.fact_trip",
        "joins": [
            join("pickup_cal", f"{CATALOG}.nyctaxi.dim_date", "source.pickup_date = pickup_cal.date_key"),
            zone_join("pu", "pu_location_id"),
            zone_join("dz", "do_location_id"),
            join("pay", f"{CATALOG}.nyctaxi.dim_payment_type", "source.payment_type = pay.payment_type"),
        ],
        "fields": TRIP_FIELDS,
        "measures": TRIP_MEASURES,
    },
}

# Materializations for the accelerated profile (no row-level security on the sources, SPEC B-01).
MATERIALIZATION = {
    "nyc_trips": {
        "schedule": "every 1 hour",
        "mode": "relaxed",
        "materialized_views": [{
            "name": "daily_trip_cube",
            "type": "aggregated",
            "dimensions": ["pickup_date", "pickup_hour", "pickup_borough", "dropoff_borough", "payment_type_name", "vendor_id"],
            "measures": ["trip_count", "total_trip_distance", "fare_amount", "tip_amount", "tolls_amount",
                         "gross_trip_revenue", "card_tips"],
            "cluster_by": {"cols": ["pickup_date"]},
            "refresh_policy": "auto",
        }],
    },
    "wwi_sales": {
        "schedule": "every 1 hour",
        "mode": "relaxed",
        "materialized_views": [{
            "name": "daily_sales_cube",
            "type": "aggregated",
            "dimensions": ["invoice_date", "sales_territory", "customer_category", "stock_item", "salesperson"],
            "measures": ["revenue", "revenue_including_tax", "gross_profit", "units_sold"],
            "cluster_by": {"cols": ["invoice_date"]},
            "refresh_policy": "auto",
        }],
    },
}

# --------------------------------------------------------------------------- rendering


def _key(text: str) -> str:
    return text.lower().replace("_", " ").strip()


def clean_synonyms(view: str, doc: dict) -> None:
    """Drop synonyms that name another field or measure of the view; reject a synonym shared by two members."""
    members = doc.get("fields", []) + doc.get("measures", [])
    owners: dict[str, str] = {}
    for m in members:
        owners[_key(m["name"])] = m["name"]
        owners[_key(m["display_name"])] = m["name"]
    seen: dict[str, str] = {}
    for m in members:
        if "synonyms" not in m:
            continue
        kept = [s for s in m["synonyms"] if owners.get(_key(s), m["name"]) == m["name"]]
        for s in kept:
            if _key(s) in seen:
                raise ValueError(f"{view}: synonym {s!r} on both {seen[_key(s)]} and {m['name']}")
            seen[_key(s)] = m["name"]
        if kept:
            m["synonyms"] = kept
        else:
            del m["synonyms"]


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str)


def to_yaml(doc: dict) -> str:
    return yaml.dump(doc, Dumper=_Dumper, sort_keys=False, width=120, allow_unicode=True)


def header(view: str) -> str:
    return (
        f"# Metric view {SCHEMA}.{view}. Generated by build_metric_views.py from its view definitions and\n"
        f"# 01-spec/glossary.yaml; edit the builder, not this file. YAML specification {SPEC_VERSION}.\n"
    )


def ddl(view: str, body: str, profile: str) -> str:
    return (
        f"-- {SCHEMA}.{view} ({profile} profile). Generated by build_metric_views.py.\n"
        f"CREATE OR REPLACE VIEW {SCHEMA}.{view}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{body}$$;\n"
    )


def outputs() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for view, doc in VIEWS.items():
        clean_synonyms(view, doc)
        body = to_yaml(doc)
        files[HERE / "metric_views" / f"{view}.yaml"] = header(view) + body
        files[HERE / "sql" / "governed" / f"{view}.sql"] = ddl(view, body, "governed")
        accel = dict(doc)
        if view in MATERIALIZATION:
            accel["materialization"] = MATERIALIZATION[view]
        files[HERE / "sql" / "accelerated" / f"{view}.sql"] = ddl(view, to_yaml(accel), "accelerated")
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, text in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(HERE)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print(f"stale generated files: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
