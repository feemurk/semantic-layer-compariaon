-- W-C2 Days of Supply: t = d*(P); DOS = OH(P) / (U91 / 91), U91 = sum(fact_sale.quantity) with invoice_date in [t - 90, t] for the items in context; NULL when U91 is 0 or absent.
-- Conformed dimensions only (Date, Stock Item, Stock Group). Outputs components :closing_units and :units_sold_91d alongside the KPI.
WITH snap AS (
  SELECT h.snapshot_date, h.quantity_on_hand, h.wwi_stock_item_id, d.calendar_year, d.month_start_date, d.fiscal_year,
         si.stock_item
  FROM wwi.fact_stock_holding_daily h
  JOIN wwi.dim_date d ON d.date_key = h.snapshot_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
),
sold AS (
  SELECT si.wwi_stock_item_id, f.invoice_date, SUM(f.quantity) AS qty
  FROM wwi.fact_sale f
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  GROUP BY si.wwi_stock_item_id, f.invoice_date
),
members AS (
  SELECT b.wwi_stock_item_id, g.stock_group_name
  FROM wwi.bridge_stock_item_group b
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
),
anchors AS (
  SELECT 'total' AS grain, CAST(NULL AS STRING) AS member_1, MAX(snapshot_date) AS t FROM snap
  UNION ALL SELECT 'year', CAST(calendar_year AS STRING), MAX(snapshot_date) FROM snap GROUP BY calendar_year
  UNION ALL SELECT 'month', CAST(month_start_date AS STRING), MAX(snapshot_date) FROM snap GROUP BY month_start_date
  UNION ALL SELECT 'fiscal_year', CAST(fiscal_year AS STRING), MAX(snapshot_date) FROM snap GROUP BY fiscal_year
  UNION ALL SELECT DISTINCT 'day', CAST(snapshot_date AS STRING), snapshot_date FROM snap
),
oh_all AS (
  SELECT a.grain, a.member_1, CAST(NULL AS STRING) AS member_2, SUM(s.quantity_on_hand) AS oh
  FROM anchors a JOIN snap s ON s.snapshot_date = a.t
  GROUP BY a.grain, a.member_1
),
u_all AS (
  SELECT a.grain, a.member_1, CAST(NULL AS STRING) AS member_2, SUM(x.qty) AS u
  FROM anchors a JOIN sold x ON x.invoice_date BETWEEN a.t - INTERVAL '90' DAY AND a.t
  GROUP BY a.grain, a.member_1
),
oh_item AS (
  SELECT 'year_stock_item' AS grain, a.member_1, s.stock_item AS member_2, s.wwi_stock_item_id, SUM(s.quantity_on_hand) AS oh
  FROM anchors a JOIN snap s ON s.snapshot_date = a.t
  WHERE a.grain = 'year'
  GROUP BY a.member_1, s.stock_item, s.wwi_stock_item_id
),
u_item AS (
  SELECT a.member_1, x.wwi_stock_item_id, SUM(x.qty) AS u
  FROM anchors a JOIN sold x ON x.invoice_date BETWEEN a.t - INTERVAL '90' DAY AND a.t
  WHERE a.grain = 'year'
  GROUP BY a.member_1, x.wwi_stock_item_id
),
oh_group AS (
  SELECT 'year_stock_group' AS grain, a.member_1, m.stock_group_name AS member_2, SUM(s.quantity_on_hand) AS oh
  FROM anchors a
  JOIN snap s ON s.snapshot_date = a.t
  JOIN members m ON m.wwi_stock_item_id = s.wwi_stock_item_id
  WHERE a.grain = 'year'
  GROUP BY a.member_1, m.stock_group_name
),
u_group AS (
  SELECT a.member_1, m.stock_group_name, SUM(x.qty) AS u
  FROM anchors a
  JOIN sold x ON x.invoice_date BETWEEN a.t - INTERVAL '90' DAY AND a.t
  JOIN members m ON m.wwi_stock_item_id = x.wwi_stock_item_id
  WHERE a.grain = 'year'
  GROUP BY a.member_1, m.stock_group_name
),
kpi AS (
  SELECT o.grain, o.member_1, o.member_2, o.oh, u.u
  FROM oh_all o LEFT JOIN u_all u ON u.grain = o.grain AND u.member_1 IS NOT DISTINCT FROM o.member_1
  UNION ALL
  SELECT o.grain, o.member_1, o.member_2, o.oh, u.u
  FROM oh_item o LEFT JOIN u_item u ON u.member_1 = o.member_1 AND u.wwi_stock_item_id = o.wwi_stock_item_id
  UNION ALL
  SELECT o.grain, o.member_1, o.member_2, o.oh, u.u
  FROM oh_group o LEFT JOIN u_group u ON u.member_1 = o.member_1 AND u.stock_group_name = o.member_2
)
SELECT grain, measure, member_1, member_2, member_3, value
FROM (
  SELECT grain, 'W-C2' AS measure, member_1, member_2, CAST(NULL AS STRING) AS member_3,
         CAST(oh AS DOUBLE) / NULLIF(CAST(u AS DOUBLE) / 91, 0) AS value
  FROM kpi
  UNION ALL
  SELECT grain, 'W-C2:closing_units', member_1, member_2, CAST(NULL AS STRING), CAST(oh AS DOUBLE) FROM kpi
  UNION ALL
  SELECT grain, 'W-C2:units_sold_91d', member_1, member_2, CAST(NULL AS STRING), CAST(u AS DOUBLE) FROM kpi
) r
ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST
