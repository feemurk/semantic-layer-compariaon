-- Q-A04 The 20 State Province x Customer Category combinations with the highest gross profit in calendar 2015 (ties: names).
SELECT ci.state_province, c.category AS customer_category, SUM(f.profit) AS gross_profit
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_city ci ON ci.city_key = f.city_key
JOIN wwi.dim_customer c ON c.customer_key = f.customer_key
WHERE d.calendar_year = 2015
GROUP BY ci.state_province, c.category
ORDER BY gross_profit DESC, ci.state_province, customer_category
LIMIT 20
