-- P-WWI-05 back-cast items end the window exactly at the current stock holding (SPEC § 5.3 rule 6)
SELECT s.wwi_stock_item_id, s.quantity_on_hand, h.quantity_on_hand AS current_holding
FROM wwi.fact_stock_holding_daily s
JOIN (
  SELECT si.wwi_stock_item_id, SUM(h.quantity_on_hand) AS quantity_on_hand
  FROM wwi.stock_holding_current h
  JOIN wwi.dim_stock_item si ON si.stock_item_key = h.stock_item_key
  GROUP BY si.wwi_stock_item_id
) h ON h.wwi_stock_item_id = s.wwi_stock_item_id
WHERE s.snapshot_date = DATE'2016-05-31'
  AND s.balance_basis = 'holding_backcast'
  AND s.quantity_on_hand <> h.quantity_on_hand
