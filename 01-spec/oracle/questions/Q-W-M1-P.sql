-- Q-W-M1-P Gross margin % (sum(profit) / sum(total_excluding_tax)) by Customer Category by fiscal quarter, FY2015.
SELECT c.category AS customer_category, d.fiscal_quarter,
       SUM(f.total_excluding_tax) AS revenue, SUM(f.profit) AS profit,
       CAST(SUM(f.profit) AS DOUBLE) / NULLIF(CAST(SUM(f.total_excluding_tax) AS DOUBLE), 0) AS gross_margin_pct
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
WHERE d.fiscal_year = 2015
GROUP BY c.category, d.fiscal_quarter
ORDER BY c.category, d.fiscal_quarter
