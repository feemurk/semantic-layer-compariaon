-- DSV named query wwi_sales: measure groups Sales and Invoices (invoice line grain).
-- Date keys are yyyymmdd integers; an undelivered line has a NULL delivery key and lands on the
-- Delivery Date unknown member (SPEC § 5.3 rule 5).
SELECT
  f.sale_key,
  YEAR(f.invoice_date) * 10000 + MONTH(f.invoice_date) * 100 + DAY(f.invoice_date) AS invoice_date_id,
  YEAR(f.delivery_date) * 10000 + MONTH(f.delivery_date) * 100 + DAY(f.delivery_date) AS delivery_date_id,
  f.customer_key,
  f.bill_to_customer_key,
  f.city_key,
  f.stock_item_key,
  f.salesperson_key,
  f.wwi_invoice_id,
  f.quantity,
  f.total_excluding_tax,
  f.total_including_tax,
  f.profit
FROM wwi.fact_sale f
