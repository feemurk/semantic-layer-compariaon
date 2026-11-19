-- W-M2 Closing Stock On Hand: d* = max(snapshot_date) within P; OH(P) = sum(quantity_on_hand) at d*. Additive across items and groups, last value across time.
-- Stock group grains sum the items of each group (bridge); the deduplicated all-groups value is the 'total'/'year' grain.
WITH snap AS (
  SELECT h.snapshot_date, h.quantity_on_hand, h.wwi_stock_item_id,
         d.calendar_year, d.month_start_date, d.fiscal_year,
         si.stock_item, si.color
  FROM wwi.fact_stock_holding_daily h
  JOIN wwi.dim_date d ON d.date_key = h.snapshot_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
),
grp AS (
  SELECT snap.snapshot_date, snap.quantity_on_hand, snap.calendar_year, g.stock_group_name
  FROM snap
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = snap.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
),
end_total AS (SELECT MAX(snapshot_date) AS d_star FROM snap),
end_year AS (SELECT calendar_year, MAX(snapshot_date) AS d_star FROM snap GROUP BY calendar_year),
end_month AS (SELECT month_start_date, MAX(snapshot_date) AS d_star FROM snap GROUP BY month_start_date),
end_fiscal AS (SELECT fiscal_year, MAX(snapshot_date) AS d_star FROM snap GROUP BY fiscal_year)
SELECT grain, measure, member_1, member_2, member_3, value
FROM (
  SELECT 'total' AS grain, 'W-M2' AS measure, CAST(NULL AS STRING) AS member_1, CAST(NULL AS STRING) AS member_2,
         CAST(NULL AS STRING) AS member_3, SUM(s.quantity_on_hand) AS value
  FROM snap s JOIN end_total e ON s.snapshot_date = e.d_star
  UNION ALL
  SELECT 'year', 'W-M2', CAST(e.calendar_year AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s JOIN end_year e ON s.snapshot_date = e.d_star
  GROUP BY e.calendar_year
  UNION ALL
  SELECT 'month', 'W-M2', CAST(e.month_start_date AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s JOIN end_month e ON s.snapshot_date = e.d_star
  GROUP BY e.month_start_date
  UNION ALL
  SELECT 'day', 'W-M2', CAST(s.snapshot_date AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s
  GROUP BY s.snapshot_date
  UNION ALL
  SELECT 'fiscal_year', 'W-M2', CAST(e.fiscal_year AS STRING), CAST(NULL AS STRING), CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s JOIN end_fiscal e ON s.snapshot_date = e.d_star
  GROUP BY e.fiscal_year
  UNION ALL
  SELECT 'year_stock_item', 'W-M2', CAST(e.calendar_year AS STRING), s.stock_item, CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s JOIN end_year e ON s.snapshot_date = e.d_star
  GROUP BY e.calendar_year, s.stock_item
  UNION ALL
  SELECT 'year_color', 'W-M2', CAST(e.calendar_year AS STRING), s.color, CAST(NULL AS STRING), SUM(s.quantity_on_hand)
  FROM snap s JOIN end_year e ON s.snapshot_date = e.d_star
  GROUP BY e.calendar_year, s.color
  UNION ALL
  SELECT 'year_stock_group', 'W-M2', CAST(e.calendar_year AS STRING), g.stock_group_name, CAST(NULL AS STRING), SUM(g.quantity_on_hand)
  FROM grp g JOIN end_year e ON g.snapshot_date = e.d_star
  GROUP BY e.calendar_year, g.stock_group_name
) r
ORDER BY grain, measure, member_1 NULLS FIRST, member_2 NULLS FIRST, member_3 NULLS FIRST
