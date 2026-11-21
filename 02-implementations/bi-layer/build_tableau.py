#!/usr/bin/env python3
"""Generate every S3 Tableau artifact from model.py and question_specs.py.

Outputs (never edit them by hand; --check fails on drift):
  datasources/<key>.tds          published data sources (live variant), Tableau 2026.3 document format
  datasources/field_catalog.json caption -> local name, datatype, role, hidden, per data source
  queries/metrics/<ID>.json      E1 reconciliation: VizQL Data Service queries per oracle grain (22)
  queries/questions/<ID>.json    stack-native answers: VDS queries plus a DuckDB assembly over their results (70)

    python3 build_tableau.py [--check]
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import question_specs  # noqa: E402
from model import CONNECTION, DATASOURCES, Calc, Col, DataSource, Param  # noqa: E402
from vds import agg, dim, query  # noqa: E402

USER_NS = "http://www.tableausoftware.com/xml/user"
ET.register_namespace("user", USER_NS)
VERSION = "26.3"

# =========================================================================== .tds rendering


def _desc(parent: ET.Element, text: str) -> None:
    run = ET.SubElement(ET.SubElement(ET.SubElement(parent, "desc"), "formatted-text"), "run")
    run.text = text


def _relation(parent: ET.Element, table) -> None:
    rel = ET.SubElement(parent, "relation", {"connection": CONNECTION, "name": table.caption, "type": "text"})
    rel.text = table.sql


def _expr(parent: ET.Element, pairs: list[tuple[str, str]]) -> None:
    def eq(node: ET.Element, a: str, b: str) -> None:
        e = ET.SubElement(node, "expression", {"op": "="})
        ET.SubElement(e, "expression", {"op": f"[{a}]"})
        ET.SubElement(e, "expression", {"op": f"[{b}]"})

    if len(pairs) == 1:
        eq(parent, *pairs[0])
    else:
        conj = ET.SubElement(parent, "expression", {"op": "AND"})
        for a, b in pairs:
            eq(conj, a, b)


def render_tds(ds: DataSource) -> str:
    root = ET.Element("datasource", {"formatted-name": ds.name, "inline": "true", "source-platform": "linux",
                                     "version": VERSION})
    ET.SubElement(ET.SubElement(root, "document-format-change-manifest"), "ManifestByVersion")
    conn = ET.SubElement(root, "connection", {"class": "federated"})
    named = ET.SubElement(ET.SubElement(conn, "named-connections"), "named-connection",
                          {"caption": "SLC Databricks SQL (serverless)", "name": CONNECTION})
    # Host, HTTP path and the token are bound at publish time from the target environment (jobs/publish.py).
    ET.SubElement(named, "connection", {"class": "databricks", "authentication": "auth-pass", "username": "token",
                                        "port": "443", "sslmode": "require", "dbname": "slc"})
    collection = ET.SubElement(conn, "relation", {"type": "collection"})
    for t in ds.tables:
        _relation(collection, t)
    cols = ET.SubElement(conn, "cols")
    for t in ds.tables:
        for c in t.cols:
            ET.SubElement(cols, "map", {"key": f"[{c.name}]", "value": f"[{t.caption}].[{c.name}]"})
    ET.SubElement(root, "aliases", {"enabled": "yes"})
    for p in ds.params:
        col = ET.SubElement(root, "column", {"caption": p.caption, "datatype": p.datatype, "name": f"[{p.name}]",
                                             "param-domain-type": "any", "role": "measure", "type": "quantitative",
                                             "value": p.value})
        ET.SubElement(col, "calculation", {"class": "tableau", "formula": p.value})
        _desc(col, p.desc)
    for c in ds.columns():
        attrs = {"caption": c.caption, "datatype": c.datatype, "name": f"[{c.name}]", "role": c.role, "type": c.type}
        if c.role == "measure":
            attrs["aggregation"] = "Sum"
        if c.hidden:
            attrs["hidden"] = "true"
        col = ET.SubElement(root, "column", attrs)
        if c.desc:
            _desc(col, c.desc)
    for c in ds.calcs:
        attrs = {"caption": c.caption, "datatype": c.datatype, "name": f"[{c.name}]", "role": c.role, "type": c.type}
        if c.fmt:
            attrs["default-format"] = c.fmt
        if c.hidden:
            attrs["hidden"] = "true"
        col = ET.SubElement(root, "column", attrs)
        ET.SubElement(col, "calculation", {"class": "tableau", "formula": c.formula})
        if c.desc:
            _desc(col, c.desc)
    for f in ds.rls:
        attrs = {"class": "categorical", "column": f"[{f.calc}]"}
        if f.logical_table_scoped:
            attrs["logical-table-scoped"] = "true"
        flt = ET.SubElement(root, "filter", attrs)
        ET.SubElement(flt, "groupfilter", {"function": "member", "level": f"[{f.calc}]", "member": "true",
                                            f"{{{USER_NS}}}ui-domain": "database",
                                            f"{{{USER_NS}}}ui-enumeration": "inclusive",
                                            f"{{{USER_NS}}}ui-marker": "enumerate"})
    graph = ET.SubElement(root, "object-graph")
    objects = ET.SubElement(graph, "objects")
    for t in ds.tables:
        obj = ET.SubElement(objects, "object", {"caption": t.caption, "id": t.id})
        _relation(ET.SubElement(obj, "properties", {"context": ""}), t)
        run = ET.SubElement(ET.SubElement(ET.SubElement(obj, "table-description"), "formatted-text"), "run")
        run.text = t.desc
    rels = ET.SubElement(graph, "relationships")
    for r in ds.rels:
        rel = ET.SubElement(rels, "relationship")
        _expr(rel, r.pairs)
        ET.SubElement(rel, "first-end-point", {"object-id": r.first})
        ET.SubElement(rel, "second-end-point", {"object-id": r.second})
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return ("<?xml version='1.0' encoding='utf-8' ?>\n"
            f"<!-- {ds.name}: published data source of stack S3. Generated by build_tableau.py from model.py; "
            "edit the builder, not this file. -->\n" + body + "\n")


def field_catalog() -> dict:
    out = {}
    for ds in DATASOURCES:
        fields = {}
        for item in [*ds.columns(), *ds.calcs, *ds.params]:
            kind = "parameter" if isinstance(item, Param) else ("calculation" if isinstance(item, Calc) else "column")
            fields[item.caption] = {
                "name": item.name, "kind": kind, "datatype": item.datatype,
                "role": getattr(item, "role", "measure"), "hidden": getattr(item, "hidden", False),
                "formula": item.formula if isinstance(item, Calc) else None,
                "metric_id": item.metric_id if isinstance(item, Calc) else None,
                "description": item.desc,
            }
        out[ds.name] = {"file": f"datasources/{ds.file}", "extract_variant": ds.extract_name,
                        "incremental_key": ds.incremental_key, "fields": fields}
    return out

# =========================================================================== E1 reconciliation specs

WS = "SLC WWI Sales and Orders"
STK = "SLC WWI Stock"
NYC = "SLC NYC Trips"

# grain -> [(caption, alias)] member fields, in member_1..3 order.
SALE_GRAINS = {
    "total": [], "year": [("Calendar Year", "m1")], "month": [("Month Start Date", "m1")],
    "day": [("Invoice Date", "m1")], "fiscal_year": [("Fiscal Year", "m1")],
    "delivery_year": [("Delivery Year", "m1")],
    "year_customer_category": [("Calendar Year", "m1"), ("Customer Category", "m2")],
    "year_customer": [("Calendar Year", "m1"), ("Customer", "m2")],
    "year_bill_to_customer": [("Calendar Year", "m1"), ("Bill-To Customer", "m2")],
    "year_sales_territory": [("Calendar Year", "m1"), ("Sales Territory", "m2")],
    "year_state_province": [("Calendar Year", "m1"), ("State Province", "m2")],
    "year_stock_item": [("Calendar Year", "m1"), ("Stock Item", "m2")],
    "year_color": [("Calendar Year", "m1"), ("Color", "m2")],
    "year_salesperson": [("Calendar Year", "m1"), ("Salesperson", "m2")],
    "year_stock_group": [("Calendar Year", "m1"), ("Stock Group", "m2")],
}
ORDER_GRAINS = {
    "total": [], "year": [("Calendar Year", "m1")], "month": [("Month Start Date", "m1")],
    "day": [("Order Date", "m1")], "fiscal_year": [("Fiscal Year", "m1")],
    "year_customer_category": [("Calendar Year", "m1"), ("Customer Category", "m2")],
    "year_customer": [("Calendar Year", "m1"), ("Customer", "m2")],
    "year_sales_territory": [("Calendar Year", "m1"), ("Sales Territory", "m2")],
    "year_state_province": [("Calendar Year", "m1"), ("State Province", "m2")],
    "year_stock_item": [("Calendar Year", "m1"), ("Stock Item", "m2")],
    "year_salesperson": [("Calendar Year", "m1"), ("Salesperson", "m2")],
    "year_picker": [("Calendar Year", "m1"), ("Picker", "m2")],
    "year_stock_group": [("Calendar Year", "m1"), ("Stock Group", "m2")],
}
TRIP_GRAINS = {
    "total": [], "year": [("Pickup Year", "m1")], "month": [("Pickup Month Start Date", "m1")],
    "day": [("Pickup Date", "m1")], "dropoff_year": [("Dropoff Year", "m1")],
    "dropoff_month": [("Dropoff Month Start Date", "m1")],
    "year_pickup_hour": [("Pickup Year", "m1"), ("Pickup Hour", "m2")],
    "year_pickup_borough": [("Pickup Year", "m1"), ("Pickup Borough", "m2")],
    "year_pickup_zone": [("Pickup Year", "m1"), ("Pickup Zone ID", "m2")],
    "year_dropoff_borough": [("Pickup Year", "m1"), ("Dropoff Borough", "m2")],
    "year_dropoff_zone": [("Pickup Year", "m1"), ("Dropoff Zone ID", "m2")],
    "year_payment_type": [("Pickup Year", "m1"), ("Payment Type", "m2")],
    "year_vendor": [("Pickup Year", "m1"), ("Vendor", "m2")],
    "year_pickup_dropoff_borough": [("Pickup Year", "m1"), ("Pickup Borough", "m2"), ("Dropoff Borough", "m3")],
}
STOCK_GRAINS = {
    "total": [], "year": [("Calendar Year", "m1")], "month": [("Month Start Date", "m1")],
    "day": [("Snapshot Date", "m1")], "fiscal_year": [("Fiscal Year", "m1")],
    "year_stock_item": [("Calendar Year", "m1"), ("Stock Item", "m2")],
    "year_color": [("Calendar Year", "m1"), ("Color", "m2")],
    "year_stock_group": [("Calendar Year", "m1"), ("Stock Group", "m2")],
}
DOS_GRAINS = {g: v for g, v in STOCK_GRAINS.items() if g != "year_color"}
W_C1_GRAINS = {
    "total_stock_group": [("Stock Group", "m1")], "total_all_groups": [],
    "year_stock_group": [("Calendar Year", "m1"), ("Stock Group", "m2")], "year_all_groups": [("Calendar Year", "m1")],
    "fiscal_year_stock_group": [("Fiscal Year", "m1"), ("Stock Group", "m2")],
    "year_sales_territory_stock_group": [("Calendar Year", "m1"), ("Sales Territory", "m2"), ("Stock Group", "m3")],
    "year_customer_category_stock_group": [("Calendar Year", "m1"), ("Customer Category", "m2"), ("Stock Group", "m3")],
}
# Period-to-date grains: anchor kind and member fields after the anchor member.
TIME_INTEL_GRAINS = {
    "day": ("day", []), "month": ("month", []), "year": ("year", []), "total": ("total", []),
    "month_pickup_borough": ("month", [("Pickup Borough", "m2")]),
    "month_payment_type": ("month", [("Payment Type", "m2")]),
    "month_vendor": ("month", [("Vendor", "m2")]),
    "month_pickup_hour": ("month", [("Pickup Hour", "m2")]),
}

# Row-presence measure of each fact: rows where it is 0 or blank carry no facts and are dropped by the runner.
PRESENCE = {"sales": ("Sales Line Count"), "orders": ("Order Line Count"), "stock": "Snapshot Row Count",
            "trips": "Trip Count"}
FACT_OF = {"B-W1": "sales", "B-W2": "sales", "B-W3": "sales", "B-W4": "sales", "W-S1": "sales", "W-M1": "sales",
           "W-C1": "sales", "B-W5": "orders", "W-S2": "orders", "W-M2": "stock", "W-C2": "stock"}

SIMPLE = {
    "B-W1": (WS, SALE_GRAINS, "Revenue Including Tax"), "B-W2": (WS, SALE_GRAINS, "Gross Profit"),
    "B-W3": (WS, SALE_GRAINS, "Units Sold"), "B-W4": (WS, SALE_GRAINS, "Invoice Count"),
    "W-S1": (WS, SALE_GRAINS, "Revenue (Excl. Tax)"), "W-M1": (WS, SALE_GRAINS, "Gross Margin %"),
    "B-W5": (WS, ORDER_GRAINS, "Backordered Order Lines"), "W-S2": (WS, ORDER_GRAINS, "Ordered Quantity"),
    "B-N1": (NYC, TRIP_GRAINS, "Trip Count"), "B-N2": (NYC, TRIP_GRAINS, "Total Trip Distance"),
    "B-N3": (NYC, TRIP_GRAINS, "Fare Amount"), "B-N4": (NYC, TRIP_GRAINS, "Tip Amount (All Payment Types)"),
    "B-N5": (NYC, TRIP_GRAINS, "Tolls Amount"), "N-S1": (NYC, TRIP_GRAINS, "Gross Trip Revenue"),
    "N-S2": (NYC, TRIP_GRAINS, "Card Tips"), "N-M1": (NYC, TRIP_GRAINS, "Distinct OD Pairs"),
    "N-M2": (NYC, TRIP_GRAINS, "Fare per Mile"),
}
MULTI = {
    "W-M2": (STK, STOCK_GRAINS, [("W-M2", "Closing Stock On Hand")]),
    "W-C2": (STK, DOS_GRAINS, [("W-C2", "Days of Supply"), ("W-C2:closing_units", "Closing Stock On Hand"),
                               ("W-C2:units_sold_91d", "Units Sold Trailing 91 Days")]),
    "W-C1": (WS, W_C1_GRAINS, [("W-C1", "Stock Group Revenue Share")]),
}
TIME_INTEL = {
    "N-C1": [("N-C1:ytd_revenue", "Revenue YTD"), ("N-C1:stly_ytd_revenue", "Revenue YTD Same Time Last Year"),
             ("N-C1:yoy_pct", "Revenue YoY % vs STLY")],
    "N-C2": [("N-C2", "MTD-to-YTD Daily Pace Index"), ("N-C2:mtd_trips", "Trips MTD"), ("N-C2:ytd_trips", "Trips YTD")],
}
NYC_FIRST, NYC_LAST = dt.date(2023, 1, 1), dt.date(2024, 12, 31)


def anchors(kind: str) -> list[list[str | None]]:
    """[anchor date, member_1 label] pairs: t(P) is the calendar end of the period, capped at the source window."""
    if kind == "day":
        n = (NYC_LAST - NYC_FIRST).days + 1
        return [[(NYC_FIRST + dt.timedelta(i)).isoformat()] * 2 for i in range(n)]
    if kind == "month":
        out = []
        for y in (2023, 2024):
            for m in range(1, 13):
                out.append([dt.date(y, m, calendar.monthrange(y, m)[1]).isoformat(), dt.date(y, m, 1).isoformat()])
        return out
    if kind == "year":
        return [["2023-12-31", "2023"], ["2024-12-31", "2024"]]
    return [[NYC_LAST.isoformat(), None]]


def metric_spec(metric_id: str) -> dict:
    branches = []
    if metric_id in SIMPLE or metric_id in MULTI:
        if metric_id in SIMPLE:
            source, grains, caption = SIMPLE[metric_id]
            values = [(metric_id, caption)]
        else:
            source, grains, values = MULTI[metric_id]
        presence = PRESENCE[FACT_OF.get(metric_id, "trips")]
        for grain, members in grains.items():
            aliases = [f"v{i}" for i in range(len(values))]
            q = query(source, [dim(c, a) for c, a in members] + [agg(c, al) for (_, c), al in zip(values, aliases)]
                      + [agg(presence, "presence")])
            branches.append({"grain": grain, **q, "members": [a for _, a in members],
                             "values": {label: al for (label, _), al in zip(values, aliases)}, "presence": "presence",
                             "value_kinds": value_kinds(source, values)})
    else:
        values = TIME_INTEL[metric_id]
        for grain, (kind, members) in TIME_INTEL_GRAINS.items():
            aliases = [f"v{i}" for i in range(len(values))]
            q = query(NYC, [dim(c, a) for c, a in members] + [agg(c, al) for (_, c), al in zip(values, aliases)]
                      + [agg(PRESENCE["trips"], "presence")])
            branches.append({"grain": grain, **q, "presence": "presence",
                             "members": (["@anchor"] if kind != "total" else []) + [a for _, a in members],
                             "anchor_parameter": "As-of Date", "anchors": anchors(kind),
                             "values": {label: al for (label, _), al in zip(values, aliases)},
                             "value_kinds": value_kinds(NYC, values)})
    return {"metric": metric_id,
            "contract": ["grain", "measure", "member_1", "member_2", "member_3", "value"],
            "generated_by": "build_tableau.py", "branches": branches}


ALL_METRICS = sorted([*SIMPLE, *MULTI, *TIME_INTEL])
KIND_OF_FORMAT = {"currency": "money", "decimal_2": "money", "units": "count", "count": "count"}


def value_kinds(source: str, values: list[tuple[str, str]]) -> dict[str, str]:
    """SPEC § 9.3 tolerance class per measure label: money (±0.005), count (exact) or ratio (±1e-6)."""
    from model import BY_NAME, FORMATS
    fmt_key = {v: k for k, v in FORMATS.items()}
    fields = BY_NAME[source].fields()
    return {label: KIND_OF_FORMAT.get(fmt_key.get(fields[cap].fmt), "ratio") for label, cap in values}

# =========================================================================== outputs


def _json(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def outputs() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for ds in DATASOURCES:
        files[HERE / "datasources" / ds.file] = render_tds(ds)
    files[HERE / "datasources" / "field_catalog.json"] = _json(field_catalog())
    for metric_id in ALL_METRICS:
        files[HERE / "queries" / "metrics" / f"{metric_id}.json"] = _json(metric_spec(metric_id))
    for qid, spec in question_specs.build().items():
        files[HERE / "queries" / "questions" / f"{qid}.json"] = _json(spec)
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
