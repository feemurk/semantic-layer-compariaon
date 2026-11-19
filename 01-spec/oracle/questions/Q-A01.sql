-- Q-A01 The 5 bill-to customers with the highest revenue including tax in calendar 2015 (Bill-To role; the source has 3 bill-to customers).
SELECT bt.customer AS bill_to_customer, SUM(f.total_including_tax) AS revenue_including_tax
FROM wwi.fact_sale f
JOIN wwi.dim_date d ON d.date_key = f.invoice_date
JOIN wwi.dim_customer bt ON bt.customer_key = f.bill_to_customer_key
WHERE d.calendar_year = 2015
GROUP BY bt.customer
ORDER BY revenue_including_tax DESC, bill_to_customer
LIMIT 5
