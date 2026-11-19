-- Q-W-S2-D4 Backordered order lines in calendar 2015 by salesperson and stock group. salesperson_total_lines counts each
-- line once (deduplicated across groups); is_top_salesperson marks the salesperson with the most lines (ties: name).
WITH bo AS (
  SELECT o.order_key, e.employee AS salesperson, si.wwi_stock_item_id
  FROM wwi.fact_order o
  JOIN wwi.dim_date d ON d.date_key = o.order_date
  JOIN wwi.dim_employee e ON e.employee_key = o.salesperson_key
  JOIN wwi.dim_stock_item si ON si.stock_item_key = o.stock_item_key
  WHERE d.calendar_year = 2015 AND o.wwi_backorder_id IS NOT NULL
),
totals AS (SELECT salesperson, COUNT(*) AS salesperson_total_lines FROM bo GROUP BY salesperson),
top_sp AS (SELECT salesperson FROM totals ORDER BY salesperson_total_lines DESC, salesperson LIMIT 1)
SELECT bo.salesperson, g.stock_group_name, COUNT(*) AS backordered_lines, t.salesperson_total_lines,
       bo.salesperson = ts.salesperson AS is_top_salesperson
FROM bo
JOIN wwi.bridge_stock_item_group b ON b.wwi_stock_item_id = bo.wwi_stock_item_id
JOIN wwi.dim_stock_group g ON g.stock_group_id = b.stock_group_id
JOIN totals t ON t.salesperson = bo.salesperson
CROSS JOIN top_sp ts
GROUP BY bo.salesperson, g.stock_group_name, t.salesperson_total_lines, ts.salesperson
ORDER BY bo.salesperson, g.stock_group_name
