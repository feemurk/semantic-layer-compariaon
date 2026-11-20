-- DSV named query wwi_stock_item_group: intermediate measure group of the Stock Group many-to-many relationship
-- (W-C1). It relates to Stock Item at the durable WWI Stock Item ID granularity.
SELECT
  b.wwi_stock_item_id,
  b.stock_group_id
FROM wwi.bridge_stock_item_group b
