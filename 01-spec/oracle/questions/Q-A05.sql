-- Q-A05 Backordered order lines by stock group by calendar quarter for 2015 (NULL where a group has no backordered line).
SELECT g.stock_group_name, d.calendar_quarter,
       NULLIF(COUNT(o.wwi_backorder_id), 0) AS backordered_lines
FROM wwi.fact_order o
JOIN wwi.dim_date d ON d.date_key = o.order_date
JOIN wwi.dim_stock_item si ON si.stock_item_key = o.stock_item_key
JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = si.wwi_stock_item_id
JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
WHERE d.calendar_year = 2015
GROUP BY g.stock_group_name, d.calendar_quarter
ORDER BY g.stock_group_name, d.calendar_quarter
