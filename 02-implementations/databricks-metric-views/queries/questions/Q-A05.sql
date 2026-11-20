-- Q-A05 Backordered order lines by stock group by calendar quarter, 2015 (NULL where none qualify).
SELECT stock_group AS stock_group_name, calendar_quarter, MEASURE(backordered_order_lines) AS backordered_lines
FROM slc.semantic.wwi_orders_by_stock_group WHERE calendar_year = 2015
GROUP BY stock_group, calendar_quarter
ORDER BY stock_group_name, calendar_quarter
