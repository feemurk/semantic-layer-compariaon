-- Q-W-S1-D3 FY2015 vs FY2014 revenue by Buying Group and Customer Category (as-was customer attributes).
WITH r AS (
  SELECT buying_group, customer_category, fiscal_year, MEASURE(revenue) AS revenue
  FROM slc.semantic.wwi_sales
  WHERE fiscal_year IN (2014, 2015)
  GROUP BY buying_group, customer_category, fiscal_year
)
SELECT buying_group, customer_category,
       SUM(CASE WHEN fiscal_year = 2014 THEN revenue END) AS revenue_fy2014,
       SUM(CASE WHEN fiscal_year = 2015 THEN revenue END) AS revenue_fy2015,
       CAST(SUM(CASE WHEN fiscal_year = 2015 THEN revenue END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN fiscal_year = 2014 THEN revenue END) AS DOUBLE), 0) - 1 AS change_pct
FROM r
GROUP BY buying_group, customer_category
ORDER BY buying_group, customer_category
