"""Stack-native answers to the 70 questions of SPEC § 7 for stack S3 (Tableau).

Each answer is a set of VizQL Data Service queries against the published data sources plus an assembly statement
(DuckDB SQL) over their results. Division of labor:

- Tableau computes every measure: sums, distinct counts, ratios of sums, LOD-based shares, semi-additive closing
  stock, trailing 91-day windows and As-of-Date period-to-date measures.
- Assembly only selects, joins, pivots one value per cell, ranks, and applies arithmetic to values Tableau returned
  (differences, change %, a combined share of ten listed items). It never reads fact rows.
- VDS queries are independent, so a drill path ("the top territory, then its peak month") is answered by querying each
  grain once and selecting in assembly (guide § 3.5).
- Fact-driven queries carry the fact's row-count measure (lines, order_lines, snap_rows, trips) and assembly keeps rows
  where it is positive, reproducing the oracle's inner-join semantics whatever join the relationship model chooses.
  Dimension-driven answers (Q-W-S2-P, Q-N-S2-D4, Q-N-C2-D4) take their member list from a dimension-only query.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from vds import agg, calc, date_range, dim, in_set, query

HERE = Path(__file__).resolve().parent
BANK = {q["id"]: q for q in yaml.safe_load(
    (HERE.parents[1] / "01-spec" / "oracle" / "questions.yaml").read_text())["questions"]}

WS = "SLC WWI Sales and Orders"
STK = "SLC WWI Stock"
NYC = "SLC NYC Trips"

FY = lambda *years: in_set("Fiscal Year", list(years))  # noqa: E731
CY = lambda *years: in_set("Calendar Year", list(years))  # noqa: E731
PY = lambda *years: in_set("Pickup Year", list(years))  # noqa: E731
LINES = agg("Sales Line Count", "lines")
ORDER_LINES = agg("Order Line Count", "order_lines")
SNAP_ROWS = agg("Snapshot Row Count", "snap_rows")
TRIPS = agg("Trip Count", "trips")
REV = agg("Revenue (Excl. Tax)", "revenue")
MANHATTAN = in_set("Pickup Borough", ["Manhattan"])
MANHATTAN_DROPOFF = in_set("Dropoff Borough", ["Manhattan"])
AIRPORTS = in_set("Pickup Service Zone", ["Airports"])

SPECS: dict[str, dict] = {}


def Q(qid: str, queries: dict[str, dict], assemble: str, note: str | None = None) -> None:
    spec = {"question": qid, "text": BANK[qid]["question"], "interpretation": BANK[qid]["interpretation"],
            "generated_by": "build_tableau.py (question_specs.py)", "queries": queries,
            "assemble": " ".join(assemble.split())}
    if note:
        spec["note"] = note
    SPECS[qid] = spec


def month_ends(year: int) -> list[str]:
    import calendar
    return [f"{year}-{m:02d}-{calendar.monthrange(year, m)[1]:02d}" for m in range(1, 13)]


# =========================================================================== W-S1 revenue

Q("Q-W-S1-P", {
    "q": query(WS, [dim("Sales Territory", "sales_territory"), dim("Fiscal Month", "fiscal_month"),
                    dim("Month Start Date", "month_start_date"), REV, LINES], [FY(2015)]),
}, "SELECT sales_territory, fiscal_month, month_start_date, revenue FROM q WHERE lines > 0 "
   "ORDER BY sales_territory, fiscal_month")

Q("Q-W-S1-D1", {
    "territories": query(WS, [dim("Sales Territory", "sales_territory"), REV, LINES], [FY(2015)]),
    "months": query(WS, [dim("Sales Territory", "sales_territory"), dim("Fiscal Month", "fiscal_month"), REV, LINES],
                    [FY(2015)]),
    "states": query(WS, [dim("Sales Territory", "sales_territory"), dim("Fiscal Month", "fiscal_month"),
                         dim("State Province", "state_province"), REV, LINES], [FY(2015)]),
    "cities": query(WS, [dim("Sales Territory", "sales_territory"), dim("Fiscal Month", "fiscal_month"),
                         dim("State Province", "state_province"), dim("City", "city"), REV, LINES], [FY(2015)]),
}, """
WITH t AS (SELECT sales_territory FROM territories WHERE lines > 0 ORDER BY revenue DESC, sales_territory LIMIT 1),
m AS (SELECT months.fiscal_month FROM months JOIN t USING (sales_territory) WHERE lines > 0
      ORDER BY revenue DESC, fiscal_month LIMIT 1)
SELECT grain, sales_territory, fiscal_month, state_province, city, revenue FROM (
  SELECT 'state' AS grain, s.sales_territory, s.fiscal_month, s.state_province, CAST(NULL AS VARCHAR) AS city, s.revenue
  FROM states s JOIN t USING (sales_territory) JOIN m USING (fiscal_month) WHERE s.lines > 0
  UNION ALL
  SELECT 'city', c.sales_territory, c.fiscal_month, c.state_province, c.city, c.revenue
  FROM cities c JOIN t USING (sales_territory) JOIN m USING (fiscal_month) WHERE c.lines > 0
) r ORDER BY grain DESC, state_province, city NULLS FIRST""")

Q("Q-W-S1-D2", {
    "territories": query(WS, [dim("Sales Territory", "sales_territory"), REV, LINES], [FY(2015)]),
    "items": query(WS, [dim("Sales Territory", "sales_territory"), dim("WWI Stock Item ID", "wwi_stock_item_id"),
                        dim("Stock Item", "stock_item"), REV, LINES], [FY(2015)]),
}, """
WITH t AS (SELECT sales_territory, revenue AS territory_revenue FROM territories WHERE lines > 0
           ORDER BY revenue DESC, sales_territory LIMIT 1),
ranked AS (SELECT i.wwi_stock_item_id, i.stock_item, i.revenue,
                  ROW_NUMBER() OVER (ORDER BY i.revenue DESC, i.wwi_stock_item_id) AS rank_no
           FROM items i JOIN t USING (sales_territory) WHERE i.lines > 0),
top10 AS (SELECT * FROM ranked WHERE rank_no <= 10)
SELECT t.sales_territory, x.rank_no, x.wwi_stock_item_id, x.stock_item, x.revenue,
       x.revenue / t.territory_revenue AS share_of_territory,
       (SELECT SUM(revenue) FROM top10) / t.territory_revenue AS top10_combined_share
FROM top10 x CROSS JOIN t ORDER BY x.rank_no""")

Q("Q-W-S1-D3", {
    "q": query(WS, [dim("Buying Group", "buying_group"), dim("Customer Category", "customer_category"),
                    dim("Fiscal Year", "fiscal_year"), REV, LINES], [FY(2014, 2015)]),
}, """
SELECT buying_group, customer_category,
       MAX(CASE WHEN fiscal_year = 2014 THEN revenue END) AS revenue_fy2014,
       MAX(CASE WHEN fiscal_year = 2015 THEN revenue END) AS revenue_fy2015,
       MAX(CASE WHEN fiscal_year = 2015 THEN revenue END)
         / NULLIF(MAX(CASE WHEN fiscal_year = 2014 THEN revenue END), 0) - 1 AS change_pct
FROM q WHERE lines > 0 GROUP BY buying_group, customer_category ORDER BY buying_group, customer_category""")

Q("Q-W-S1-D4", {
    "as_was": query(WS, [dim("Color", "color"), REV, LINES], [FY(2015)]),
    "as_is": query(WS, [dim("Current Color", "color"), REV, LINES], [FY(2015)]),
}, """
WITH w AS (SELECT color, revenue FROM as_was WHERE lines > 0),
i AS (SELECT color, revenue FROM as_is WHERE lines > 0),
colors AS (SELECT color FROM w UNION SELECT color FROM i)
SELECT c.color, w.revenue AS revenue_as_was, i.revenue AS revenue_as_is,
       COALESCE(w.revenue, 0) <> COALESCE(i.revenue, 0) AS differs
FROM colors c LEFT JOIN w ON w.color = c.color LEFT JOIN i ON i.color = c.color ORDER BY c.color""")

# =========================================================================== W-S2 ordered quantity (multi-fact)

Q("Q-W-S2-P", {
    "months": query(WS, [dim("Month Start Date", "month_start_date")], [CY(2015)]),
    "q": query(WS, [dim("Month Start Date", "month_start_date"), agg("Ordered Quantity", "ordered_quantity"), REV],
               [CY(2015)]),
}, """
SELECT m.month_start_date, q.ordered_quantity, q.revenue
FROM months m LEFT JOIN q ON q.month_start_date = m.month_start_date ORDER BY m.month_start_date""",
  note="One query returns orders (by order date) and revenue (by invoice date) on the shared Date table; the month "
       "axis is the Date table's own domain (dimension-only query).")

GAP_MONTHS = query(WS, [dim("Month Start Date", "month_start_date"), agg("Ordered Quantity", "ordered_quantity"),
                        agg("Units Sold", "units_sold")], [CY(2015)])
GAP_SQL = ("SELECT month_start_date, ordered_quantity, units_sold FROM gap "
           "WHERE ordered_quantity IS NOT NULL AND units_sold IS NOT NULL "
           "ORDER BY ABS(ordered_quantity - units_sold) DESC, month_start_date LIMIT 1")

Q("Q-W-S2-D1", {
    "gap": GAP_MONTHS,
    "items": query(WS, [dim("Month Start Date", "month_start_date"), dim("WWI Stock Item ID", "wwi_stock_item_id"),
                        dim("Stock Item", "stock_item"), agg("Ordered Quantity", "ordered_quantity"), ORDER_LINES],
                   [CY(2015)]),
}, f"""
WITH g AS ({GAP_SQL})
SELECT g.month_start_date, g.ordered_quantity AS month_ordered_quantity, g.units_sold AS month_units_sold,
       i.wwi_stock_item_id, i.stock_item, i.ordered_quantity
FROM items i JOIN g ON g.month_start_date = i.month_start_date WHERE i.order_lines > 0
ORDER BY i.ordered_quantity DESC, i.wwi_stock_item_id""")

Q("Q-W-S2-D2", {
    "gap": GAP_MONTHS,
    "pickers": query(WS, [dim("Month Start Date", "month_start_date"), dim("Picker", "picker"),
                          agg("Ordered Quantity", "ordered_quantity"), ORDER_LINES], [CY(2015)]),
}, f"""
WITH g AS ({GAP_SQL})
SELECT g.month_start_date, p.picker, p.ordered_quantity
FROM pickers p JOIN g ON g.month_start_date = p.month_start_date WHERE p.order_lines > 0
ORDER BY p.ordered_quantity DESC, p.picker NULLS FIRST""")

Q("Q-W-S2-D3", {
    "q": query(WS, [dim("Selling Package", "selling_package"), dim("Calendar Quarter", "calendar_quarter"),
                    dim("Calendar Year", "calendar_year"), agg("Ordered Quantity", "ordered_quantity"), ORDER_LINES],
               [CY(2014, 2015)]),
}, """
SELECT selling_package, calendar_quarter,
       MAX(CASE WHEN calendar_year = 2014 THEN ordered_quantity END) AS ordered_quantity_2014,
       MAX(CASE WHEN calendar_year = 2015 THEN ordered_quantity END) AS ordered_quantity_2015,
       CAST(MAX(CASE WHEN calendar_year = 2015 THEN ordered_quantity END) AS DOUBLE)
         / NULLIF(CAST(MAX(CASE WHEN calendar_year = 2014 THEN ordered_quantity END) AS DOUBLE), 0) - 1 AS change_pct
FROM q WHERE order_lines > 0 GROUP BY selling_package, calendar_quarter ORDER BY selling_package, calendar_quarter""")

Q("Q-W-S2-D4", {
    "groups": query(WS, [dim("Salesperson", "salesperson"), dim("Stock Group", "stock_group_name"),
                         agg("Backordered Order Lines", "backordered_lines")], [CY(2015)]),
    "people": query(WS, [dim("Salesperson", "salesperson"), agg("Backordered Order Lines", "total_lines")],
                    [CY(2015)]),
}, """
WITH p AS (SELECT salesperson, total_lines FROM people WHERE total_lines IS NOT NULL),
top_sp AS (SELECT salesperson FROM p ORDER BY total_lines DESC, salesperson LIMIT 1)
SELECT g.salesperson, g.stock_group_name, g.backordered_lines, p.total_lines AS salesperson_total_lines,
       g.salesperson = t.salesperson AS is_top_salesperson
FROM groups g JOIN p ON p.salesperson = g.salesperson CROSS JOIN top_sp t
WHERE g.backordered_lines IS NOT NULL ORDER BY g.salesperson, g.stock_group_name""",
  note="salesperson_total_lines comes from a query without Stock Group, which Tableau answers without the bridge, "
       "so each backordered line counts once.")

# =========================================================================== W-M1 gross margin %

GM = agg("Gross Margin %", "gross_margin_pct")
PROFIT = agg("Gross Profit", "profit")

Q("Q-W-M1-P", {
    "q": query(WS, [dim("Customer Category", "customer_category"), dim("Fiscal Quarter", "fiscal_quarter"), REV, PROFIT,
                    GM, LINES], [FY(2015)]),
}, "SELECT customer_category, fiscal_quarter, revenue, profit, gross_margin_pct FROM q WHERE lines > 0 "
   "ORDER BY customer_category, fiscal_quarter")

LOW_CAT = query(WS, [dim("Customer Category", "customer_category"), GM, LINES], [FY(2015)])
CAT_ITEMS = query(WS, [dim("Customer Category", "customer_category"), dim("WWI Stock Item ID", "wwi_stock_item_id"),
                       dim("Stock Item", "stock_item"), REV, PROFIT, GM, LINES], [FY(2015)])
LOW_SQL = ("SELECT customer_category FROM cats WHERE lines > 0 "
           "ORDER BY gross_margin_pct, customer_category LIMIT 1")
TOP10_SQL = ("SELECT i.*, ROW_NUMBER() OVER (ORDER BY i.gross_margin_pct, i.wwi_stock_item_id) AS rank_no "
             "FROM items i JOIN low USING (customer_category) WHERE i.lines > 0 AND i.revenue > 10000")

Q("Q-W-M1-D1", {"cats": LOW_CAT, "items": CAT_ITEMS}, f"""
WITH low AS ({LOW_SQL}), ranked AS ({TOP10_SQL})
SELECT customer_category, rank_no, wwi_stock_item_id, stock_item, revenue, profit, gross_margin_pct
FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

Q("Q-W-M1-D2", {
    "cats": LOW_CAT, "items": CAT_ITEMS,
    "territories": query(WS, [dim("Customer Category", "customer_category"),
                              dim("WWI Stock Item ID", "wwi_stock_item_id"), dim("Stock Item", "stock_item"),
                              dim("Sales Territory", "sales_territory"), REV, PROFIT, GM, LINES], [FY(2015)]),
}, f"""
WITH low AS ({LOW_SQL}), ranked AS ({TOP10_SQL}), top10 AS (SELECT wwi_stock_item_id FROM ranked WHERE rank_no <= 10)
SELECT t.wwi_stock_item_id, t.stock_item, t.sales_territory, t.revenue, t.profit, t.gross_margin_pct
FROM territories t JOIN low USING (customer_category) JOIN top10 USING (wwi_stock_item_id) WHERE t.lines > 0
ORDER BY t.wwi_stock_item_id, t.sales_territory""")

Q("Q-W-M1-D3", {
    "q": query(WS, [dim("Selling Package", "selling_package"), dim("Fiscal Year", "fiscal_year"), GM, LINES],
               [FY(2014, 2015)]),
}, """
WITH g AS (SELECT selling_package,
                  MAX(CASE WHEN fiscal_year = 2014 THEN gross_margin_pct END) AS gm_2014,
                  MAX(CASE WHEN fiscal_year = 2015 THEN gross_margin_pct END) AS gm_2015
           FROM q WHERE lines > 0 GROUP BY selling_package)
SELECT selling_package, gm_2014 AS gross_margin_pct_fy2014, gm_2015 AS gross_margin_pct_fy2015,
       (gm_2015 - gm_2014) * 100 AS change_points FROM g ORDER BY selling_package""")

Q("Q-W-M1-D4", {
    "people": query(WS, [dim("Salesperson", "salesperson"), dim("Fiscal Year", "fiscal_year"), GM, LINES],
                    [FY(2014, 2015)]),
    "groups": query(WS, [dim("Salesperson", "salesperson"), dim("Stock Group", "stock_group_name"),
                         dim("Fiscal Year", "fiscal_year"), GM, REV, LINES], [FY(2014, 2015)]),
}, """
WITH sp AS (SELECT salesperson,
                   MAX(CASE WHEN fiscal_year = 2014 THEN gross_margin_pct END) AS gm_2014,
                   MAX(CASE WHEN fiscal_year = 2015 THEN gross_margin_pct END) AS gm_2015
            FROM people WHERE lines > 0 GROUP BY salesperson),
worst AS (SELECT salesperson, gm_2014, gm_2015 FROM sp ORDER BY gm_2015 - gm_2014, salesperson LIMIT 1),
bg AS (SELECT g.stock_group_name,
              MAX(CASE WHEN g.fiscal_year = 2014 THEN g.gross_margin_pct END) AS gm_2014,
              MAX(CASE WHEN g.fiscal_year = 2015 THEN g.gross_margin_pct END) AS gm_2015,
              MAX(CASE WHEN g.fiscal_year = 2015 THEN g.revenue END) AS revenue_fy2015
       FROM groups g JOIN worst w ON w.salesperson = g.salesperson WHERE g.lines > 0 GROUP BY g.stock_group_name)
SELECT w.salesperson, w.gm_2014 AS salesperson_gm_fy2014, w.gm_2015 AS salesperson_gm_fy2015, bg.stock_group_name,
       bg.gm_2014 AS group_gm_fy2014, bg.gm_2015 AS group_gm_fy2015, (bg.gm_2015 - bg.gm_2014) * 100 AS group_change_points,
       bg.revenue_fy2015
FROM bg CROSS JOIN worst w ORDER BY group_change_points NULLS FIRST, bg.stock_group_name""")

# =========================================================================== W-M2 closing stock (semi-additive)

CLOSE = agg("Closing Stock On Hand", "closing_units")
CLOSE_DATE = agg("Closing Snapshot Date", "closing_date")
FY2015_END = date_range("Snapshot Date", "2015-10-31", "2015-10-31")

Q("Q-W-M2-P", {
    "q": query(STK, [dim("Fiscal Month", "fiscal_month"), CLOSE_DATE, CLOSE, SNAP_ROWS], [FY(2015)]),
}, "SELECT fiscal_month, closing_date AS month_end_date, closing_units FROM q WHERE snap_rows > 0 "
   "ORDER BY fiscal_month")

Q("Q-W-M2-D1", {
    "groups": query(STK, [dim("Stock Group", "stock_group_name"), CLOSE, SNAP_ROWS], [FY(2015)]),
    "total": query(STK, [CLOSE, SNAP_ROWS], [FY(2015)]),
}, """
SELECT grain, stock_group_name, closing_units FROM (
  SELECT 'group' AS grain, stock_group_name, closing_units FROM groups WHERE snap_rows > 0
  UNION ALL SELECT 'total', CAST(NULL AS VARCHAR), closing_units FROM total WHERE snap_rows > 0
) r ORDER BY grain, stock_group_name NULLS FIRST""")

Q("Q-W-M2-D2", {
    "groups": query(STK, [dim("Stock Group", "stock_group_name"), CLOSE, SNAP_ROWS], [FY2015_END]),
    "items": query(STK, [dim("Stock Group", "stock_group_name"), dim("WWI Stock Item ID", "wwi_stock_item_id"),
                         dim("Stock Item", "stock_item"), CLOSE, SNAP_ROWS], [FY2015_END]),
}, """
WITH g AS (SELECT stock_group_name FROM groups WHERE snap_rows > 0 ORDER BY closing_units DESC, stock_group_name LIMIT 1),
ranked AS (SELECT i.stock_group_name, i.wwi_stock_item_id, i.stock_item, i.closing_units,
                  ROW_NUMBER() OVER (ORDER BY i.closing_units DESC, i.wwi_stock_item_id) AS rank_no
           FROM items i JOIN g USING (stock_group_name) WHERE i.snap_rows > 0)
SELECT stock_group_name, rank_no, wwi_stock_item_id, stock_item, closing_units FROM ranked WHERE rank_no <= 10
ORDER BY rank_no""")

Q("Q-W-M2-D3", {
    "q": query(STK, [dim("Selling Package", "selling_package"), dim("Is Chiller Stock", "is_chiller_stock"),
                     dim("Snapshot Date", "snapshot_date"), CLOSE, SNAP_ROWS],
               [in_set("Snapshot Date", ["2014-12-31", "2015-12-31"])]),
}, """
SELECT selling_package, is_chiller_stock,
       MAX(CASE WHEN snapshot_date = DATE '2014-12-31' THEN closing_units END) AS closing_units_2014,
       MAX(CASE WHEN snapshot_date = DATE '2015-12-31' THEN closing_units END) AS closing_units_2015,
       MAX(CASE WHEN snapshot_date = DATE '2015-12-31' THEN closing_units END)
         - MAX(CASE WHEN snapshot_date = DATE '2014-12-31' THEN closing_units END) AS change_units
FROM q WHERE snap_rows > 0 GROUP BY selling_package, is_chiller_stock ORDER BY selling_package, is_chiller_stock""")

Q("Q-W-M2-D4", {
    "month_ends": query(STK, [dim("WWI Stock Item ID", "wwi_stock_item_id"), dim("Month Start Date", "month_start_date"),
                              dim("Balance Basis", "balance_basis"), CLOSE_DATE, CLOSE, SNAP_ROWS], [CY(2015)]),
    "names": query(STK, [dim("WWI Stock Item ID", "wwi_stock_item_id"), dim("Current Stock Item", "stock_item")]),
}, """
WITH e AS (SELECT wwi_stock_item_id, closing_date AS d_star, closing_units, balance_basis
           FROM month_ends WHERE snap_rows > 0),
item_min AS (SELECT wwi_stock_item_id, MIN(closing_units) AS min_closing_units FROM e GROUP BY wwi_stock_item_id),
first_at_min AS (SELECT m.wwi_stock_item_id, m.min_closing_units, MIN(e.d_star) AS month_end_date,
                        MAX(e.balance_basis) AS balance_basis
                 FROM item_min m JOIN e ON e.wwi_stock_item_id = m.wwi_stock_item_id
                  AND e.closing_units = m.min_closing_units
                 GROUP BY m.wwi_stock_item_id, m.min_closing_units),
ranked AS (SELECT f.*, ROW_NUMBER() OVER (ORDER BY f.min_closing_units, f.wwi_stock_item_id) AS rank_no FROM first_at_min f)
SELECT r.rank_no, r.wwi_stock_item_id, n.stock_item, r.min_closing_units, r.month_end_date, r.balance_basis
FROM ranked r JOIN names n ON n.wwi_stock_item_id = r.wwi_stock_item_id WHERE r.rank_no <= 10 ORDER BY r.rank_no""",
  note="Tableau returns each item's closing stock per month end (semi-additive measure); selecting each item's "
       "minimum month and ranking happens in assembly.")

# =========================================================================== W-C1 stock group share (many-to-many)

SHARE = agg("Stock Group Revenue Share", "share")

Q("Q-W-C1-P", {
    "groups": query(WS, [dim("Stock Group", "stock_group_name"), REV, SHARE, LINES], [FY(2015)]),
    "total": query(WS, [REV, SHARE, LINES], [FY(2015)]),
}, """
SELECT grain, stock_group_name, revenue, share FROM (
  SELECT 'group' AS grain, stock_group_name, revenue, share FROM groups WHERE lines > 0 AND stock_group_name IS NOT NULL
  UNION ALL SELECT 'total', CAST(NULL AS VARCHAR), revenue, share FROM total WHERE lines > 0
) r ORDER BY grain, stock_group_name NULLS FIRST""",
  note="Group rows sum each line into every group of its item (relationship through the bridge); the total row is the "
       "same measure without Stock Group, which Tableau answers without the bridge (deduplicated).")

Q("Q-W-C1-D1", {
    "groups": query(WS, [dim("Stock Group", "stock_group_name"), REV, LINES], [FY(2015)]),
    "items": query(WS, [dim("Stock Group", "stock_group_name"), dim("WWI Stock Item ID", "wwi_stock_item_id"),
                        dim("Stock Item", "stock_item"), REV, LINES], [FY(2015)]),
}, """
WITH g AS (SELECT stock_group_name, revenue AS group_revenue FROM groups WHERE lines > 0 AND stock_group_name IS NOT NULL
           ORDER BY revenue DESC, stock_group_name LIMIT 1)
SELECT g.stock_group_name, i.wwi_stock_item_id, i.stock_item, i.revenue, i.revenue / g.group_revenue AS share_of_group
FROM items i JOIN g USING (stock_group_name) WHERE i.lines > 0
ORDER BY share_of_group DESC, i.wwi_stock_item_id""")

Q("Q-W-C1-D2", {
    "q": query(WS, [dim("Sales Territory", "sales_territory"), dim("Stock Group", "stock_group_name"), REV, SHARE, LINES],
               [FY(2015)]),
}, "SELECT sales_territory, stock_group_name, revenue, share AS share_of_territory FROM q "
   "WHERE lines > 0 AND stock_group_name IS NOT NULL ORDER BY sales_territory, stock_group_name",
  note="share_of_territory is Stock Group Revenue Share itself: its EXCLUDE [Stock Group] denominator is the "
       "territory's deduplicated revenue.")

Q("Q-W-C1-D3", {
    "q": query(WS, [dim("Stock Group", "stock_group_name"), dim("Fiscal Year", "fiscal_year"), SHARE, LINES],
               [FY(2014, 2015)]),
}, """
WITH s AS (SELECT * FROM q WHERE lines > 0 AND stock_group_name IS NOT NULL),
cmp AS (SELECT a.stock_group_name, a.share AS share_fy2014, b.share AS share_fy2015,
               (b.share - a.share) * 100 AS change_points
        FROM s a JOIN s b ON b.stock_group_name = a.stock_group_name AND b.fiscal_year = 2015 WHERE a.fiscal_year = 2014),
top_gainer AS (SELECT stock_group_name FROM cmp ORDER BY change_points DESC, stock_group_name LIMIT 1)
SELECT c.stock_group_name, c.share_fy2014, c.share_fy2015, c.change_points, c.stock_group_name = t.stock_group_name
       AS is_top_gainer
FROM cmp c CROSS JOIN top_gainer t ORDER BY c.stock_group_name""")

Q("Q-W-C1-D4", {
    "items": query(WS, [dim("WWI Stock Item ID", "wwi_stock_item_id"), REV, LINES], [FY(2015)]),
    "memberships": query(WS, [dim("WWI Stock Item ID", "wwi_stock_item_id"),
                              calc("Group Memberships", "COUNTD([Stock Group])", "groups", "integer")]),
    "groups": query(WS, [dim("Stock Group", "stock_group_name"), REV, LINES], [FY(2015)]),
    "total": query(WS, [REV, LINES], [FY(2015)]),
}, """
WITH ir AS (SELECT wwi_stock_item_id, revenue FROM items WHERE lines > 0),
k AS (SELECT wwi_stock_item_id, groups FROM memberships WHERE groups > 0)
SELECT (SELECT SUM(revenue) FROM groups WHERE lines > 0 AND stock_group_name IS NOT NULL) AS sum_of_group_revenue,
       (SELECT revenue FROM total) AS total_revenue,
       (SELECT SUM(revenue) FROM groups WHERE lines > 0 AND stock_group_name IS NOT NULL)
         - (SELECT revenue FROM total) AS overlap_revenue,
       SUM(CASE WHEN k.groups >= 2 THEN ir.revenue * (k.groups - 1) ELSE 0 END) AS overlap_from_multi_group_items,
       SUM(CASE WHEN k.groups IS NULL THEN ir.revenue ELSE 0 END) AS revenue_without_group
FROM ir LEFT JOIN k ON k.wwi_stock_item_id = ir.wwi_stock_item_id""",
  note="The overlap check needs each item's group count; COUNTD([Stock Group]) per item is a dimension-table count "
       "issued as an ad hoc VDS calculation.")

# =========================================================================== W-C2 days of supply

DOS_FIELDS = [CLOSE, agg("Units Sold Trailing 91 Days", "units_sold_91d"), agg("Days of Supply", "days_of_supply"),
              SNAP_ROWS]
DEC_31 = date_range("Snapshot Date", "2015-12-31", "2015-12-31")

Q("Q-W-C2-P", {
    "q": query(STK, [dim("Month Start Date", "month_start_date"), CLOSE_DATE, *DOS_FIELDS], [CY(2015)]),
}, "SELECT closing_date AS month_end_date, closing_units, units_sold_91d, days_of_supply FROM q WHERE snap_rows > 0 "
   "ORDER BY closing_date")

Q("Q-W-C2-D1", {
    "q": query(STK, [dim("Stock Group", "stock_group_name"), *DOS_FIELDS], [DEC_31]),
}, "SELECT stock_group_name, closing_units, units_sold_91d, days_of_supply FROM q WHERE snap_rows > 0 "
   "AND stock_group_name IS NOT NULL ORDER BY stock_group_name")

Q("Q-W-C2-D2", {
    "q": query(STK, [dim("WWI Stock Item ID", "wwi_stock_item_id"), dim("Stock Item", "stock_item"), *DOS_FIELDS],
               [DEC_31]),
}, """
WITH ranked AS (SELECT q.*, ROW_NUMBER() OVER (ORDER BY days_of_supply, wwi_stock_item_id) AS rank_no
                FROM q WHERE snap_rows > 0 AND units_sold_91d > 0)
SELECT rank_no, wwi_stock_item_id, stock_item, closing_units, units_sold_91d, days_of_supply
FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

Q("Q-W-C2-D3", {
    "q": query(STK, [dim("Calendar Quarter", "calendar_quarter"), dim("Is Chiller Stock", "is_chiller_stock"),
                     CLOSE_DATE, *DOS_FIELDS], [CY(2015)]),
}, "SELECT calendar_quarter, closing_date AS quarter_end_date, is_chiller_stock, closing_units, units_sold_91d, "
   "days_of_supply FROM q WHERE snap_rows > 0 ORDER BY calendar_quarter, is_chiller_stock")

Q("Q-W-C2-D4", {
    "territories": query(WS, [dim("Sales Territory", "sales_territory"), LINES]),
}, """
SELECT sales_territory, CAST(NULL AS DOUBLE) AS days_of_supply,
       'non-conformed dimension: stock holdings carry no city' AS reason
FROM territories WHERE lines > 0 ORDER BY sales_territory""",
  note="SLC WWI Stock has no City table: stock is a separate published data source because a multi-fact model would "
       "repeat stock measures across the unrelated City dimension (guide § 3.3). Territories come from the sales "
       "data source.")

# =========================================================================== N-S1 gross trip revenue

NREV = agg("Gross Trip Revenue", "revenue")
TOP_MONTH = query(NYC, [dim("Pickup Month Start Date", "month_start_date"), NREV, TRIPS], [PY(2024)])
TOP_MONTH_SQL = ("SELECT month_start_date FROM months WHERE trips > 0 "
                 "ORDER BY revenue DESC, month_start_date LIMIT 1")

Q("Q-N-S1-P", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), dim("Pickup Month Start Date", "month_start_date"), NREV,
                     TRIPS], [PY(2024)]),
}, "SELECT pickup_borough, month_start_date, revenue FROM q WHERE trips > 0 ORDER BY pickup_borough, month_start_date")

Q("Q-N-S1-D1", {
    "months": TOP_MONTH,
    "zones": query(NYC, [dim("Pickup Month Start Date", "month_start_date"), dim("Pickup Zone ID", "pu_location_id"),
                         dim("Pickup Zone", "zone"), NREV, TRIPS], [PY(2024), MANHATTAN]),
}, f"""
WITH m AS ({TOP_MONTH_SQL}),
ranked AS (SELECT z.month_start_date, z.pu_location_id, z.zone, z.revenue,
                  ROW_NUMBER() OVER (ORDER BY z.revenue DESC, z.pu_location_id) AS rank_no
           FROM zones z JOIN m USING (month_start_date) WHERE z.trips > 0)
SELECT month_start_date, rank_no, pu_location_id, zone, revenue FROM ranked WHERE rank_no <= 15 ORDER BY rank_no""")

Q("Q-N-S1-D2", {
    "months": TOP_MONTH,
    "q": query(NYC, [dim("Pickup Month Start Date", "month_start_date"), dim("Pickup Hour", "pickup_hour"),
                     dim("Payment Type", "payment_type_name"), NREV, TRIPS], [PY(2024)]),
}, f"""
WITH m AS ({TOP_MONTH_SQL})
SELECT q.month_start_date, q.pickup_hour, q.payment_type_name, q.revenue
FROM q JOIN m USING (month_start_date) WHERE q.trips > 0 ORDER BY q.pickup_hour, q.payment_type_name""")

Q("Q-N-S1-D3", {
    "q": query(NYC, [dim("Pickup Calendar Month", "calendar_month"), dim("Pickup Year", "pickup_year"), NREV, TRIPS],
               [AIRPORTS]),
}, """
SELECT calendar_month,
       MAX(CASE WHEN pickup_year = 2023 THEN revenue END) AS revenue_2023,
       MAX(CASE WHEN pickup_year = 2024 THEN revenue END) AS revenue_2024,
       MAX(CASE WHEN pickup_year = 2024 THEN revenue END)
         / NULLIF(MAX(CASE WHEN pickup_year = 2023 THEN revenue END), 0) - 1 AS change_pct
FROM q WHERE trips > 0 GROUP BY calendar_month ORDER BY calendar_month""")

Q("Q-N-S1-D4", {
    "q": query(NYC, [dim("Dropoff Zone ID", "do_location_id"), dim("Dropoff Borough", "dropoff_borough"),
                     dim("Dropoff Zone", "dropoff_zone"), NREV, TRIPS],
               [PY(2024), in_set("Pickup Zone", ["JFK Airport"])]),
}, """
WITH ranked AS (SELECT q.*, ROW_NUMBER() OVER (ORDER BY revenue DESC, do_location_id) AS rank_no FROM q WHERE trips > 0)
SELECT rank_no, do_location_id, dropoff_borough, dropoff_zone, revenue FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

# =========================================================================== N-S2 card tips

CARD = agg("Card Tips", "card_tips")

Q("Q-N-S2-P", {
    "q": query(NYC, [dim("Vendor", "vendor_id"), dim("Pickup Month Start Date", "month_start_date"), CARD, TRIPS],
               [PY(2024)]),
}, "SELECT vendor_id, month_start_date, card_tips FROM q WHERE trips > 0 ORDER BY vendor_id, month_start_date")

Q("Q-N-S2-D1", {
    "q": query(NYC, [dim("Pickup Hour", "pickup_hour"), CARD, TRIPS],
               [in_set("Pickup Month Start Date", ["2024-12-01"])]),
}, "SELECT pickup_hour, card_tips FROM q WHERE trips > 0 ORDER BY pickup_hour")

Q("Q-N-S2-D2", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), dim("Dropoff Borough", "dropoff_borough"), CARD, TRIPS],
               [PY(2024)]),
}, "SELECT pickup_borough, dropoff_borough, card_tips FROM q WHERE trips > 0 ORDER BY pickup_borough, dropoff_borough")

Q("Q-N-S2-D3", {
    "q": query(NYC, [dim("Pickup Calendar Month", "calendar_month"), dim("Pickup Year", "pickup_year"), CARD, TRIPS],
               [in_set("Payment Type Code", [1])]),
}, """
SELECT calendar_month,
       MAX(CASE WHEN pickup_year = 2023 THEN card_tips / NULLIF(trips, 0) END) AS card_tips_per_card_trip_2023,
       MAX(CASE WHEN pickup_year = 2024 THEN card_tips / NULLIF(trips, 0) END) AS card_tips_per_card_trip_2024
FROM q WHERE trips > 0 GROUP BY calendar_month ORDER BY calendar_month""")

Q("Q-N-S2-D4", {
    "codes": query(NYC, [dim("Payment Type Code", "payment_type"), dim("Payment Type", "payment_type_name")]),
    "q": query(NYC, [dim("Payment Type Code", "payment_type"), CARD, TRIPS], [PY(2024)]),
}, """
SELECT c.payment_type, c.payment_type_name, q.card_tips
FROM codes c LEFT JOIN q ON q.payment_type = c.payment_type AND q.trips > 0 ORDER BY c.payment_type""",
  note="The member list is the Payment Type table's domain (dimension-only query), so codes without 2024 trips appear "
       "with blank card tips, as the oracle requires.")

# =========================================================================== N-M1 distinct OD pairs

OD = agg("Distinct OD Pairs", "distinct_od_pairs")

Q("Q-N-M1-P", {
    "q": query(NYC, [dim("Pickup Month Start Date", "month_start_date"), OD, TRIPS], [PY(2024)]),
}, "SELECT month_start_date, distinct_od_pairs FROM q WHERE trips > 0 ORDER BY month_start_date")

Q("Q-N-M1-D1", {
    "types": query(NYC, [dim("Payment Type", "payment_type_name"), OD, TRIPS], [PY(2024)]),
    "total": query(NYC, [OD, TRIPS], [PY(2024)]),
}, """
SELECT grain, payment_type_name, distinct_od_pairs FROM (
  SELECT 'payment_type' AS grain, payment_type_name, distinct_od_pairs FROM types WHERE trips > 0
  UNION ALL SELECT 'total', CAST(NULL AS VARCHAR), distinct_od_pairs FROM total WHERE trips > 0
  UNION ALL SELECT 'sum_of_members', CAST(NULL AS VARCHAR), SUM(distinct_od_pairs) FROM types WHERE trips > 0
) r ORDER BY grain, payment_type_name NULLS FIRST""",
  note="sum_of_members adds the per-type distinct counts Tableau returned, to show they exceed the total.")

Q("Q-N-M1-D2", {
    "q": query(NYC, [dim("Pickup Hour", "pickup_hour"), OD, TRIPS], [PY(2024), in_set("Pickup Quarter", [4])]),
}, "SELECT pickup_hour, distinct_od_pairs FROM q WHERE trips > 0 ORDER BY pickup_hour")

Q("Q-N-M1-D3", {
    "q": query(NYC, [dim("Vendor", "vendor_id"), dim("Pickup Year", "pickup_year"), OD, TRIPS]),
}, """
SELECT vendor_id,
       COALESCE(MAX(CASE WHEN pickup_year = 2023 THEN distinct_od_pairs END), 0) AS distinct_od_pairs_2023,
       COALESCE(MAX(CASE WHEN pickup_year = 2024 THEN distinct_od_pairs END), 0) AS distinct_od_pairs_2024
FROM q WHERE trips > 0 GROUP BY vendor_id ORDER BY vendor_id""",
  note="A vendor with no trips in a year has zero distinct pairs, as COUNT(DISTINCT) over no rows.")

Q("Q-N-M1-D4", {
    "q": query(NYC, [dim("Pickup Zone ID", "pu_location_id"), dim("Pickup Zone", "zone"), OD, TRIPS],
               [PY(2024), MANHATTAN]),
}, """
WITH ranked AS (SELECT q.*, ROW_NUMBER() OVER (ORDER BY distinct_od_pairs DESC, pu_location_id) AS rank_no
                FROM q WHERE trips > 0)
SELECT rank_no, pu_location_id, zone, distinct_od_pairs FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

# =========================================================================== N-M2 fare per mile

FPM = agg("Fare per Mile", "fare_per_mile")

Q("Q-N-M2-P", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), dim("Dropoff Borough", "dropoff_borough"),
                     agg("Fare Amount", "fare_amount"), agg("Total Trip Distance", "trip_distance"), FPM, TRIPS],
               [PY(2024)]),
}, "SELECT pickup_borough, dropoff_borough, fare_amount, trip_distance, fare_per_mile FROM q WHERE trips > 0 "
   "ORDER BY pickup_borough, dropoff_borough")

Q("Q-N-M2-D1", {
    "q": query(NYC, [dim("Pickup Zone ID", "pu_location_id"), dim("Pickup Zone", "zone"), TRIPS, FPM],
               [PY(2024), MANHATTAN, MANHATTAN_DROPOFF]),
}, """
WITH ranked AS (SELECT q.*, ROW_NUMBER() OVER (ORDER BY fare_per_mile DESC, pu_location_id) AS rank_no
                FROM q WHERE trips >= 10000)
SELECT rank_no, pu_location_id, zone, trips, fare_per_mile FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

Q("Q-N-M2-D2", {
    "q": query(NYC, [dim("Pickup Hour", "pickup_hour"), FPM, TRIPS], [PY(2024), MANHATTAN, MANHATTAN_DROPOFF]),
}, "SELECT pickup_hour, fare_per_mile FROM q WHERE trips > 0 ORDER BY pickup_hour")

Q("Q-N-M2-D3", {
    "q": query(NYC, [dim("Pickup Calendar Month", "calendar_month"), dim("Pickup Year", "pickup_year"), FPM, TRIPS],
               [AIRPORTS]),
}, """
SELECT calendar_month,
       MAX(CASE WHEN pickup_year = 2023 THEN fare_per_mile END) AS fare_per_mile_2023,
       MAX(CASE WHEN pickup_year = 2024 THEN fare_per_mile END) AS fare_per_mile_2024
FROM q WHERE trips > 0 GROUP BY calendar_month ORDER BY calendar_month""")

Q("Q-N-M2-D4", {
    "q": query(NYC, [dim("Dropoff Borough", "dropoff_borough"), dim("Payment Type", "payment_type_name"), TRIPS, FPM],
               [PY(2024), in_set("Pickup Zone", ["JFK Airport"])]),
}, """
WITH c AS (SELECT * FROM q WHERE trips > 0),
top_c AS (SELECT dropoff_borough, payment_type_name FROM c
          ORDER BY fare_per_mile DESC, dropoff_borough, payment_type_name LIMIT 1)
SELECT c.dropoff_borough, c.payment_type_name, c.trips, c.fare_per_mile,
       c.dropoff_borough = t.dropoff_borough AND c.payment_type_name = t.payment_type_name AS is_highest
FROM c CROSS JOIN top_c t ORDER BY c.dropoff_borough, c.payment_type_name""")

# =========================================================================== N-C1 YTD and YoY (As-of Date parameter)

YTD = [agg("Revenue YTD", "ytd_revenue"), agg("Revenue YTD Same Time Last Year", "stly_ytd_revenue"),
       agg("Revenue YoY % vs STLY", "yoy_pct")]

Q("Q-N-C1-P", {
    f"m{i + 1:02d}": query(NYC, YTD, parameters={"As-of Date": t}) for i, t in enumerate(month_ends(2024))
}, " UNION ALL ".join(
    f"SELECT DATE '{t}' AS month_end_date, ytd_revenue, stly_ytd_revenue, yoy_pct FROM m{i + 1:02d}"
    for i, t in enumerate(month_ends(2024))) + " ORDER BY month_end_date",
  note="One query per month end: the period-to-date measures are anchored by the As-of Date parameter.")

H1 = date_range("Pickup Date", "2023-01-01", "2024-06-30")

Q("Q-N-C1-D1", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), *YTD, TRIPS], [H1], {"As-of Date": "2024-06-30"}),
}, "SELECT pickup_borough, ytd_revenue, stly_ytd_revenue, yoy_pct FROM q WHERE trips > 0 ORDER BY pickup_borough")

Q("Q-N-C1-D2", {
    "boroughs": query(NYC, [dim("Pickup Borough", "pickup_borough"), *YTD, TRIPS], [H1], {"As-of Date": "2024-06-30"}),
    "zones": query(NYC, [dim("Pickup Borough", "pickup_borough"), dim("Pickup Zone ID", "pu_location_id"),
                         dim("Pickup Zone", "zone"), *YTD[:2], TRIPS], [H1], {"As-of Date": "2024-06-30"}),
}, """
WITH low AS (SELECT pickup_borough, yoy_pct FROM boroughs WHERE trips > 0 AND yoy_pct IS NOT NULL
             ORDER BY yoy_pct, pickup_borough LIMIT 1),
ranked AS (SELECT z.pickup_borough AS borough, low.yoy_pct AS borough_yoy_pct, z.pu_location_id, z.zone,
                  z.ytd_revenue, z.stly_ytd_revenue,
                  COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0) AS revenue_change,
                  ROW_NUMBER() OVER (ORDER BY COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0),
                                     z.pu_location_id) AS rank_no
           FROM zones z JOIN low ON low.pickup_borough = z.pickup_borough WHERE z.trips > 0)
SELECT borough, borough_yoy_pct, rank_no, pu_location_id, zone, ytd_revenue, stly_ytd_revenue, revenue_change
FROM ranked WHERE rank_no <= 10 ORDER BY rank_no""")

Q("Q-N-C1-D3", {
    "q": query(NYC, [dim("Payment Type", "payment_type_name"), *YTD, TRIPS], parameters={"As-of Date": "2024-12-31"}),
}, "SELECT payment_type_name, ytd_revenue, stly_ytd_revenue, yoy_pct FROM q WHERE trips > 0 ORDER BY payment_type_name")

Q("Q-N-C1-D4", {
    "pickup": query(NYC, [NREV], [PY(2024)]),
    "dropoff": query(NYC, [NREV], [in_set("Dropoff Year", [2024])]),
}, """
SELECT p.revenue AS revenue_pickup_2024, d.revenue AS revenue_dropoff_2024, d.revenue - p.revenue AS difference
FROM pickup p CROSS JOIN dropoff d""")

# =========================================================================== N-C2 pace index (As-of Date parameter)

MTD_FILLED = calc("Trips MTD (zero filled)", "ZN([Trips MTD])", "mtd_trips", "integer")
# As-of day counts are dimension calculations of the parameter, not aggregates.
PACE = [dim("As-of Day of Month", "day_of_month"), agg("Trips YTD", "ytd_trips"),
        dim("As-of Day of Year", "day_of_year"), agg("MTD-to-YTD Daily Pace Index", "pace_index")]

Q("Q-N-C2-P", {
    f"m{i + 1:02d}": query(NYC, [agg("Trips MTD", "mtd_trips"), *PACE], parameters={"As-of Date": t})
    for i, t in enumerate(month_ends(2024))
}, " UNION ALL ".join(
    f"SELECT DATE '{t}' AS month_end_date, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index FROM m{i + 1:02d}"
    for i, t in enumerate(month_ends(2024))) + " ORDER BY month_end_date")

YTD_NOV = date_range("Pickup Date", "2024-01-01", "2024-11-30")

Q("Q-N-C2-D1", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), MTD_FILLED, *PACE, TRIPS], [YTD_NOV],
               {"As-of Date": "2024-11-30"}),
}, "SELECT pickup_borough, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index FROM q WHERE trips > 0 "
   "ORDER BY pickup_borough")

Q("Q-N-C2-D2", {
    "q": query(NYC, [dim("Payment Type", "payment_type_name"), MTD_FILLED, *PACE, TRIPS], [YTD_NOV],
               {"As-of Date": "2024-11-30"}),
}, "SELECT payment_type_name, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index FROM q WHERE trips > 0 "
   "ORDER BY payment_type_name")

Q("Q-N-C2-D3", {
    "a2023": query(NYC, [MTD_FILLED, *PACE], parameters={"As-of Date": "2023-03-15"}),
    "a2024": query(NYC, [MTD_FILLED, *PACE], parameters={"As-of Date": "2024-03-15"}),
}, """
SELECT DATE '2023-03-15' AS anchor_date, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index FROM a2023
UNION ALL
SELECT DATE '2024-03-15', mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index FROM a2024
ORDER BY anchor_date""")

Q("Q-N-C2-D4", {
    "zones": query(NYC, [dim("Pickup Zone ID", "pu_location_id"), agg("Trips YTD", "ytd_trips"),
                         agg("MTD-to-YTD Daily Pace Index", "pace_index"), TRIPS], [YTD_NOV],
                   {"As-of Date": "2024-11-30"}),
    "days": query(NYC, [dim("Pickup Calendar Date", "pickup_date")],
                  [date_range("Pickup Calendar Date", "2024-11-01", "2024-11-30")]),
    "daily": query(NYC, [dim("Pickup Zone ID", "pu_location_id"), dim("Pickup Zone", "zone"),
                         dim("Pickup Date", "pickup_date"), TRIPS],
                   [date_range("Pickup Date", "2024-11-01", "2024-11-30")]),
}, """
WITH top_zone AS (SELECT pu_location_id, pace_index FROM zones WHERE trips > 0 AND ytd_trips >= 50000
                  ORDER BY pace_index DESC, pu_location_id LIMIT 1),
names AS (SELECT DISTINCT pu_location_id, zone FROM daily)
SELECT t.pu_location_id, n.zone, t.pace_index, d.pickup_date, c.trips
FROM days d CROSS JOIN top_zone t JOIN names n ON n.pu_location_id = t.pu_location_id
LEFT JOIN daily c ON c.pickup_date = d.pickup_date AND c.pu_location_id = t.pu_location_id AND c.trips > 0
ORDER BY d.pickup_date""",
  note="The day list is the Pickup Calendar domain (dimension-only query), so days without trips keep a blank count.")

# =========================================================================== ad hoc

Q("Q-A01", {
    "q": query(WS, [dim("Bill-To Customer", "bill_to_customer"), agg("Revenue Including Tax", "revenue_including_tax"),
                    LINES], [CY(2015)]),
}, "SELECT bill_to_customer, revenue_including_tax FROM q WHERE lines > 0 "
   "ORDER BY revenue_including_tax DESC, bill_to_customer LIMIT 5")

Q("Q-A02", {
    "q": query(WS, [dim("Salesperson", "salesperson"), dim("Fiscal Year", "fiscal_year"),
                    agg("Invoice Count", "invoice_count"), LINES]),
}, "SELECT salesperson, fiscal_year, invoice_count FROM q WHERE lines > 0 ORDER BY salesperson, fiscal_year")

Q("Q-A03", {
    "q": query(WS, [dim("Stock Group", "stock_group_name"), dim("Delivery Month Start Date", "delivery_month"),
                    agg("Units Sold", "units_sold"), LINES],
               [date_range("Delivery Date", "2016-01-01", "2016-05-31")]),
}, "SELECT stock_group_name, delivery_month, units_sold FROM q WHERE lines > 0 AND stock_group_name IS NOT NULL "
   "ORDER BY stock_group_name, delivery_month")

Q("Q-A04", {
    "q": query(WS, [dim("State Province", "state_province"), dim("Customer Category", "customer_category"),
                    agg("Gross Profit", "gross_profit"), LINES], [CY(2015)]),
}, "SELECT state_province, customer_category, gross_profit FROM q WHERE lines > 0 "
   "ORDER BY gross_profit DESC, state_province, customer_category LIMIT 20")

Q("Q-A05", {
    "q": query(WS, [dim("Stock Group", "stock_group_name"), dim("Calendar Quarter", "calendar_quarter"),
                    agg("Backordered Order Lines", "backordered_lines"), ORDER_LINES], [CY(2015)]),
}, "SELECT stock_group_name, calendar_quarter, backordered_lines FROM q WHERE order_lines > 0 "
   "AND stock_group_name IS NOT NULL ORDER BY stock_group_name, calendar_quarter")

Q("Q-A06", {
    "q": query(NYC, [dim("Pickup Hour", "pickup_hour"), dim("Pickup Day of Week", "day_of_week"),
                     dim("Pickup Day Name", "day_name"), TRIPS], [PY(2024)]),
}, "SELECT pickup_hour, day_of_week, day_name, trips FROM q WHERE trips > 0 ORDER BY pickup_hour, day_of_week")

Q("Q-A07", {
    "q": query(NYC, [dim("Pickup Borough", "pickup_borough"), agg("Total Trip Distance", "total_distance"), TRIPS],
               [PY(2024)]),
}, "SELECT pickup_borough, total_distance, trips, total_distance / trips AS average_trip_distance FROM q "
   "WHERE trips > 0 ORDER BY pickup_borough")

Q("Q-A08", {
    "q": query(NYC, [dim("Dropoff Borough", "dropoff_borough"), agg("Tolls Amount", "tolls_amount"), TRIPS],
               [PY(2024), in_set("Pickup Zone", ["LaGuardia Airport"])]),
}, "SELECT dropoff_borough, tolls_amount FROM q WHERE trips > 0 ORDER BY dropoff_borough")

Q("Q-A09", {
    "q": query(NYC, [dim("Payment Type Code", "payment_type"), dim("Payment Type", "payment_type_name"),
                     agg("Tip Amount (All Payment Types)", "tip_amount"), CARD, TRIPS], [PY(2024)]),
}, "SELECT payment_type, payment_type_name, tip_amount, card_tips FROM q WHERE trips > 0 ORDER BY payment_type")

Q("Q-A10", {
    "q": query(NYC, [dim("Vendor", "vendor_id"), dim("Pickup Month Start Date", "month_start_date"),
                     agg("Fare Amount", "fare_amount"), TRIPS], [PY(2024)]),
}, "SELECT vendor_id, month_start_date, fare_amount, trips, fare_amount / trips AS fare_per_trip FROM q "
   "WHERE trips > 0 ORDER BY vendor_id, month_start_date")


def build() -> dict[str, dict]:
    missing = sorted(set(BANK) - set(SPECS))
    if missing:
        raise ValueError(f"questions without a Tableau answer: {missing}")
    return dict(sorted(SPECS.items()))
