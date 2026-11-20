-- Q-A02 Invoice count (exact distinct) by salesperson by fiscal year.
SELECT salesperson, fiscal_year, MEASURE(invoice_count) AS invoice_count
FROM slc.semantic.wwi_sales
GROUP BY salesperson, fiscal_year
ORDER BY salesperson, fiscal_year
