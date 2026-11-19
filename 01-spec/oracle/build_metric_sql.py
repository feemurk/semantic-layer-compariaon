#!/usr/bin/env python3
"""Render the oracle SQL for the 17 metrics that are a single aggregate over one fact.

Output contract for every metrics/*.sql file (generated or hand-written):
  grain     STRING  reconciliation grain label (see GRAINS below)
  measure   STRING  metric id, or metric id + ':' + component for multi-output metrics
  member_1..member_3 STRING  members of the grain's attributes, NULL when unused
  value     the metric value (BIGINT for counts, DECIMAL for sums, DOUBLE for ratios)
Rows are ordered by grain, measure, member_1, member_2, member_3 (NULLS FIRST).

Grains cover each applicable dimension of the SPEC § 6.5 matrix at its top attribute
(and at the leaf member where the member set is bounded) crossed with calendar year,
plus the time hierarchy (total, year, month, day). Dimensions marked N in the matrix
are not emitted: the NULL expectation for them follows from the matrix itself.

Hand-written metric files (not rendered here): W-M2, W-C1, W-C2, N-C1, N-C2.

    python build_metric_sql.py          # writes metrics/*.sql
    python build_metric_sql.py --check  # exit 1 if committed files differ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "metrics"

SALE_BASE = """\
base AS (
  SELECT f.total_excluding_tax, f.total_including_tax, f.profit, f.quantity, f.wwi_invoice_id,
         f.invoice_date, d.calendar_year, d.month_start_date, d.fiscal_year,
         dd.calendar_year AS delivery_year,
         c.category AS customer_category, c.customer AS customer_name,
         bt.customer AS bill_to_customer_name,
         ci.sales_territory, ci.state_province,
         si.wwi_stock_item_id, si.stock_item, si.color,
         e.employee AS salesperson
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  LEFT JOIN wwi.dim_date dd ON dd.date_key = f.delivery_date
  JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
  JOIN wwi.dim_customer bt ON bt.customer_key = f.bill_to_customer_key
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  JOIN wwi.dim_employee e ON e.employee_key = f.salesperson_key
)"""

ORDER_BASE = """\
base AS (
  SELECT f.quantity, f.wwi_backorder_id,
         f.order_date, d.calendar_year, d.month_start_date, d.fiscal_year,
         c.category AS customer_category, c.customer AS customer_name,
         ci.sales_territory, ci.state_province,
         si.wwi_stock_item_id, si.stock_item,
         e.employee AS salesperson,
         p.employee AS picker
  FROM wwi.fact_order f
  JOIN wwi.dim_date d ON d.date_key = f.order_date
  JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  JOIN wwi.dim_employee e ON e.employee_key = f.salesperson_key
  LEFT JOIN wwi.dim_employee p ON p.employee_key = f.picker_key
)"""

TRIP_BASE = """\
base AS (
  SELECT f.total_amount, f.fare_amount, f.tip_amount, f.tolls_amount, f.trip_distance,
         f.payment_type, f.od_pair_id, f.pickup_hour, f.vendor_id,
         f.pickup_date, pd.calendar_year, pd.month_start_date,
         dd.calendar_year AS dropoff_year, dd.month_start_date AS dropoff_month,
         pz.borough AS pickup_borough, f.pu_location_id,
         dz.borough AS dropoff_borough, f.do_location_id,
         pt.payment_type_name
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date pd ON pd.date_key = f.pickup_date
  JOIN nyctaxi.dim_date dd ON dd.date_key = f.dropoff_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
  JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
)"""

GROUP_JOIN = (
    "base JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = base.wwi_stock_item_id "
    "JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id"
)

# (grain, member expressions, FROM clause override)
TIME = [("total", []), ("year", ["calendar_year"]), ("month", ["month_start_date"])]

GRAINS = {
    "sale": TIME + [
        ("day", ["invoice_date"]),
        ("fiscal_year", ["fiscal_year"]),
        ("delivery_year", ["delivery_year"]),
        ("year_customer_category", ["calendar_year", "customer_category"]),
        ("year_customer", ["calendar_year", "customer_name"]),
        ("year_bill_to_customer", ["calendar_year", "bill_to_customer_name"]),
        ("year_sales_territory", ["calendar_year", "sales_territory"]),
        ("year_state_province", ["calendar_year", "state_province"]),
        ("year_stock_item", ["calendar_year", "stock_item"]),
        ("year_color", ["calendar_year", "color"]),
        ("year_salesperson", ["calendar_year", "salesperson"]),
        ("year_stock_group", ["calendar_year", "g.stock_group_name"], GROUP_JOIN),
    ],
    "order": TIME + [
        ("day", ["order_date"]),
        ("fiscal_year", ["fiscal_year"]),
        ("year_customer_category", ["calendar_year", "customer_category"]),
        ("year_customer", ["calendar_year", "customer_name"]),
        ("year_sales_territory", ["calendar_year", "sales_territory"]),
        ("year_state_province", ["calendar_year", "state_province"]),
        ("year_stock_item", ["calendar_year", "stock_item"]),
        ("year_salesperson", ["calendar_year", "salesperson"]),
        ("year_picker", ["calendar_year", "picker"]),
        ("year_stock_group", ["calendar_year", "g.stock_group_name"], GROUP_JOIN),
    ],
    "trip": TIME + [
        ("day", ["pickup_date"]),
        ("dropoff_year", ["dropoff_year"]),
        ("dropoff_month", ["dropoff_month"]),
        ("year_pickup_hour", ["calendar_year", "pickup_hour"]),
        ("year_pickup_borough", ["calendar_year", "pickup_borough"]),
        ("year_pickup_zone", ["calendar_year", "pu_location_id"]),
        ("year_dropoff_borough", ["calendar_year", "dropoff_borough"]),
        ("year_dropoff_zone", ["calendar_year", "do_location_id"]),
        ("year_payment_type", ["calendar_year", "payment_type_name"]),
        ("year_vendor", ["calendar_year", "vendor_id"]),
        ("year_pickup_dropoff_borough", ["calendar_year", "pickup_borough", "dropoff_borough"]),
    ],
}

BASES = {"sale": SALE_BASE, "order": ORDER_BASE, "trip": TRIP_BASE}


def ratio(num: str, den: str) -> str:
    return f"CAST(SUM({num}) AS DOUBLE) / NULLIF(CAST(SUM({den}) AS DOUBLE), 0)"


# metric id -> (base, value expression, SPEC definition line)
METRICS = {
    "B-W1": ("sale", "SUM(total_including_tax)", "Revenue Including Tax = sum(total_including_tax) over fact_sale"),
    "B-W2": ("sale", "SUM(profit)", "Gross Profit = sum(profit) over fact_sale"),
    "B-W3": ("sale", "SUM(quantity)", "Units Sold = sum(quantity) over fact_sale"),
    "B-W4": ("sale", "COUNT(DISTINCT wwi_invoice_id)", "Invoice Count = exact count(distinct wwi_invoice_id)"),
    "B-W5": ("order", "NULLIF(COUNT(wwi_backorder_id), 0)",
             "Backordered Order Lines = count(fact_order rows with wwi_backorder_id not null); NULL when none qualify"),
    "W-S1": ("sale", "SUM(total_excluding_tax)", "Revenue (Excl. Tax) = sum(total_excluding_tax) over fact_sale"),
    "W-S2": ("order", "SUM(quantity)", "Ordered Quantity = sum(quantity) over fact_order, dated by order_date"),
    "W-M1": ("sale", ratio("profit", "total_excluding_tax"),
             "Gross Margin % = sum(profit) / sum(total_excluding_tax); ratio of sums at every grain"),
    "B-N1": ("trip", "COUNT(*)", "Trip Count = count(fact_trip rows)"),
    "B-N2": ("trip", "SUM(trip_distance)", "Total Trip Distance = sum(trip_distance)"),
    "B-N3": ("trip", "SUM(fare_amount)", "Fare Amount = sum(fare_amount)"),
    "B-N4": ("trip", "SUM(tip_amount)", "Tip Amount (All Payment Types) = sum(tip_amount)"),
    "B-N5": ("trip", "SUM(tolls_amount)", "Tolls Amount = sum(tolls_amount)"),
    "N-S1": ("trip", "SUM(total_amount)", "Gross Trip Revenue = sum(total_amount)"),
    "N-S2": ("trip", "SUM(CASE WHEN payment_type = 1 THEN tip_amount END)",
             "Card Tips = sum(tip_amount) where payment_type = 1; NULL when no card trip qualifies"),
    "N-M1": ("trip", "COUNT(DISTINCT od_pair_id)", "Distinct OD Pairs = exact count(distinct od_pair_id)"),
    "N-M2": ("trip", ratio("fare_amount", "trip_distance"), "Fare per Mile = sum(fare_amount) / sum(trip_distance)"),
}


def member(expr: str | None) -> str:
    return "CAST(NULL AS STRING)" if expr is None else f"CAST({expr} AS STRING)"


def render(metric_id: str) -> str:
    base_key, expr, definition = METRICS[metric_id]
    branches = []
    for grain in GRAINS[base_key]:
        name, members = grain[0], grain[1]
        source = grain[2] if len(grain) > 2 else "base"
        cols = (members + [None, None, None])[:3]
        group_by = f"\n  GROUP BY {', '.join(members)}" if members else ""
        branches.append(
            f"  SELECT '{name}' AS grain, '{metric_id}' AS measure, {member(cols[0])} AS member_1, "
            f"{member(cols[1])} AS member_2, {member(cols[2])} AS member_3, {expr} AS value\n"
            f"  FROM {source}{group_by}"
        )
    union = "\n  UNION ALL\n".join(branches)
    return (
        f"-- {metric_id} {definition}\n"
        f"-- Generated by build_metric_sql.py; edit the generator, not this file.\n"
        f"WITH {BASES[base_key]}\n"
        f"SELECT grain, measure, member_1, member_2, member_3, value\n"
        f"FROM (\n{union}\n) r\n"
        f"ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    stale = []
    for metric_id in METRICS:
        path = OUT / f"{metric_id}.sql"
        text = render(metric_id)
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
    if stale:
        print(f"stale generated metric files: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
