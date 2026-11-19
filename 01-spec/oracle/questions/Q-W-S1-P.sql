-- Q-W-S1-P Revenue (excl. tax) by Sales Territory by fiscal month for fiscal year 2015.
SELECT ci.sales_territory, d.fiscal_month, MIN(d.month_start_date) AS month_start_date,
       SUM(f.total_excluding_tax) AS revenue
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_city ci ON ci.city_key = f.city_key
WHERE d.fiscal_year = 2015
GROUP BY ci.sales_territory, d.fiscal_month
ORDER BY ci.sales_territory, d.fiscal_month
