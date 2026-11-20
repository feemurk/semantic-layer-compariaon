-- Q-W-S1-D1 Top FY2015 territory, its peak fiscal month, revenue by State Province and City (additive revenue rolled up from the city grain).
WITH fy AS (
  SELECT sales_territory, fiscal_month, state_province, city, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales
  WHERE fiscal_year = 2015
  GROUP BY sales_territory, fiscal_month, state_province, city
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
  SELECT 'city', sales_territory, fiscal_month, state_province, city, revenue FROM scope
) r
ORDER BY grain DESC, state_province, city NULLS FIRST
