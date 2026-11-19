-- P-WWI-04 no derived daily stock balance is negative (SPEC § 5.3 rule 6)
SELECT wwi_stock_item_id, snapshot_date, quantity_on_hand, balance_basis
FROM wwi.fact_stock_holding_daily
WHERE quantity_on_hand < 0
