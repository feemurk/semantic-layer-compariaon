-- Q-W-M2-D1 Closing stock at FY2015 end (2015-10-31) by stock group, plus the deduplicated total from wwi_stock.
SELECT grain, stock_group_name, closing_units
FROM (
  SELECT 'group' AS grain, stock_group AS stock_group_name, MEASURE(closing_units) AS closing_units
  FROM slc.semantic.wwi_stock_by_stock_group WHERE snapshot_date = DATE '2015-10-31'
  GROUP BY stock_group
  UNION ALL
  SELECT 'total', CAST(NULL AS STRING), MEASURE(closing_units)
  FROM slc.semantic.wwi_stock WHERE snapshot_date = DATE '2015-10-31'
) r
ORDER BY grain, stock_group_name NULLS FIRST
