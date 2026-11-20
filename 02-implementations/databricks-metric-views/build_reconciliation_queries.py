#!/usr/bin/env python3
"""Generate the E1 reconciliation queries: one MEASURE() query per metric (SPEC § 8 E1, § 9.2).

Each queries/metrics/<ID>.sql reads only the metric views (never the gold tables) and returns the
oracle metric contract (grain, measure, member_1..member_3, value) for exactly the grains and members
of 01-spec/oracle/metrics/<ID>.sql, so results compare row by row with
01-spec/oracle/expected/metrics/<ID>.csv using run_oracle.compare().

    python build_reconciliation_queries.py          # write queries/metrics/*.sql
    python build_reconciliation_queries.py --check  # exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "queries" / "metrics"
MV = "slc.semantic"

S = lambda expr: f"CAST({expr} AS STRING)"  # noqa: E731
YEAR = lambda field: f"CAST(YEAR({field}) AS STRING)"  # noqa: E731

# Grain -> (view suffix, [member expressions], [group-by fields]); view suffix "" = base view, "group" = by_stock_group.
SALE_GRAINS = [
    ("total", "", [], []),
    ("year", "", [S("calendar_year")], ["calendar_year"]),
    ("month", "", [S("month_start_date")], ["month_start_date"]),
    ("day", "", [S("invoice_date")], ["invoice_date"]),
    ("fiscal_year", "", [S("fiscal_year")], ["fiscal_year"]),
    ("delivery_year", "", [S("delivery_year")], ["delivery_year"]),
    ("year_customer_category", "", [S("calendar_year"), "customer_category"], ["calendar_year", "customer_category"]),
    ("year_customer", "", [S("calendar_year"), "customer"], ["calendar_year", "customer"]),
    ("year_bill_to_customer", "", [S("calendar_year"), "bill_to_customer"], ["calendar_year", "bill_to_customer"]),
    ("year_sales_territory", "", [S("calendar_year"), "sales_territory"], ["calendar_year", "sales_territory"]),
    ("year_state_province", "", [S("calendar_year"), "state_province"], ["calendar_year", "state_province"]),
    ("year_stock_item", "", [S("calendar_year"), "stock_item"], ["calendar_year", "stock_item"]),
    ("year_color", "", [S("calendar_year"), "color"], ["calendar_year", "color"]),
    ("year_salesperson", "", [S("calendar_year"), "salesperson"], ["calendar_year", "salesperson"]),
    ("year_stock_group", "group", [S("calendar_year"), "stock_group"], ["calendar_year", "stock_group"]),
]

ORDER_GRAINS = [
    ("total", "", [], []),
    ("year", "", [S("calendar_year")], ["calendar_year"]),
    ("month", "", [S("month_start_date")], ["month_start_date"]),
    ("day", "", [S("order_date")], ["order_date"]),
    ("fiscal_year", "", [S("fiscal_year")], ["fiscal_year"]),
    ("year_customer_category", "", [S("calendar_year"), "customer_category"], ["calendar_year", "customer_category"]),
    ("year_customer", "", [S("calendar_year"), "customer"], ["calendar_year", "customer"]),
    ("year_sales_territory", "", [S("calendar_year"), "sales_territory"], ["calendar_year", "sales_territory"]),
    ("year_state_province", "", [S("calendar_year"), "state_province"], ["calendar_year", "state_province"]),
    ("year_stock_item", "", [S("calendar_year"), "stock_item"], ["calendar_year", "stock_item"]),
    ("year_salesperson", "", [S("calendar_year"), "salesperson"], ["calendar_year", "salesperson"]),
    ("year_picker", "", [S("calendar_year"), "picker"], ["calendar_year", "picker"]),
    ("year_stock_group", "group", [S("calendar_year"), "stock_group"], ["calendar_year", "stock_group"]),
]

TRIP_GRAINS = [
    ("total", "", [], []),
    ("year", "", [YEAR("pickup_year")], ["pickup_year"]),
    ("month", "", [S("pickup_month")], ["pickup_month"]),
    ("day", "", [S("pickup_date")], ["pickup_date"]),
    ("dropoff_year", "", [S("dropoff_year")], ["dropoff_year"]),
    ("dropoff_month", "", [S("dropoff_month")], ["dropoff_month"]),
    ("year_pickup_hour", "", [YEAR("pickup_year"), S("pickup_hour")], ["pickup_year", "pickup_hour"]),
    ("year_pickup_borough", "", [YEAR("pickup_year"), "pickup_borough"], ["pickup_year", "pickup_borough"]),
    ("year_pickup_zone", "", [YEAR("pickup_year"), S("pickup_zone_id")], ["pickup_year", "pickup_zone_id"]),
    ("year_dropoff_borough", "", [YEAR("pickup_year"), "dropoff_borough"], ["pickup_year", "dropoff_borough"]),
    ("year_dropoff_zone", "", [YEAR("pickup_year"), S("dropoff_zone_id")], ["pickup_year", "dropoff_zone_id"]),
    ("year_payment_type", "", [YEAR("pickup_year"), "payment_type_name"], ["pickup_year", "payment_type_name"]),
    ("year_vendor", "", [YEAR("pickup_year"), S("vendor_id")], ["pickup_year", "vendor_id"]),
    ("year_pickup_dropoff_borough", "", [YEAR("pickup_year"), "pickup_borough", "dropoff_borough"],
     ["pickup_year", "pickup_borough", "dropoff_borough"]),
]

STOCK_GRAINS = [
    ("total", "", [], []),
    ("year", "", [YEAR("snapshot_year")], ["snapshot_year"]),
    ("month", "", [S("snapshot_month")], ["snapshot_month"]),
    ("day", "", [S("snapshot_date")], ["snapshot_date"]),
    ("fiscal_year", "", [S("snapshot_fiscal_year")], ["snapshot_fiscal_year"]),
    ("year_stock_item", "", [YEAR("snapshot_year"), "stock_item"], ["snapshot_year", "stock_item"]),
    ("year_color", "", [YEAR("snapshot_year"), "color"], ["snapshot_year", "color"]),
    ("year_stock_group", "group", [YEAR("snapshot_year"), "stock_group"], ["snapshot_year", "stock_group"]),
]
DOS_GRAINS = [g for g in STOCK_GRAINS if g[0] != "year_color"]

TIME_INTEL_GRAINS = [
    ("day", "", [S("pickup_date")], ["pickup_date"]),
    ("month", "", [S("pickup_month")], ["pickup_month"]),
    ("year", "", [YEAR("pickup_year")], ["pickup_year"]),
    ("total", "", [], []),
    ("month_pickup_borough", "", [S("pickup_month"), "pickup_borough"], ["pickup_month", "pickup_borough"]),
    ("month_payment_type", "", [S("pickup_month"), "payment_type_name"], ["pickup_month", "payment_type_name"]),
    ("month_vendor", "", [S("pickup_month"), S("vendor_id")], ["pickup_month", "vendor_id"]),
    ("month_pickup_hour", "", [S("pickup_month"), S("pickup_hour")], ["pickup_month", "pickup_hour"]),
]

W_C1_GRAINS = [
    ("total_stock_group", [("stock_group")], ["stock_group"]),
    ("total_all_groups", [], []),
    ("year_stock_group", [S("calendar_year"), "stock_group"], ["calendar_year", "stock_group"]),
    ("year_all_groups", [S("calendar_year")], ["calendar_year"]),
    ("fiscal_year_stock_group", [S("fiscal_year"), "stock_group"], ["fiscal_year", "stock_group"]),
    ("year_sales_territory_stock_group", [S("calendar_year"), "sales_territory", "stock_group"],
     ["calendar_year", "sales_territory", "stock_group"]),
    ("year_customer_category_stock_group", [S("calendar_year"), "customer_category", "stock_group"],
     ["calendar_year", "customer_category", "stock_group"]),
]

# Metric -> (base view, by-stock-group view, grains, [(measure label, value expression)])
SIMPLE = {
    "B-W1": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(revenue_including_tax)"),
    "B-W2": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(gross_profit)"),
    "B-W3": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(units_sold)"),
    "B-W4": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(invoice_count)"),
    "W-S1": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(revenue)"),
    "W-M1": ("wwi_sales", "wwi_sales_by_stock_group", SALE_GRAINS, "MEASURE(gross_margin_pct)"),
    "B-W5": ("wwi_orders", "wwi_orders_by_stock_group", ORDER_GRAINS, "MEASURE(backordered_order_lines)"),
    "W-S2": ("wwi_orders", "wwi_orders_by_stock_group", ORDER_GRAINS, "MEASURE(ordered_quantity)"),
    "B-N1": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(trip_count)"),
    "B-N2": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(total_trip_distance)"),
    "B-N3": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(fare_amount)"),
    "B-N4": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(tip_amount)"),
    "B-N5": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(tolls_amount)"),
    "N-S1": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(gross_trip_revenue)"),
    "N-S2": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(card_tips)"),
    "N-M1": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(distinct_od_pairs)"),
    "N-M2": ("nyc_trips", None, TRIP_GRAINS, "MEASURE(fare_per_mile)"),
}

MULTI = {
    "W-M2": ("wwi_stock", "wwi_stock_by_stock_group", STOCK_GRAINS, [("W-M2", "MEASURE(closing_units)")]),
    "W-C2": ("wwi_stock", "wwi_stock_by_stock_group", DOS_GRAINS, [
        ("W-C2", "MEASURE(days_of_supply)"),
        ("W-C2:closing_units", "CAST(MEASURE(closing_units) AS DOUBLE)"),
        ("W-C2:units_sold_91d", "CAST(MEASURE(units_sold_91d) AS DOUBLE)"),
    ]),
    "N-C1": ("nyc_trips", None, TIME_INTEL_GRAINS, [
        ("N-C1:ytd_revenue", "CAST(MEASURE(revenue_ytd) AS DOUBLE)"),
        ("N-C1:stly_ytd_revenue", "CAST(MEASURE(revenue_stly_ytd) AS DOUBLE)"),
        ("N-C1:yoy_pct", "MEASURE(revenue_yoy_pct)"),
    ]),
    "N-C2": ("nyc_trips", None, TIME_INTEL_GRAINS, [
        ("N-C2", "MEASURE(pace_index)"),
        ("N-C2:mtd_trips", "CAST(MEASURE(trips_mtd) AS DOUBLE)"),
        ("N-C2:ytd_trips", "CAST(MEASURE(trips_ytd) AS DOUBLE)"),
    ]),
}


def members(exprs: list[str]) -> str:
    cols = (exprs + ["CAST(NULL AS STRING)"] * 3)[:3]
    return ", ".join(f"{c} AS member_{i + 1}" for i, c in enumerate(cols))


def branch(grain: str, measure_label: str, view: str, member_exprs: list[str], group_by: list[str], value: str) -> str:
    gb = f"\n  GROUP BY {', '.join(group_by)}" if group_by else ""
    return (f"  SELECT '{grain}' AS grain, '{measure_label}' AS measure, {members(member_exprs)}, {value} AS value\n"
            f"  FROM {MV}.{view}{gb}")


def render(metric_id: str) -> str:
    branches = []
    if metric_id in SIMPLE:
        base, by_group, grains, value = SIMPLE[metric_id]
        for grain, which, exprs, gb in grains:
            branches.append(branch(grain, metric_id, by_group if which == "group" else base, exprs, gb, value))
    elif metric_id == "W-C1":
        view = "wwi_sales_by_stock_group"
        for grain, exprs, gb in W_C1_GRAINS:
            value = ("CAST(MEASURE(revenue_deduplicated) AS DOUBLE) / NULLIF(CAST(MEASURE(revenue_all_groups) AS DOUBLE), 0)"
                     if grain.endswith("all_groups") else "MEASURE(stock_group_revenue_share)")
            branches.append(branch(grain, "W-C1", view, exprs, gb, value))
    else:
        base, by_group, grains, measures = MULTI[metric_id]
        for grain, which, exprs, gb in grains:
            for label, value in measures:
                branches.append(branch(grain, label, by_group if which == "group" else base, exprs, gb, value))
    union = "\n  UNION ALL\n".join(branches)
    return (
        f"-- {metric_id} E1 reconciliation through the metric views (contract of 01-spec/oracle/metrics/{metric_id}.sql).\n"
        f"-- Generated by build_reconciliation_queries.py; edit the generator, not this file.\n"
        f"SELECT grain, measure, member_1, member_2, member_3, value\n"
        f"FROM (\n{union}\n) r\n"
        f"ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST\n"
    )


ALL_METRICS = list(SIMPLE) + ["W-C1"] + list(MULTI)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for metric_id in ALL_METRICS:
        path, text = OUT / f"{metric_id}.sql", render(metric_id)
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
    if stale:
        print(f"stale reconciliation queries: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
