"""Local stand-in for the VizQL Data Service, for testing the S3 query plans and assemblies without Tableau.

The emulator executes the queries of queries/metrics and queries/questions with DuckDB over the oracle fixtures
(01-spec/oracle/fixtures), using the logical tables and relationships of model.py:

- dimensions resolve to their logical table and are joined from the measure's fact along the relationship path
  (left joins, so unmatched fact rows group under a NULL member, as relationships keep unmatched measure values);
- each measure is evaluated per fact at the query's dimensions, and measures of different facts are stitched on the
  shared dimensions (multi-fact);
- Stock Group Revenue Share divides by the same measure evaluated without Stock Group (EXCLUDE semantics, bridge not
  joined); closing stock and trailing 91-day units take the last snapshot date per group (the INCLUDE/argmax pattern);
  period-to-date measures read the As-of Date parameter;
- dimension-only queries return the distinct members of the dimension tables.

The measure SQL below restates what each Tableau calculation computes. It proves that the query decomposition and the
assembly reproduce the oracle; it is not evidence that Tableau evaluates the calculations this way (guide § 7).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from model import BY_NAME, Calc, Col, DataSource  # noqa: E402

SALES_M = {
    "Revenue (Excl. Tax)": "SUM(f.sale_total_excluding_tax)",
    "Revenue Including Tax": "SUM(f.sale_total_including_tax)",
    "Gross Profit": "SUM(f.sale_profit)",
    "Units Sold": "SUM(f.sale_quantity)",
    "Invoice Count": "COUNT(DISTINCT f.sale_wwi_invoice_id)",
    "Gross Margin %": "CAST(SUM(f.sale_profit) AS DOUBLE) / NULLIF(CAST(SUM(f.sale_total_excluding_tax) AS DOUBLE), 0)",
    "Sales Line Count": "COUNT(f.sale_key)",
}
ORDER_M = {
    "Ordered Quantity": "SUM(f.ord_quantity)",
    "Backordered Order Lines": "NULLIF(COUNT(f.ord_wwi_backorder_id), 0)",
    "Order Line Count": "COUNT(f.ord_order_key)",
}
TRIP_M = {
    "Trip Count": "COUNT(f.trip_id)",
    "Total Trip Distance": "SUM(f.trip_trip_distance)",
    "Fare Amount": "SUM(f.trip_fare_amount)",
    "Tip Amount (All Payment Types)": "SUM(f.trip_tip_amount)",
    "Tolls Amount": "SUM(f.trip_tolls_amount)",
    "Gross Trip Revenue": "SUM(f.trip_total_amount)",
    "Card Tips": "SUM(CASE WHEN f.trip_payment_type = 1 THEN f.trip_tip_amount END)",
    "Distinct OD Pairs": "COUNT(DISTINCT f.trip_od_pair_id)",
    "Fare per Mile": "CAST(SUM(f.trip_fare_amount) AS DOUBLE) / NULLIF(CAST(SUM(f.trip_trip_distance) AS DOUBLE), 0)",
}
YTD_RANGE = "f.trip_pickup_date BETWEEN DATE_TRUNC('year', DATE '{a}') AND DATE '{a}'"
STLY_RANGE = ("f.trip_pickup_date BETWEEN DATE_TRUNC('year', DATE '{a}') - INTERVAL 1 YEAR "
              "AND CAST(DATE '{a}' - INTERVAL 1 YEAR AS DATE)")
MTD_RANGE = "f.trip_pickup_date BETWEEN DATE_TRUNC('month', DATE '{a}') AND DATE '{a}'"
ANCHORED_M = {
    "Revenue YTD": f"SUM(CASE WHEN {YTD_RANGE} THEN f.trip_total_amount END)",
    "Revenue YTD Same Time Last Year": f"SUM(CASE WHEN {STLY_RANGE} THEN f.trip_total_amount END)",
    "Revenue YoY % vs STLY": (f"(SUM(CASE WHEN {YTD_RANGE} THEN f.trip_total_amount END) - "
                              f"SUM(CASE WHEN {STLY_RANGE} THEN f.trip_total_amount END)) / "
                              f"CAST(SUM(CASE WHEN {STLY_RANGE} THEN f.trip_total_amount END) AS DOUBLE)"),
    "Trips MTD": f"SUM(CASE WHEN {MTD_RANGE} THEN 1 END)",
    "Trips YTD": f"SUM(CASE WHEN {YTD_RANGE} THEN 1 END)",
    "MTD-to-YTD Daily Pace Index": (f"(CAST(COALESCE(SUM(CASE WHEN {MTD_RANGE} THEN 1 END), 0) AS DOUBLE) / "
                                    "DAYOFMONTH(DATE '{a}')) / (CAST(SUM(CASE WHEN " + YTD_RANGE +
                                    " THEN 1 END) AS DOUBLE) / DAYOFYEAR(DATE '{a}'))"),
}
STOCK_M = {"Closing Stock On Hand", "Units Sold Trailing 91 Days", "Days of Supply", "Closing Snapshot Date",
           "Snapshot Row Count"}
SHARE_M = {"Stock Group Revenue Share", "Revenue (All Stock Groups)"}
FACT_OF_TABLE = {"sales": SALES_M, "orders": ORDER_M, "trips": {**TRIP_M, **ANCHORED_M}}
ADHOC = {  # ad hoc VDS calculations used by the question specs
    "ZN([Trips MTD])": ("trips", "COALESCE(" + ANCHORED_M["Trips MTD"] + ", 0)"),
}


def _local(sql: str) -> str:
    return re.sub(r"\bslc\.(wwi|nyctaxi)\.", r"\1.", sql)


class Emulator:
    def __init__(self, con):
        """con: a DuckDB connection holding the oracle fixture tables wwi.* and nyctaxi.*."""
        self.con = con
        for ds in BY_NAME.values():
            for t in ds.tables:
                con.execute(f'CREATE OR REPLACE VIEW "{ds.key}__{t.id}" AS {_local(t.sql)}')

    # ------------------------------------------------------------------ model navigation

    @staticmethod
    def _table_of(ds: DataSource, col_name: str) -> str:
        for t in ds.tables:
            if any(c.name == col_name for c in t.cols):
                return t.id
        raise KeyError(col_name)

    @staticmethod
    def _path(ds: DataSource, start: str, target: str, facts: set[str]) -> list[tuple[str, str, list]]:
        """Relationship edges (from, to, pairs) from start to target, never passing through another fact."""
        frontier, seen = [(start, [])], {start}
        while frontier:
            node, path = frontier.pop(0)
            if node == target:
                return path
            for r in ds.rels:
                for a, b, pairs in ((r.first, r.second, r.pairs), (r.second, r.first, [(y, x) for x, y in r.pairs])):
                    if a == node and b not in seen and (b not in facts or b == target):
                        seen.add(b)
                        frontier.append((b, path + [(a, b, pairs)]))
        raise LookupError(f"{ds.name}: no relationship path from {start} to {target}")

    def _dim_expr(self, ds: DataSource, caption: str, anchor: str) -> tuple[str | None, str]:
        """(table id or None, SQL expression) for a dimension caption."""
        item = ds.fields()[caption]
        if isinstance(item, Col):
            t = self._table_of(ds, item.name)
            return t, f'"{t}".{item.name}'
        formulas = {
            "Dropoff Year": ("trips", 'YEAR("trips".trip_dropoff_date)'),
            "Dropoff Month Start Date": ("trips", "CAST(DATE_TRUNC('month', \"trips\".trip_dropoff_date) AS DATE)"),
            "As-of Day of Month": (None, f"DAYOFMONTH(DATE '{anchor}')"),
            "As-of Day of Year": (None, f"DAYOFYEAR(DATE '{anchor}')"),
        }
        if caption not in formulas:
            raise KeyError(f"no emulation for dimension {caption!r}")
        return formulas[caption]

    def _from(self, ds: DataSource, fact: str, tables: set[str], skip: set[str] = frozenset()) -> str:
        facts = {"sales", "orders", "stock_daily", "trips"} & {t.id for t in ds.tables}
        sql = f'"{ds.key}__{fact}" AS "{fact}"'
        joined = {fact}
        for t in sorted(tables - {fact, None} - set(skip)):
            for a, b, pairs in self._path(ds, fact, t, facts):
                if b in joined:
                    continue
                on = " AND ".join(f'"{a}".{x} = "{b}".{y}' for x, y in pairs)
                sql += f' LEFT JOIN "{ds.key}__{b}" AS "{b}" ON {on}'
                joined.add(b)
        return sql

    def _where(self, ds: DataSource, filters: list, anchor: str, skip_tables: set[str] = frozenset()) -> tuple[list, set]:
        clauses, tables = [], set()
        for f in filters:
            t, expr = self._dim_expr(ds, f["field"]["fieldCaption"], anchor)
            if t in skip_tables:
                continue
            tables.add(t)
            kind = f["filterType"]
            if kind == "SET":
                vals = ", ".join(self._lit(v) for v in f["values"])
                clauses.append(f"{expr} {'NOT IN' if f.get('exclude') else 'IN'} ({vals})")
            elif kind == "QUANTITATIVE_DATE":
                clauses.append(f"{expr} BETWEEN DATE '{f['minDate']}' AND DATE '{f['maxDate']}'")
            elif kind == "QUANTITATIVE_NUMERICAL":
                if "min" in f:
                    clauses.append(f"{expr} >= {f['min']}")
                if "max" in f:
                    clauses.append(f"{expr} <= {f['max']}")
            else:
                raise NotImplementedError(kind)
        return clauses, tables

    @staticmethod
    def _lit(v) -> str:
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)):
            return f"DATE '{v}'"
        return "'" + str(v).replace("'", "''") + "'"

    # ------------------------------------------------------------------ evaluation

    def _group(self, ds, fact, dims, measures, filters, anchor, skip=frozenset()) -> str:
        dim_sql = [(a, *self._dim_expr(ds, c, anchor)) for c, a in dims if c not in skip]
        where, ftables = self._where(ds, filters, anchor)
        tables = {t for _, t, _ in dim_sql} | ftables
        sel = [f'{e} AS "{a}"' for a, _, e in dim_sql] + [f'{m} AS "{a}"' for a, m in measures]
        sql = f"SELECT {', '.join(sel)} FROM {self._from(ds, fact, tables)}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if dim_sql:
            sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(dim_sql)))
        return sql

    def execute(self, spec: dict) -> tuple[list[str], list[tuple]]:
        ds = BY_NAME[spec["datasource"]]
        q = spec["query"]
        params = {p["parameterCaption"]: p["value"] for p in q.get("parameters", [])}
        anchor = params.get("As-of Date", "2024-12-31")
        fields = ds.fields()
        dims, groups, stock, share = [], {}, [], []
        for f in q["fields"]:
            cap, alias = f["fieldCaption"], f["fieldAlias"]
            if "calculation" in f:
                if f["calculation"] == "COUNTD([Stock Group])":
                    groups.setdefault("memberships", []).append((alias, "COUNT(DISTINCT \"stock_group\".sg_stock_group_name)"))
                    continue
                fact, sql = ADHOC[f["calculation"]]
                groups.setdefault(fact, []).append((alias, sql.format(a=anchor).replace("f.", '"trips".')))
                continue
            item = fields[cap]
            if isinstance(item, Calc) and item.role == "measure":
                if cap in STOCK_M:
                    stock.append((cap, alias))
                elif cap in SHARE_M:
                    share.append((cap, alias))
                else:
                    fact = next(t for t, ms in FACT_OF_TABLE.items() if cap in ms and t in {x.id for x in ds.tables})
                    groups.setdefault(fact, []).append((alias, FACT_OF_TABLE[fact][cap].format(a=anchor)
                                                        .replace("f.", f'"{fact}".')))
            else:
                dims.append((cap, alias))
        parts = []
        for fact, measures in groups.items():
            if fact == "memberships":
                dim_sql = [(a, *self._dim_expr(ds, c, anchor)) for c, a in dims]
                sel = [f'{e} AS "{a}"' for a, _, e in dim_sql] + [f'{m} AS "{a}"' for a, m in measures]
                sql = (f'SELECT {", ".join(sel)} FROM "{ds.key}__stock_item" AS "stock_item" LEFT JOIN '
                       f'"{ds.key}__stock_group" AS "stock_group" ON "stock_item".si_wwi_stock_item_id = '
                       f'"stock_group".sg_wwi_stock_item_id GROUP BY ' + ", ".join(str(i + 1) for i in range(len(dims))))
                parts.append(sql)
            else:
                parts.append(self._group(ds, fact, dims, measures, q.get("filters", []), anchor))
        if share:
            parts.append(self._share(ds, dims, share, q.get("filters", []), anchor))
        if stock:
            parts.append(self._stock(ds, dims, stock, q.get("filters", []), anchor))
        if not parts:
            return self._members(ds, dims, q.get("filters", []), anchor)
        return self._stitch(dims, parts, [f["fieldAlias"] for f in q["fields"]])

    def _share(self, ds, dims, share, filters, anchor) -> str:
        rev = "SUM(\"sales\".sale_total_excluding_tax)"
        num = self._group(ds, "sales", dims, [("__num", rev)], filters, anchor)
        rest = [(c, a) for c, a in dims if c != "Stock Group"]
        den = self._group(ds, "sales", rest, [("__den", rev)], [f for f in filters
                                                                 if f["field"]["fieldCaption"] != "Stock Group"], anchor)
        on = " AND ".join(f'n."{a}" IS NOT DISTINCT FROM d."{a}"' for _, a in rest) or "TRUE"
        sel = [f'n."{a}"' for _, a in dims]
        for cap, alias in share:
            expr = "CAST(n.__num AS DOUBLE) / NULLIF(d.__den, 0)" if cap == "Stock Group Revenue Share" else "d.__den"
            sel.append(f'{expr} AS "{alias}"')
        return f"SELECT {', '.join(sel)} FROM ({num}) n LEFT JOIN ({den}) d ON {on}"

    def _stock(self, ds, dims, stock, filters, anchor) -> str:
        daily = self._group(ds, "stock_daily", dims + [("Snapshot Date", "__d")],
                            [("__q", 'SUM("stock_daily".stk_quantity_on_hand)'),
                             ("__u", 'SUM("stock_daily".stk_units_sold_91d)'), ("__n", "COUNT(*)")], filters, anchor)
        keys = [a for _, a in dims]
        # d* is the period's last snapshot date with item and group attributes removed (EXCLUDE semantics).
        date_keys = [a for c, a in dims if c == "Snapshot Date" or self._dim_expr(ds, c, anchor)[0] == "date"]
        dpart = ", ".join(f'"{k}"' for k in date_keys)
        part = ", ".join(f'"{k}"' for k in keys)
        ranked = (f"SELECT *, MAX(__d) OVER ({'PARTITION BY ' + dpart if date_keys else ''}) AS __dmax, "
                  f"SUM(__n) OVER ({'PARTITION BY ' + part if keys else ''}) AS __rows FROM ({daily}) x")
        exprs = {
            "Closing Stock On Hand": "__q",
            "Units Sold Trailing 91 Days": "__u",
            "Days of Supply": "CAST(__q AS DOUBLE) / (__u / 91.0)",
            "Closing Snapshot Date": "__dmax",
            "Snapshot Row Count": "__rows",
        }
        sel = [f'"{k}"' for k in keys] + [f'{exprs[c]} AS "{a}"' for c, a in stock]
        return f"SELECT {', '.join(sel)} FROM ({ranked}) r WHERE __d = __dmax"

    def _members(self, ds, dims, filters, anchor) -> tuple[list[str], list[tuple]]:
        dim_sql = [(a, *self._dim_expr(ds, c, anchor)) for c, a in dims]
        where, ftables = self._where(ds, filters, anchor)
        tables = [t for _, t, _ in dim_sql] + sorted(ftables)
        base = tables[0]
        from_sql = self._from(ds, base, set(tables))
        sql = f"SELECT DISTINCT {', '.join(f'{e} AS {chr(34)}{a}{chr(34)}' for a, _, e in dim_sql)} FROM {from_sql}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        cur = self.con.execute(sql)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]

    def _stitch(self, dims, parts, order) -> tuple[list[str], list[tuple]]:
        """Full outer combination of per-fact results on the shared dimension aliases."""
        keys = [a for _, a in dims]
        q = lambda a: '"' + a + '"'  # noqa: E731
        if len(parts) == 1:
            sql = f"SELECT {', '.join(q(a) for a in order)} FROM ({parts[0]}) p"
        else:
            owners = {}
            for i, p in enumerate(parts):
                for a in order:
                    if a not in keys and f'AS "{a}"' in p:
                        owners.setdefault(a, i)
            if keys:
                union = " UNION ".join(f"SELECT {', '.join(q(k) for k in keys)} FROM ({p}) u{i}"
                                       for i, p in enumerate(parts))
            else:
                union = "SELECT 1 AS __one"
            cols = [f"k.{q(a)}" if a in keys else f"p{owners[a]}.{q(a)}" for a in order]
            sql = f"SELECT {', '.join(cols)} FROM ({union}) k"
            for i, p in enumerate(parts):
                on = " AND ".join(f"k.{q(a)} IS NOT DISTINCT FROM p{i}.{q(a)}" for a in keys) or "TRUE"
                sql += f" LEFT JOIN ({p}) p{i} ON {on}"
        cur = self.con.execute(sql)
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]


def fixture_connection():
    """A DuckDB connection with the oracle fixture tables loaded (the oracle's own loader)."""
    oracle = HERE.parents[1] / "01-spec" / "oracle"
    if str(oracle) not in sys.path:
        sys.path.insert(0, str(oracle))
    import run_oracle

    engine = run_oracle.DuckDBEngine(fixtures=oracle / "fixtures")
    return engine, engine.con


__all__ = ["Emulator", "fixture_connection"]
