-- Q-W-C1-D3 Stock group shares FY2014 vs FY2015, change in share points, top gainer flagged.
WITH s AS (
  SELECT stock_group, fiscal_year, MEASURE(stock_group_revenue_share) AS share
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year IN (2014, 2015)
  GROUP BY stock_group, fiscal_year
),
cmp AS (
  SELECT stock_group, MAX(CASE WHEN fiscal_year = 2014 THEN share END) AS share_fy2014,
         MAX(CASE WHEN fiscal_year = 2015 THEN share END) AS share_fy2015,
         (MAX(CASE WHEN fiscal_year = 2015 THEN share END) - MAX(CASE WHEN fiscal_year = 2014 THEN share END)) * 100 AS change_points
  FROM s GROUP BY stock_group
),
top_gainer AS (SELECT stock_group FROM cmp ORDER BY change_points DESC, stock_group LIMIT 1)
SELECT c.stock_group AS stock_group_name, c.share_fy2014, c.share_fy2015, c.change_points,
       c.stock_group = t.stock_group AS is_top_gainer
FROM cmp c CROSS JOIN top_gainer t
ORDER BY c.stock_group
