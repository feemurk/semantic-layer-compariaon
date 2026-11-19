-- Q-A02 Invoice count (exact distinct wwi_invoice_id) by salesperson by fiscal year.
SELECT e.employee AS salesperson, d.fiscal_year, COUNT(DISTINCT f.wwi_invoice_id) AS invoice_count
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_employee e ON e.employee_key = f.salesperson_key
GROUP BY e.employee, d.fiscal_year
ORDER BY e.employee, d.fiscal_year
