-- Q-W-C1-P FY2015 revenue share by stock group (REV(g) / FY2015 revenue) plus the deduplicated total row equal to FY2015 revenue.
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year = 2015
),
total AS (SELECT SUM(revenue) AS rev FROM fy)
SELECT grain, stock_group_name, revenue, share
FROM (
  SELECT 'group' AS grain, g.stock_group_name, SUM(fy.revenue) AS revenue,
         CAST(SUM(fy.revenue) AS DOUBLE) / CAST(MAX(t.rev) AS DOUBLE) AS share
  FROM fy
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = fy.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
  CROSS JOIN total t
  GROUP BY g.stock_group_name
  UNION ALL
  SELECT 'total', CAST(NULL AS STRING), t.rev, CAST(t.rev AS DOUBLE) / CAST(t.rev AS DOUBLE) FROM total t
) r
ORDER BY grain, stock_group_name NULLS FIRST
