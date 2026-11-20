#!/usr/bin/env python3
"""Generate the E1 reconciliation queries of S1 (queries/metrics/<ID>.mdx) for the oracle contract.

Each file is a sequence of MDX statements, one per oracle grain, each preceded by a directive:

    // @branch grain=<grain> rows=<hierarchy>;<hierarchy> values=<measure label>:<[Measures].[Name]>,...

scripts/reconcile.ps1 runs each statement and flattens the cell set into the contract
(grain, measure, member_1, member_2, member_3, value): member_i is the caption of the i-th row hierarchy (an All
member flattens to NULL), and every value column becomes one contract row with its measure label. Grains and member
formats follow 01-spec/oracle/metrics/<ID>.sql. Rows use NonEmpty against the metric's measures: an absent row is
equivalent to a NULL value (SPEC § 5.3 rule 7).

    python3 build_reconciliation_queries.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "queries" / "metrics"

# Row hierarchies by grain token. Unknown members (NULL delivery date, NULL picker) are added explicitly.
H = {
    "calendar_year": "[Date].[Calendar Year]",
    "month": "[Date].[Month]",
    "date": "[Date].[Date]",
    "fiscal_year": "[Date].[Fiscal Year]",
    "delivery_year": "[Delivery Date].[Calendar Year]",
    "customer_category": "[Customer].[Category]",
    "customer": "[Customer].[Customer]",
    "bill_to_customer": "[Bill To Customer].[Customer]",
    "sales_territory": "[City].[Sales Territory]",
    "state_province": "[City].[State Province]",
    "stock_item": "[Stock Item].[Stock Item]",
    "color": "[Stock Item].[Color]",
    "salesperson": "[Salesperson].[Employee]",
    "picker": "[Picker].[Employee]",
    "stock_group": "[Stock Group].[Stock Group]",
    "pickup_year": "[Pickup Date].[Calendar Year]",
    "pickup_month": "[Pickup Date].[Month]",
    "pickup_date": "[Pickup Date].[Date]",
    "dropoff_year": "[Dropoff Date].[Calendar Year]",
    "dropoff_month": "[Dropoff Date].[Month]",
    "pickup_hour": "[Pickup Hour].[Pickup Hour]",
    "pickup_borough": "[Pickup Zone].[Borough]",
    "pickup_zone": "[Pickup Zone].[Location ID]",
    "dropoff_borough": "[Dropoff Zone].[Borough]",
    "dropoff_zone": "[Dropoff Zone].[Location ID]",
    "payment_type": "[Payment Type].[Payment Type]",
    "vendor": "[Vendor].[Vendor]",
}
WITH_UNKNOWN = {"delivery_year", "picker"}

SALE_GRAINS = [
    ("total", []), ("year", ["calendar_year"]), ("month", ["month"]), ("day", ["date"]),
    ("fiscal_year", ["fiscal_year"]), ("delivery_year", ["delivery_year"]),
    ("year_customer_category", ["calendar_year", "customer_category"]), ("year_customer", ["calendar_year", "customer"]),
    ("year_bill_to_customer", ["calendar_year", "bill_to_customer"]),
    ("year_sales_territory", ["calendar_year", "sales_territory"]),
    ("year_state_province", ["calendar_year", "state_province"]), ("year_stock_item", ["calendar_year", "stock_item"]),
    ("year_color", ["calendar_year", "color"]), ("year_salesperson", ["calendar_year", "salesperson"]),
    ("year_stock_group", ["calendar_year", "stock_group"]),
]
ORDER_GRAINS = [
    ("total", []), ("year", ["calendar_year"]), ("month", ["month"]), ("day", ["date"]),
    ("fiscal_year", ["fiscal_year"]), ("year_customer_category", ["calendar_year", "customer_category"]),
    ("year_customer", ["calendar_year", "customer"]), ("year_sales_territory", ["calendar_year", "sales_territory"]),
    ("year_state_province", ["calendar_year", "state_province"]), ("year_stock_item", ["calendar_year", "stock_item"]),
    ("year_salesperson", ["calendar_year", "salesperson"]), ("year_picker", ["calendar_year", "picker"]),
    ("year_stock_group", ["calendar_year", "stock_group"]),
]
TRIP_GRAINS = [
    ("total", []), ("year", ["pickup_year"]), ("month", ["pickup_month"]), ("day", ["pickup_date"]),
    ("dropoff_year", ["dropoff_year"]), ("dropoff_month", ["dropoff_month"]),
    ("year_pickup_hour", ["pickup_year", "pickup_hour"]), ("year_pickup_borough", ["pickup_year", "pickup_borough"]),
    ("year_pickup_zone", ["pickup_year", "pickup_zone"]), ("year_dropoff_borough", ["pickup_year", "dropoff_borough"]),
    ("year_dropoff_zone", ["pickup_year", "dropoff_zone"]), ("year_payment_type", ["pickup_year", "payment_type"]),
    ("year_vendor", ["pickup_year", "vendor"]),
    ("year_pickup_dropoff_borough", ["pickup_year", "pickup_borough", "dropoff_borough"]),
]
STOCK_GRAINS = [
    ("total", []), ("year", ["calendar_year"]), ("month", ["month"]), ("day", ["date"]),
    ("fiscal_year", ["fiscal_year"]), ("year_stock_item", ["calendar_year", "stock_item"]),
    ("year_color", ["calendar_year", "color"]), ("year_stock_group", ["calendar_year", "stock_group"]),
]
DOS_GRAINS = [g for g in STOCK_GRAINS if g[0] != "year_color"]
TIME_INTEL_GRAINS = [
    ("day", ["pickup_date"]), ("month", ["pickup_month"]), ("year", ["pickup_year"]), ("total", []),
    ("month_pickup_borough", ["pickup_month", "pickup_borough"]),
    ("month_payment_type", ["pickup_month", "payment_type"]),
    ("month_vendor", ["pickup_month", "vendor"]), ("month_pickup_hour", ["pickup_month", "pickup_hour"]),
]
W_C1_GRAINS = [
    ("total_stock_group", ["stock_group"]), ("total_all_groups", []),
    ("year_stock_group", ["calendar_year", "stock_group"]), ("year_all_groups", ["calendar_year"]),
    ("fiscal_year_stock_group", ["fiscal_year", "stock_group"]),
    ("year_sales_territory_stock_group", ["calendar_year", "sales_territory", "stock_group"]),
    ("year_customer_category_stock_group", ["calendar_year", "customer_category", "stock_group"]),
]

# Metric -> (cube, grains, [(measure label, measure)])
METRICS: dict[str, tuple[str, list, list[tuple[str, str]]]] = {
    "B-W1": ("WWI", SALE_GRAINS, [("B-W1", "Revenue Including Tax")]),
    "B-W2": ("WWI", SALE_GRAINS, [("B-W2", "Gross Profit")]),
    "B-W3": ("WWI", SALE_GRAINS, [("B-W3", "Units Sold")]),
    "B-W4": ("WWI", SALE_GRAINS, [("B-W4", "Invoice Count")]),
    "W-S1": ("WWI", SALE_GRAINS, [("W-S1", "Revenue")]),
    "W-M1": ("WWI", SALE_GRAINS, [("W-M1", "Gross Margin %")]),
    "B-W5": ("WWI", ORDER_GRAINS, [("B-W5", "Backordered Order Lines")]),
    "W-S2": ("WWI", ORDER_GRAINS, [("W-S2", "Ordered Quantity")]),
    "W-M2": ("WWI", STOCK_GRAINS, [("W-M2", "Closing Units")]),
    "W-C1": ("WWI", W_C1_GRAINS, [("W-C1", "Stock Group Revenue Share")]),
    "W-C2": ("WWI", DOS_GRAINS, [("W-C2", "Days of Supply"), ("W-C2:closing_units", "Closing Units"),
                                  ("W-C2:units_sold_91d", "Units Sold 91D")]),
    "B-N1": ("NYC", TRIP_GRAINS, [("B-N1", "Trip Count")]),
    "B-N2": ("NYC", TRIP_GRAINS, [("B-N2", "Total Trip Distance")]),
    "B-N3": ("NYC", TRIP_GRAINS, [("B-N3", "Fare Amount")]),
    "B-N4": ("NYC", TRIP_GRAINS, [("B-N4", "Tip Amount")]),
    "B-N5": ("NYC", TRIP_GRAINS, [("B-N5", "Tolls Amount")]),
    "N-S1": ("NYC", TRIP_GRAINS, [("N-S1", "Gross Trip Revenue")]),
    "N-S2": ("NYC", TRIP_GRAINS, [("N-S2", "Card Tips")]),
    "N-M1": ("NYC", TRIP_GRAINS, [("N-M1", "Distinct OD Pairs")]),
    "N-M2": ("NYC", TRIP_GRAINS, [("N-M2", "Fare per Mile")]),
    "N-C1": ("NYC", TIME_INTEL_GRAINS, [("N-C1:ytd_revenue", "Revenue YTD"), ("N-C1:stly_ytd_revenue", "Revenue STLY YTD"),
                                         ("N-C1:yoy_pct", "Revenue YoY %")]),
    "N-C2": ("NYC", TIME_INTEL_GRAINS, [("N-C2", "Pace Index"), ("N-C2:mtd_trips", "Trips MTD"),
                                         ("N-C2:ytd_trips", "Trips YTD")]),
}


def level_set(token: str) -> str:
    hierarchy = H[token]
    name = hierarchy.split(".")[1]
    members = f"{hierarchy}.{name}.Members"
    if token in WITH_UNKNOWN:
        return f"Union({members}, {{{hierarchy}.UnknownMember}})"
    return members


def statement(cube: str, grain: str, tokens: list[str], values: list[tuple[str, str]]) -> str:
    measures = ", ".join(f"[Measures].[{m}]" for _, m in values)
    rows = ";".join(H[t] for t in tokens)
    directive = (f"// @branch grain={grain} rows={rows} "
                 f"values={','.join(f'{label}:[Measures].[{m}]' for label, m in values)}")
    lines = [directive, f"SELECT {{{measures}}} ON COLUMNS"]
    if tokens:
        crossjoin = " * ".join(level_set(t) for t in tokens)
        lines[-1] += ","
        lines.append(f"  NonEmpty({crossjoin}, {{{measures}}}) ON ROWS")
    lines.append(f"FROM [{cube}]")
    return "\n".join(lines)


def render(metric_id: str) -> str:
    cube, grains, values = METRICS[metric_id]
    header = [
        f"// {metric_id} E1 reconciliation, oracle contract of 01-spec/oracle/metrics/{metric_id}.sql.",
        "// Generated by build_reconciliation_queries.py; edit the generator, not this file.",
    ]
    return "\n".join(header) + "\n\n" + "\n\n".join(statement(cube, g, t, values) for g, t in grains) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for metric_id in METRICS:
        path, text = OUT / f"{metric_id}.mdx", render(metric_id)
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
