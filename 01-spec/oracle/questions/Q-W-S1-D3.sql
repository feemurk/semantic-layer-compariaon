-- Q-W-S1-D3 FY2015 vs FY2014 revenue by Buying Group and Customer Category (as-was customer attributes).
SELECT c.buying_group, c.category AS customer_category,
       SUM(CASE WHEN d.fiscal_year = 2014 THEN f.total_excluding_tax END) AS revenue_fy2014,
       SUM(CASE WHEN d.fiscal_year = 2015 THEN f.total_excluding_tax END) AS revenue_fy2015,
       CAST(SUM(CASE WHEN d.fiscal_year = 2015 THEN f.total_excluding_tax END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN d.fiscal_year = 2014 THEN f.total_excluding_tax END) AS DOUBLE), 0) - 1 AS change_pct
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
WHERE d.fiscal_year IN (2014, 2015)
GROUP BY c.buying_group, c.category
ORDER BY c.buying_group, c.category
