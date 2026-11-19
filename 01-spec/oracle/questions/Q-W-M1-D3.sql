-- Q-W-M1-D3 Gross margin % by selling package (as-was stock item attribute), FY2014 vs FY2015; change in percentage points.
-- A package with sales in only one of the two years keeps its row, with NULL for the other year.
WITH g AS (
  SELECT si.selling_package,
         CAST(SUM(CASE WHEN d.fiscal_year = 2014 THEN f.profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN d.fiscal_year = 2014 THEN f.total_excluding_tax END) AS DOUBLE), 0) AS gm_2014,
         CAST(SUM(CASE WHEN d.fiscal_year = 2015 THEN f.profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN d.fiscal_year = 2015 THEN f.total_excluding_tax END) AS DOUBLE), 0) AS gm_2015
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year IN (2014, 2015)
  GROUP BY si.selling_package
)
SELECT selling_package, gm_2014 AS gross_margin_pct_fy2014, gm_2015 AS gross_margin_pct_fy2015,
       (gm_2015 - gm_2014) * 100 AS change_points
FROM g
ORDER BY selling_package
