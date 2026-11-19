-- Q-W-M2-D1 Closing stock on hand at the end of FY2015 (2015-10-31) by stock group, plus the deduplicated all-groups total.
WITH snap AS (
  SELECT h.wwi_stock_item_id, h.quantity_on_hand
  FROM wwi.fact_stock_holding_daily h
  WHERE h.snapshot_date = (SELECT MAX(h2.snapshot_date) FROM wwi.fact_stock_holding_daily h2
                           JOIN wwi.dim_date d ON d.date_key = h2.snapshot_date WHERE d.fiscal_year = 2015)
)
SELECT grain, stock_group_name, closing_units
FROM (
  SELECT 'group' AS grain, g.stock_group_name, SUM(s.quantity_on_hand) AS closing_units
  FROM snap s
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = s.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
  GROUP BY g.stock_group_name
  UNION ALL
  SELECT 'total', CAST(NULL AS STRING), SUM(quantity_on_hand) FROM snap
) r
ORDER BY grain, stock_group_name NULLS FIRST
