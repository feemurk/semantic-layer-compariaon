-- Q-A04 The 20 State Province x Customer Category combinations with the highest gross profit in calendar 2015.
SELECT state_province, customer_category, MEASURE(gross_profit) AS gross_profit
FROM slc.semantic.wwi_sales WHERE calendar_year = 2015
GROUP BY state_province, customer_category
ORDER BY gross_profit DESC, state_province, customer_category
LIMIT 20
