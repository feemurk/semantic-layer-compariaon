-- Q-A03 Units sold by stock group by delivery month, January-May 2016, delivered lines only (Delivery Date role).
SELECT stock_group AS stock_group_name, delivery_month_start_date AS delivery_month, MEASURE(units_sold) AS units_sold
FROM slc.semantic.wwi_sales_by_stock_group
WHERE delivery_date BETWEEN DATE '2016-01-01' AND DATE '2016-05-31'
GROUP BY stock_group, delivery_month_start_date
ORDER BY stock_group_name, delivery_month
