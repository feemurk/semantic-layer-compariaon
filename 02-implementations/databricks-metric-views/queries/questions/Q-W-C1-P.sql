-- Q-W-C1-P FY2015 revenue share by stock group, plus the deduplicated total row (revenue_deduplicated).
SELECT grain, stock_group_name, revenue, share
FROM (
  SELECT 'group' AS grain, stock_group AS stock_group_name, MEASURE(revenue) AS revenue,
         MEASURE(stock_group_revenue_share) AS share
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year = 2015
  GROUP BY stock_group
  UNION ALL
  SELECT 'total', CAST(NULL AS STRING), MEASURE(revenue_deduplicated),
         CAST(MEASURE(revenue_deduplicated) AS DOUBLE) / NULLIF(CAST(MEASURE(revenue_all_groups) AS DOUBLE), 0)
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year = 2015
) r
ORDER BY grain, stock_group_name NULLS FIRST
