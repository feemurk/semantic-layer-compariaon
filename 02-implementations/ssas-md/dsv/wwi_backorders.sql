-- DSV named query wwi_backorders: measure group Backorders (B-W5): order lines with a backorder id only, so the
-- row count is the backordered line count and a cell without backorders is empty rather than zero.
SELECT
  o.order_key,
  YEAR(o.order_date) * 10000 + MONTH(o.order_date) * 100 + DAY(o.order_date) AS order_date_id,
  o.customer_key,
  o.city_key,
  o.stock_item_key,
  o.salesperson_key,
  o.picker_key
FROM wwi.fact_order o
WHERE o.wwi_backorder_id IS NOT NULL
