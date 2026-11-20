-- Q-W-S2-D4 Backordered lines 2015 by salesperson and stock group; salesperson total deduplicated across groups
-- (backordered_lines_all_groups: coarser level of detail over stock_group); top salesperson flagged.
WITH g AS (
  SELECT salesperson, stock_group, MEASURE(backordered_order_lines) AS backordered_lines,
         MEASURE(backordered_lines_all_groups) AS salesperson_total_lines
  FROM slc.semantic.wwi_orders_by_stock_group WHERE calendar_year = 2015
  GROUP BY salesperson, stock_group
),
top_sp AS (
  SELECT salesperson FROM g GROUP BY salesperson ORDER BY MAX(salesperson_total_lines) DESC, salesperson LIMIT 1
)
SELECT g.salesperson, g.stock_group AS stock_group_name, g.backordered_lines, g.salesperson_total_lines,
       g.salesperson = t.salesperson AS is_top_salesperson
FROM g CROSS JOIN top_sp t
WHERE g.backordered_lines IS NOT NULL
ORDER BY g.salesperson, g.stock_group
