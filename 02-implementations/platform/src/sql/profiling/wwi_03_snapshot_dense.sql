-- P-WWI-03 fact_stock_holding_daily has one row per held stock item per day, 2013-01-01..2016-05-31 (SPEC § 5.3 rule 6)
SELECT n_rows, n_items, n_days, first_day, last_day, expected_items
FROM (
  SELECT COUNT(*) AS n_rows,
         COUNT(DISTINCT wwi_stock_item_id) AS n_items,
         COUNT(DISTINCT snapshot_date) AS n_days,
         MIN(snapshot_date) AS first_day,
         MAX(snapshot_date) AS last_day
  FROM wwi.fact_stock_holding_daily
) s
CROSS JOIN (
  SELECT COUNT(DISTINCT si.wwi_stock_item_id) AS expected_items
  FROM wwi.stock_holding_current h
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
) e
WHERE n_rows <> n_items * n_days
   OR n_days <> 1247
   OR first_day <> DATE'2013-01-01'
   OR last_day <> DATE'2016-05-31'
   OR n_items <> expected_items
