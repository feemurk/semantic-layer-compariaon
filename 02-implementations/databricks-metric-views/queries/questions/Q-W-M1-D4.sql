-- Q-W-M1-D4 Salesperson with the largest FY2014 -> FY2015 margin decline; per stock group margins, change and FY2015 revenue.
WITH sp AS (
  SELECT salesperson, fiscal_year, MEASURE(gross_margin_pct) AS gm
  FROM slc.semantic.wwi_sales WHERE fiscal_year IN (2014, 2015)
  GROUP BY salesperson, fiscal_year
),
sp_cmp AS (
  SELECT salesperson, MAX(CASE WHEN fiscal_year = 2014 THEN gm END) AS gm_2014, MAX(CASE WHEN fiscal_year = 2015 THEN gm END) AS gm_2015
  FROM sp GROUP BY salesperson
),
worst AS (SELECT salesperson, gm_2014, gm_2015 FROM sp_cmp ORDER BY gm_2015 - gm_2014, salesperson LIMIT 1),
grp AS (
  SELECT salesperson, stock_group, fiscal_year, MEASURE(gross_margin_pct) AS gm, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales_by_stock_group WHERE fiscal_year IN (2014, 2015)
  GROUP BY salesperson, stock_group, fiscal_year
),
by_group AS (
  SELECT g.stock_group, MAX(CASE WHEN g.fiscal_year = 2014 THEN g.gm END) AS gm_2014,
         MAX(CASE WHEN g.fiscal_year = 2015 THEN g.gm END) AS gm_2015,
         SUM(CASE WHEN g.fiscal_year = 2015 THEN g.revenue END) AS revenue_fy2015
  FROM grp g JOIN worst w ON w.salesperson = g.salesperson
  GROUP BY g.stock_group
)
SELECT w.salesperson, w.gm_2014 AS salesperson_gm_fy2014, w.gm_2015 AS salesperson_gm_fy2015,
       b.stock_group AS stock_group_name, b.gm_2014 AS group_gm_fy2014, b.gm_2015 AS group_gm_fy2015,
       (b.gm_2015 - b.gm_2014) * 100 AS group_change_points, b.revenue_fy2015
FROM by_group b CROSS JOIN worst w
ORDER BY group_change_points NULLS FIRST, b.stock_group
