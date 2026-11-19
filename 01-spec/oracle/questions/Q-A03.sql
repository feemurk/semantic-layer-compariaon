-- Q-A03 Units sold by stock group by delivery month for January-May 2016 (Delivery Date role), delivered lines only.
SELECT g.stock_group_name, dd.month_start_date AS delivery_month, SUM(f.quantity) AS units_sold
FROM wwi.fact_sale f
JOIN wwi.dim_date dd ON dd.date_key = f.delivery_date
JOIN wwi.dim_stock_item si ON si.stock_item_key = f.stock_item_key
JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = si.wwi_stock_item_id
JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
WHERE dd.date_key BETWEEN DATE '2016-01-01' AND DATE '2016-05-31'
GROUP BY g.stock_group_name, dd.month_start_date
ORDER BY g.stock_group_name, delivery_month
