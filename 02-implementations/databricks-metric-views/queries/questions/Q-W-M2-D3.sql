-- Q-W-M2-D3 Closing stock at 2015-12-31 vs 2014-12-31 by selling package and chiller flag (as-was item attributes).
WITH c AS (
  SELECT selling_package, is_chiller_stock, snapshot_date, MEASURE(closing_units) AS units
  FROM slc.semantic.wwi_stock WHERE snapshot_date IN (DATE '2014-12-31', DATE '2015-12-31')
  GROUP BY selling_package, is_chiller_stock, snapshot_date
)
SELECT selling_package, is_chiller_stock,
       SUM(CASE WHEN snapshot_date = DATE '2014-12-31' THEN units END) AS closing_units_2014,
       SUM(CASE WHEN snapshot_date = DATE '2015-12-31' THEN units END) AS closing_units_2015,
       SUM(CASE WHEN snapshot_date = DATE '2015-12-31' THEN units END)
         - SUM(CASE WHEN snapshot_date = DATE '2014-12-31' THEN units END) AS change_units
FROM c
GROUP BY selling_package, is_chiller_stock
ORDER BY selling_package, is_chiller_stock
