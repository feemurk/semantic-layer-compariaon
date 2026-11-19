-- Q-W-S1-D1 Territory with the highest FY2015 revenue; its peak fiscal month (highest revenue for that territory);
-- revenue in that month by State Province (grain 'state') and by City within State Province (grain 'city').
WITH fy AS (
  SELECT f.total_excluding_tax AS revenue, d.fiscal_month, ci.sales_territory, ci.state_province, ci.city
  FROM wwi.fact_sale f
  JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  JOIN wwi.dim_city ci ON ci.city_key = f.city_key
  WHERE d.fiscal_year = 2015
),
top_territory AS (
  SELECT sales_territory FROM fy GROUP BY sales_territory ORDER BY SUM(revenue) DESC, sales_territory LIMIT 1
),
peak_month AS (
  SELECT fy.fiscal_month FROM fy JOIN top_territory t ON t.sales_territory = fy.sales_territory
  GROUP BY fy.fiscal_month ORDER BY SUM(fy.revenue) DESC, fy.fiscal_month LIMIT 1
),
scope AS (
  SELECT fy.* FROM fy
  JOIN top_territory t ON t.sales_territory = fy.sales_territory
  JOIN peak_month m ON m.fiscal_month = fy.fiscal_month
)
SELECT grain, sales_territory, fiscal_month, state_province, city, revenue
FROM (
  SELECT 'state' AS grain, sales_territory, fiscal_month, state_province, CAST(NULL AS STRING) AS city, SUM(revenue) AS revenue
  FROM scope GROUP BY sales_territory, fiscal_month, state_province
  UNION ALL
  SELECT 'city', sales_territory, fiscal_month, state_province, city, SUM(revenue)
  FROM scope GROUP BY sales_territory, fiscal_month, state_province, city
) r
ORDER BY grain DESC, state_province, city NULLS FIRST
