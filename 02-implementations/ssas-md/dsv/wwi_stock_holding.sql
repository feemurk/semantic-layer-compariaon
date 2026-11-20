-- DSV named query wwi_stock_holding: measure group Stock Holdings (dense daily snapshot, SPEC § 5.3 rule 6).
SELECT
  YEAR(h.snapshot_date) * 10000 + MONTH(h.snapshot_date) * 100 + DAY(h.snapshot_date) AS snapshot_date_id,
  h.stock_item_key,
  h.wwi_stock_item_id,
  h.quantity_on_hand,
  1 AS access_key
FROM wwi.fact_stock_holding_daily h
