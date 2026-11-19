#!/usr/bin/env python3
"""Build the deterministic oracle fixtures (standard library only).

Writes fixtures/<schema>/<table>.csv for every gold table the oracle reads, plus
fixtures/schema.json with column types (from the canonical schema, SPEC § 5).
The calendar is generated here independently of the platform code, so fixture
dim_date values are a second implementation of SPEC § 5.4.

Every value was chosen so the answers asserted in scripts/test_oracle.py can be
computed by hand; the derivations are written next to each fixture block.

    python build_fixtures.py          # rewrite the CSVs
    python build_fixtures.py --check  # exit 1 if committed fixtures differ
"""

from __future__ import annotations

import argparse
import calendar as cal
import csv
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "02-implementations" / "platform" / "src"))

from slc_platform.schema import NYC_TABLES, WWI_TABLES  # noqa: E402  (pure dataclasses, no Spark)

OPEN = "9999-12-31 23:59:59.999999"


def dim_date(start: date, end: date) -> list[dict]:
    rows, d = [], start
    while d <= end:
        fy = d.year + (1 if d.month >= 11 else 0)
        fm = (d.month - 11) % 12 + 1
        fy_start = date(fy - 1, 11, 1)
        iso_year, iso_week, iso_dow = d.isocalendar()
        rows.append({
            "date_key": d.isoformat(), "calendar_year": d.year, "calendar_quarter": (d.month - 1) // 3 + 1,
            "calendar_month": d.month, "month_name": cal.month_name[d.month], "month_start_date": d.replace(day=1).isoformat(),
            "day_of_month": d.day, "day_of_year": d.timetuple().tm_yday, "day_of_week": iso_dow,
            "day_name": cal.day_name[d.weekday()], "iso_week_number": iso_week, "fiscal_year": fy,
            "fiscal_quarter": (fm - 1) // 3 + 1, "fiscal_month": fm, "fiscal_period_index": fy * 12 + fm,
            "day_of_fiscal_year": (d - fy_start).days + 1,
        })
        d += timedelta(days=1)
    return rows


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def wwi_tables() -> dict[str, list[dict]]:
    t: dict[str, list[dict]] = {"dim_date": dim_date(date(2013, 1, 1), date(2016, 12, 31))}
    t["dim_city"] = [
        {"city_key": 1, "wwi_city_id": 1, "city": "Seattle", "state_province": "Washington", "country": "United States",
         "continent": "North America", "sales_territory": "Far West", "region": "Americas", "subregion": "Northern America",
         "valid_from": "2013-01-01 00:00:00", "valid_to": OPEN, "is_current": "true"},
        {"city_key": 2, "wwi_city_id": 2, "city": "Miami", "state_province": "Florida", "country": "United States",
         "continent": "North America", "sales_territory": "Southeast", "region": "Americas", "subregion": "Northern America",
         "valid_from": "2013-01-01 00:00:00", "valid_to": OPEN, "is_current": "true"},
    ]
    t["dim_customer"] = [
        {"customer_key": k, "wwi_customer_id": k, "customer": n, "bill_to_customer": b, "category": c, "buying_group": g,
         "valid_from": "2013-01-01 00:00:00", "valid_to": OPEN, "is_current": "true"}
        for k, n, b, c, g in [
            (0, "Unknown", "N/A", "N/A", "N/A"),
            (1, "Cust A", "Tailspin Toys (Head Office)", "Novelty Shop", "Tailspin Toys"),
            (2, "Cust B", "Cust B", "Novelty Shop", "N/A"),
        ]
    ]
    t["dim_employee"] = [
        {"employee_key": k, "wwi_employee_id": k, "employee": n, "is_salesperson": s,
         "valid_from": "2013-01-01 00:00:00", "valid_to": OPEN, "is_current": "true"}
        for k, n, s in [(0, "Unknown", "false"), (1, "Sam Seller", "true"), (2, "Pat Picker", "false")]
    ]
    # Item 1 changes color Gray -> Steel Gray on 2015-06-01 (SCD2: key 10 as-was, key 11 current).
    item = lambda k, i, name, color, pkg, chill, vf, vt, cur: {  # noqa: E731
        "stock_item_key": k, "wwi_stock_item_id": i, "stock_item": name, "brand": "N/A", "color": color, "size": "N/A",
        "selling_package": pkg, "is_chiller_stock": chill, "unit_price": "10.00", "valid_from": vf, "valid_to": vt,
        "is_current": cur}
    t["dim_stock_item"] = [
        item(10, 1, "Mug", "Gray", "Each", "false", "2013-01-01 00:00:00", "2015-06-01 00:00:00", "false"),
        item(11, 1, "Mug", "Steel Gray", "Each", "false", "2015-06-01 00:00:00", OPEN, "true"),
        item(20, 2, "Toy Mug", "Blue", "Each", "false", "2013-01-01 00:00:00", OPEN, "true"),
        item(30, 3, "Toy Car", "Red", "Packet", "false", "2013-01-01 00:00:00", OPEN, "true"),
    ]
    t["dim_stock_group"] = [{"stock_group_id": 1, "stock_group_name": "Mugs"}, {"stock_group_id": 2, "stock_group_name": "Toys"}]
    # Item 2 belongs to both groups: the fan-out case.
    t["bridge_stock_item_group"] = [
        {"wwi_stock_item_id": i, "stock_group_id": g} for i, g in [(1, 1), (2, 1), (2, 2), (3, 2)]
    ]
    # FY2015 = 2014-11-01 .. 2015-10-31: s1 + s2 + s3 -> revenue 350, profit 95.
    # Gross margin FY2015 = 95 / 350 = 0.27142857...; the average of line margins (0.40, 0.25, 0.10) would be 0.25.
    # Stock groups FY2015: Mugs = 100 + 200 + 50 = 350, Toys = 200; sum 550, overlap 200 (item 2 in two groups).
    # s6, s7 sit on the Days of Supply window edges (see fact_stock_holding_daily).
    sale = lambda k, inv, dlv, city, cust, bill, key, qty, rev, profit: {  # noqa: E731
        "sale_key": k, "invoice_date": inv, "delivery_date": dlv, "city_key": city, "customer_key": cust,
        "bill_to_customer_key": bill, "stock_item_key": key, "salesperson_key": 1, "wwi_invoice_id": 100 + k,
        "quantity": qty, "unit_price": "10.00", "total_excluding_tax": f"{rev:.2f}", "tax_amount": f"{rev * 0.15:.2f}",
        "profit": f"{profit:.2f}", "total_including_tax": f"{rev * 1.15:.2f}"}
    t["fact_sale"] = [
        sale(1, "2014-12-10", "2014-12-11", 2, 1, 1, 10, 10, 100, 40),
        sale(2, "2015-03-05", "", 1, 2, 0, 20, 5, 200, 50),
        sale(3, "2015-07-20", "2015-07-21", 2, 1, 1, 11, 2, 50, 5),
        sale(4, "2015-12-01", "2015-12-02", 2, 2, 0, 30, 1, 30, 30),
        sale(5, "2014-03-01", "2014-03-02", 1, 1, 1, 20, 4, 80, 8),
        sale(6, "2016-01-01", "2016-01-02", 1, 2, 0, 20, 2, 20, 2),
        sale(7, "2015-12-31", "2016-01-04", 1, 2, 0, 20, 100, 1000, 100),
    ]
    t["fact_order"] = [
        {"order_key": 1, "order_date": "2015-02-01", "city_key": 2, "customer_key": 1, "stock_item_key": 10,
         "salesperson_key": 1, "picker_key": 2, "wwi_order_id": 1, "wwi_backorder_id": "", "quantity": 7,
         "total_excluding_tax": "70.00"},
        {"order_key": 2, "order_date": "2015-02-15", "city_key": 1, "customer_key": 2, "stock_item_key": 20,
         "salesperson_key": 1, "picker_key": "", "wwi_order_id": 2, "wwi_backorder_id": 501, "quantity": 3,
         "total_excluding_tax": "60.00"},
    ]
    t["fact_stock_movement"] = []
    t["stock_holding_current"] = [
        {"stock_item_key": 11, "quantity_on_hand": 100}, {"stock_item_key": 20, "quantity_on_hand": 20},
        {"stock_item_key": 30, "quantity_on_hand": 10},
    ]
    # Dense snapshot: item 1 = 100, item 2 = 50 until 2015-12-15 then 20, item 3 = 10.
    # Closing stock 2015 (d* = 2015-12-31) = 100 + 20 + 10 = 130; November 2015 = 100 + 50 + 10 = 160.
    # DOS at 2015-12-31: window [2015-10-02, 2015-12-31] holds s4 (1) and s7 (100) -> 130 / (101 / 91) = 117.1287...
    # DOS at 2016-03-31: window [2016-01-01, 2016-03-31] (91 days, leap February) holds s6 (2) only -> 130 / (2 / 91) = 5915.
    snap = []
    for d in days(date(2013, 1, 1), date(2016, 5, 31)):
        snap.append({"snapshot_date": d.isoformat(), "wwi_stock_item_id": 1,
                     "stock_item_key": 10 if d < date(2015, 6, 1) else 11, "quantity_on_hand": 100,
                     "balance_basis": "holding_backcast"})
        snap.append({"snapshot_date": d.isoformat(), "wwi_stock_item_id": 2, "stock_item_key": 20,
                     "quantity_on_hand": 50 if d <= date(2015, 12, 15) else 20, "balance_basis": "holding_backcast"})
        snap.append({"snapshot_date": d.isoformat(), "wwi_stock_item_id": 3, "stock_item_key": 30,
                     "quantity_on_hand": 10, "balance_basis": "holding_backcast"})
    t["fact_stock_holding_daily"] = snap
    return t


def nyc_tables() -> dict[str, list[dict]]:
    t: dict[str, list[dict]] = {"dim_date": dim_date(date(2023, 1, 1), date(2025, 12, 31))}
    t["dim_zone"] = [
        {"location_id": i, "borough": b, "zone": z, "service_zone": s}
        for i, b, z, s in [
            (61, "Brooklyn", "Crown Heights North", "Boro Zone"),
            (132, "Queens", "JFK Airport", "Airports"),
            (138, "Queens", "LaGuardia Airport", "Airports"),
            (161, "Manhattan", "Midtown Center", "Yellow Zone"),
            (236, "Manhattan", "Upper East Side North", "Yellow Zone"),
        ]
    ]
    t["dim_payment_type"] = [
        {"payment_type": c, "payment_type_name": n}
        for c, n in [(0, "Flex Fare trip"), (1, "Credit card"), (2, "Cash"), (3, "No charge"), (4, "Dispute"),
                     (5, "Unknown"), (6, "Voided trip")]
    ]
    # Pickup-2024 revenue = t3 + t4 + t5 + t7 = 16 + 12 + 60 + 17 = 105; dropoff-2024 = t2 + t3 + t4 + t7 = 145.
    # Card tips 2024 = 1.50 + 8.00 + 3.00 = 12.50 (payment type 1 only; cash has none -> NULL, not 0).
    # Distinct OD pairs 2024 = {161236, 236161, 138061} = 3; card {236161, 138061, 161236} = 3, cash {161236} = 1 -> sum 4.
    # YTD at 2024-02-29 = t7 + t3 = 33; STLY through 2023-02-28 (29 Feb -> 28 Feb) = t1 = 15; YoY = 1.2.
    # Pace 2024-03-15 = (1 / 15) / (3 / 75) = 1.6667; 2023-03-15 = (1 / 15) / (2 / 74) = 2.4667.
    trip = lambda i, pu_ts, do_ts, pu, do, pay, fare, tip, tolls, total, dist, vendor: {  # noqa: E731
        "trip_id": i, "vendor_id": vendor, "pickup_ts": pu_ts, "dropoff_ts": do_ts, "pickup_date": pu_ts[:10],
        "dropoff_date": do_ts[:10], "pickup_hour": int(pu_ts[11:13]), "pu_location_id": pu, "do_location_id": do,
        "od_pair_id": pu * 1000 + do, "passenger_count": 1, "trip_distance": f"{dist:.2f}", "payment_type": pay,
        "fare_amount": f"{fare:.2f}", "tip_amount": f"{tip:.2f}", "tolls_amount": f"{tolls:.2f}",
        "total_amount": f"{total:.2f}"}
    t["fact_trip"] = [
        trip(1, "2023-02-28 10:00:00", "2023-02-28 10:20:00", 161, 236, 1, 10, 2, 0, 15, 2.0, 1),
        trip(2, "2023-12-31 23:50:00", "2024-01-01 00:10:00", 132, 161, 1, 70, 10, 6.94, 100, 17.0, 2),
        trip(3, "2024-02-29 09:00:00", "2024-02-29 09:15:00", 161, 236, 2, 12, 0, 0, 16, 3.0, 1),
        trip(4, "2024-03-15 18:00:00", "2024-03-15 18:10:00", 236, 161, 1, 8, 1.5, 0, 12, 1.5, 2),
        trip(5, "2024-12-31 23:55:00", "2025-01-01 00:20:00", 138, 61, 1, 40, 8, 6.94, 60, 10.0, 2),
        trip(6, "2023-03-15 08:00:00", "2023-03-15 08:12:00", 161, 236, 2, 9, 0, 0, 12, 2.0, 1),
        trip(7, "2024-01-10 12:00:00", "2024-01-10 12:14:00", 161, 236, 1, 11, 3, 0, 17, 2.5, 1),
    ]
    return t


def render(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="raise")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


def outputs() -> dict[Path, str]:
    files: dict[Path, str] = {}
    types: dict[str, list[list[str]]] = {}
    for schema, specs, data in (("wwi", WWI_TABLES, wwi_tables()), ("nyctaxi", NYC_TABLES, nyc_tables())):
        for name, rows in data.items():
            spec = specs[name]
            files[HERE / schema / f"{name}.csv"] = render(rows, spec.column_names)
            types[f"{schema}.{name}"] = [[c, t] for c, t, _ in spec.columns]
    files[HERE / "schema.json"] = json.dumps(types, indent=1) + "\n"
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
        print(f"stale fixtures: {stale}")
        sys.exit(1)


if __name__ == "__main__":
    main()
