-- Q-W-M1-D4 Salesperson whose gross margin % fell the most from FY2014 to FY2015 (ties: name); for that salesperson,
-- per stock group: gross margin % in each year, change in points, and FY2015 revenue; ordered by change ascending (largest drop first).
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, f.profit, d.fiscal_year, e.employee AS salesperson, si.wwi_stock_item_id
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_employee e ON e.employee_key = f.salesperson_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
  WHERE d.fiscal_year IN (2014, 2015)
),
sp AS (
  SELECT salesperson,
         CAST(SUM(CASE WHEN fiscal_year = 2014 THEN profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN fiscal_year = 2014 THEN revenue END) AS DOUBLE), 0) AS gm_2014,
         CAST(SUM(CASE WHEN fiscal_year = 2015 THEN profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN fiscal_year = 2015 THEN revenue END) AS DOUBLE), 0) AS gm_2015
  FROM fy GROUP BY salesperson
),
worst AS (SELECT salesperson, gm_2014, gm_2015 FROM sp ORDER BY gm_2015 - gm_2014, salesperson LIMIT 1),
by_group AS (
  SELECT g.stock_group_name,
         CAST(SUM(CASE WHEN fy.fiscal_year = 2014 THEN fy.profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN fy.fiscal_year = 2014 THEN fy.revenue END) AS DOUBLE), 0) AS gm_2014,
         CAST(SUM(CASE WHEN fy.fiscal_year = 2015 THEN fy.profit END) AS DOUBLE)
           / NULLIF(CAST(SUM(CASE WHEN fy.fiscal_year = 2015 THEN fy.revenue END) AS DOUBLE), 0) AS gm_2015,
         SUM(CASE WHEN fy.fiscal_year = 2015 THEN fy.revenue END) AS revenue_fy2015
  FROM fy
  JOIN worst w ON w.salesperson = fy.salesperson
  JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = fy.wwi_stock_item_id
  JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
  GROUP BY g.stock_group_name
)
SELECT w.salesperson, w.gm_2014 AS salesperson_gm_fy2014, w.gm_2015 AS salesperson_gm_fy2015,
       bg.stock_group_name, bg.gm_2014 AS group_gm_fy2014, bg.gm_2015 AS group_gm_fy2015,
       (bg.gm_2015 - bg.gm_2014) * 100 AS group_change_points, bg.revenue_fy2015
FROM by_group bg CROSS JOIN worst w
ORDER BY group_change_points NULLS FIRST, bg.stock_group_name
