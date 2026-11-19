-- Q-W-M2-D3 Closing stock on hand at 2015-12-31 vs 2014-12-31 by selling package and chiller flag (as-was item attributes).
SELECT si.selling_package, si.is_chiller_stock,
       SUM(CASE WHEN h.snapshot_date = DATE '2014-12-31' THEN h.quantity_on_hand END) AS closing_units_2014,
       SUM(CASE WHEN h.snapshot_date = DATE '2015-12-31' THEN h.quantity_on_hand END) AS closing_units_2015,
       SUM(CASE WHEN h.snapshot_date = DATE '2015-12-31' THEN h.quantity_on_hand END)
         - SUM(CASE WHEN h.snapshot_date = DATE '2014-12-31' THEN h.quantity_on_hand END) AS change_units
FROM wwi.fact_stock_holding_daily h
JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
WHERE h.snapshot_date IN (DATE '2014-12-31', DATE '2015-12-31')
GROUP BY si.selling_package, si.is_chiller_stock
ORDER BY si.selling_package, si.is_chiller_stock
