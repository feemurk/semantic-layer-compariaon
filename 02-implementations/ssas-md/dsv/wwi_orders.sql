-- DSV named query wwi_orders: measure group Orders (order line grain, dated by order_date).
SELECT
  o.order_key,
  YEAR(o.order_date) * 10000 + MONTH(o.order_date) * 100 + DAY(o.order_date) AS order_date_id,
  o.customer_key,
  o.city_key,
  o.stock_item_key,
  o.salesperson_key,
  o.picker_key,
  o.quantity
FROM wwi.fact_order o
