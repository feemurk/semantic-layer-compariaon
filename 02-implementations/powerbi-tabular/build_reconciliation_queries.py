#!/usr/bin/env python3
"""Generate the 22 E1 reconciliation queries in DAX (queries/metrics/<ID>.dax).

Each query returns the oracle contract of 01-spec/oracle/metrics/<ID>.sql: grain, measure, member_1..member_3
(text) and value, for the same grains. Grains and metric bases of the 17 single-aggregate metrics are imported from
the oracle's own generator (01-spec/oracle/build_metric_sql.py), so both sides cannot drift apart. Members are
rendered with FORMAT so they compare as text with the oracle's CAST(... AS STRING). SUMMARIZECOLUMNS omits groups
whose measures are blank; SPEC § 5.3 rule 7 treats an absent row and a NULL value as equal, and the comparator in
deploy/reconcile.py applies that rule.

    python build_reconciliation_queries.py          # write queries/metrics/*.dax
    python build_reconciliation_queries.py --check  # exit 1 when committed files differ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "queries" / "metrics"
sys.path.insert(0, str(REPO / "01-spec" / "oracle"))

import build_metric_sql as oracle  # noqa: E402

# Oracle base attribute -> (DAX column, kind) where kind selects the text rendering.
ATTRIBUTES = {
    "sale": {
        "calendar_year": ("'Date'[Calendar Year]", "int"),
        "month_start_date": ("'Date'[Month Start]", "date"),
        "invoice_date": ("'Date'[Date]", "date"),
        "fiscal_year": ("'Date'[Fiscal Year]", "int"),
        "delivery_year": ("'Delivery Date'[Delivery Year]", "int"),
        "customer_category": ("'Customer'[Customer Category]", "str"),
        "customer_name": ("'Customer'[Customer]", "str"),
        "bill_to_customer_name": ("'Bill-To Customer'[Bill-To Customer]", "str"),
        "sales_territory": ("'City'[Sales Territory]", "str"),
        "state_province": ("'City'[State Province]", "str"),
        "stock_item": ("'Stock Item'[Stock Item]", "str"),
        "color": ("'Stock Item'[Color]", "str"),
        "salesperson": ("'Salesperson'[Salesperson]", "str"),
        "g.stock_group_name": ("'Stock Group'[Stock Group]", "str"),
    },
    "order": {
        "calendar_year": ("'Date'[Calendar Year]", "int"),
        "month_start_date": ("'Date'[Month Start]", "date"),
        "order_date": ("'Date'[Date]", "date"),
        "fiscal_year": ("'Date'[Fiscal Year]", "int"),
        "customer_category": ("'Customer'[Customer Category]", "str"),
        "customer_name": ("'Customer'[Customer]", "str"),
        "sales_territory": ("'City'[Sales Territory]", "str"),
        "state_province": ("'City'[State Province]", "str"),
        "stock_item": ("'Stock Item'[Stock Item]", "str"),
        "salesperson": ("'Salesperson'[Salesperson]", "str"),
        "picker": ("'Picker'[Picker]", "str"),
        "g.stock_group_name": ("'Stock Group'[Stock Group]", "str"),
    },
    "trip": {
        "calendar_year": ("'Pickup Date'[Pickup Calendar Year]", "int"),
        "month_start_date": ("'Pickup Date'[Pickup Month Start]", "date"),
        "pickup_date": ("'Pickup Date'[Pickup Date]", "date"),
        "dropoff_year": ("'Dropoff Date'[Dropoff Calendar Year]", "int"),
        "dropoff_month": ("'Dropoff Date'[Dropoff Month Start]", "date"),
        "pickup_hour": ("Trips[Pickup Hour]", "int"),
        "pickup_borough": ("'Pickup Zone'[Pickup Borough]", "str"),
        "pu_location_id": ("'Pickup Zone'[Pickup Location ID]", "int"),
        "dropoff_borough": ("'Dropoff Zone'[Dropoff Borough]", "str"),
        "do_location_id": ("'Dropoff Zone'[Dropoff Location ID]", "int"),
        "payment_type_name": ("'Payment Type'[Payment Type Name]", "str"),
        "vendor_id": ("Trips[Vendor ID]", "int"),
    },
}

SIMPLE_MEASURES = {
    "B-W1": "[Revenue Including Tax]", "B-W2": "[Gross Profit]", "B-W3": "[Units Sold]", "B-W4": "[Invoice Count]",
    "B-W5": "[Backordered Order Lines]", "W-S1": "[Revenue (Excl. Tax)]", "W-S2": "[Ordered Quantity]",
    "W-M1": "[Gross Margin %]", "B-N1": "[Trip Count]", "B-N2": "[Total Trip Distance]", "B-N3": "[Fare Amount]",
    "B-N4": "[Tip Amount (All Payment Types)]", "B-N5": "[Tolls Amount]", "N-S1": "[Gross Trip Revenue]",
    "N-S2": "[Card Tips]", "N-M1": "[Distinct OD Pairs]", "N-M2": "[Fare per Mile]",
}

WWI_DATE = {"year": ("'Date'[Calendar Year]", "int"), "month": ("'Date'[Month Start]", "date"),
            "day": ("'Date'[Date]", "date"), "fiscal_year": ("'Date'[Fiscal Year]", "int")}
STOCK_ITEM = ("'Stock Item'[Stock Item]", "str")
COLOR = ("'Stock Item'[Color]", "str")
GROUP = ("'Stock Group'[Stock Group]", "str")
TERRITORY = ("'City'[Sales Territory]", "str")
CATEGORY = ("'Customer'[Customer Category]", "str")
PDATE = {"year": ("'Pickup Date'[Pickup Calendar Year]", "int"), "month": ("'Pickup Date'[Pickup Month Start]", "date"),
         "day": ("'Pickup Date'[Pickup Date]", "date")}
NYC_MEMBERS = {"pickup_borough": ("'Pickup Zone'[Pickup Borough]", "str"),
               "payment_type": ("'Payment Type'[Payment Type Name]", "str"),
               "vendor": ("Trips[Vendor ID]", "int"), "pickup_hour": ("Trips[Pickup Hour]", "int")}

# Hand-written oracle metrics: grain -> member columns, and (measure label, DAX value) pairs.
COMPLEX: dict[str, tuple[list[tuple[str, list[tuple[str, str]]]], list[tuple[str, str]]]] = {
    "W-M2": ([("total", []), ("year", [WWI_DATE["year"]]), ("month", [WWI_DATE["month"]]), ("day", [WWI_DATE["day"]]),
              ("fiscal_year", [WWI_DATE["fiscal_year"]]), ("year_stock_item", [WWI_DATE["year"], STOCK_ITEM]),
              ("year_color", [WWI_DATE["year"], COLOR]), ("year_stock_group", [WWI_DATE["year"], GROUP])],
             [("W-M2", "[Closing Stock On Hand]")]),
    "W-C1": ([("total_stock_group", [GROUP]), ("total_all_groups", []), ("year_stock_group", [WWI_DATE["year"], GROUP]),
              ("year_all_groups", [WWI_DATE["year"]]), ("fiscal_year_stock_group", [WWI_DATE["fiscal_year"], GROUP]),
              ("year_sales_territory_stock_group", [WWI_DATE["year"], TERRITORY, GROUP]),
              ("year_customer_category_stock_group", [WWI_DATE["year"], CATEGORY, GROUP])],
             [("W-C1", "[Stock Group Revenue Share]")]),
    "W-C2": ([("total", []), ("year", [WWI_DATE["year"]]), ("month", [WWI_DATE["month"]]), ("day", [WWI_DATE["day"]]),
              ("fiscal_year", [WWI_DATE["fiscal_year"]]), ("year_stock_item", [WWI_DATE["year"], STOCK_ITEM]),
              ("year_stock_group", [WWI_DATE["year"], GROUP])],
             [("W-C2", "[Days of Supply]"), ("W-C2:closing_units", "[Closing Stock On Hand]"),
              ("W-C2:units_sold_91d", "[Units Sold 91D]")]),
    "N-C1": ([("day", [PDATE["day"]]), ("month", [PDATE["month"]]), ("year", [PDATE["year"]]), ("total", [])]
             + [(f"month_{k}", [PDATE["month"], v]) for k, v in NYC_MEMBERS.items()],
             [("N-C1:ytd_revenue", "[Revenue YTD]"), ("N-C1:stly_ytd_revenue", "[Revenue STLY YTD]"),
              ("N-C1:yoy_pct", "[Revenue YoY % vs STLY]")]),
    "N-C2": ([("day", [PDATE["day"]]), ("month", [PDATE["month"]]), ("year", [PDATE["year"]]), ("total", [])]
             + [(f"month_{k}", [PDATE["month"], v]) for k, v in NYC_MEMBERS.items()],
             [("N-C2", "[MTD-to-YTD Daily Pace Index]"), ("N-C2:mtd_trips", "[Trips MTD]"), ("N-C2:ytd_trips", "[Trips YTD]")]),
}
ORDER = ["B-W1", "B-W2", "B-W3", "B-W4", "B-W5", "B-N1", "B-N2", "B-N3", "B-N4", "B-N5", "W-S1", "W-S2", "W-M1", "W-M2",
         "W-C1", "W-C2", "N-S1", "N-S2", "N-M1", "N-M2", "N-C1", "N-C2"]
NULL_TEXT = "CONVERT ( BLANK (), STRING )"


def as_text(column: str, kind: str) -> str:
    if kind == "int":
        return f"FORMAT ( {column}, \"0\" )"
    if kind == "date":
        return f"FORMAT ( {column}, \"yyyy-MM-dd\" )"
    return column


def branch(grain: str, label: str, members: list[tuple[str, str]], value: str) -> str:
    texts = [as_text(c, k) for c, k in members] + [NULL_TEXT] * (3 - len(members))
    cols = (f'"grain", "{grain}", "measure", "{label}", "member_1", {texts[0]}, "member_2", {texts[1]}, '
            f'"member_3", {texts[2]}')
    if not members:
        return f"    SELECTCOLUMNS ( {{ 1 }}, {cols}, \"value\", {value} )"
    groups = ", ".join(c for c, _ in members)
    return (f"    SELECTCOLUMNS (\n        SUMMARIZECOLUMNS ( {groups}, \"v\", {value} ),\n"
            f"        {cols}, \"value\", [v]\n    )")


def render(metric_id: str) -> str:
    branches = []
    if metric_id in SIMPLE_MEASURES:
        base = oracle.METRICS[metric_id][0]
        for grain in oracle.GRAINS[base]:
            members = [ATTRIBUTES[base][m] for m in grain[1]]
            branches.append(branch(grain[0], metric_id, members, SIMPLE_MEASURES[metric_id]))
        definition = oracle.METRICS[metric_id][2]
    else:
        grains, values = COMPLEX[metric_id]
        for grain, members in grains:
            for label, value in values:
                branches.append(branch(grain, label, members, value))
        definition = f"hand-written oracle contract of 01-spec/oracle/metrics/{metric_id}.sql"
    return (f"// {metric_id} E1 reconciliation ({definition}).\n"
            f"// Generated by build_reconciliation_queries.py; edit the generator, not this file.\n"
            f"EVALUATE\nUNION (\n" + ",\n".join(branches) + "\n)\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for metric_id in ORDER:
        path, text = OUT / f"{metric_id}.dax", render(metric_id)
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print(f"stale reconciliation queries: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
