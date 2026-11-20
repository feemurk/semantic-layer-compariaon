-- Q-A01 The 5 bill-to customers with the highest revenue including tax in calendar 2015 (Bill-To role).
SELECT bill_to_customer, MEASURE(revenue_including_tax) AS revenue_including_tax
FROM slc.semantic.wwi_sales WHERE calendar_year = 2015
GROUP BY bill_to_customer
ORDER BY revenue_including_tax DESC, bill_to_customer
LIMIT 5
