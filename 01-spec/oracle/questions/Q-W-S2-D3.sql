-- Q-W-S2-D3 Ordered quantity by selling package (as-was stock item attribute) by calendar quarter, 2014 vs 2015.
SELECT si.selling_package, d.calendar_quarter,
       SUM(CASE WHEN d.calendar_year = 2014 THEN o.quantity END) AS ordered_quantity_2014,
       SUM(CASE WHEN d.calendar_year = 2015 THEN o.quantity END) AS ordered_quantity_2015,
       CAST(SUM(CASE WHEN d.calendar_year = 2015 THEN o.quantity END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN d.calendar_year = 2014 THEN o.quantity END) AS DOUBLE), 0) - 1 AS change_pct
FROM wwi.fact_order o
JOIN wwi.dim_date d ON d.date_key = o.order_date
JOIN wwi.dim_stock_item si ON si.stock_item_key = o.stock_item_key
WHERE d.calendar_year IN (2014, 2015)
GROUP BY si.selling_package, d.calendar_quarter
ORDER BY si.selling_package, d.calendar_quarter
