-- Q-W-S2-D1 The 2015 month with the largest absolute gap |ordered quantity - units sold| (order_date vs invoice_date months);
-- ordered quantity by stock item in that month (ties broken by item id).
WITH oq AS (
  SELECT d.month_start_date, SUM(o.quantity) AS ordered_quantity
  FROM wwi.fact_order o JOIN wwi.dim_date d ON d.date_key = o.order_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
us AS (
  SELECT d.month_start_date, SUM(f.quantity) AS units_sold
  FROM wwi.fact_sale f JOIN wwi.dim_date d ON d.date_key = f.invoice_date
  WHERE d.calendar_year = 2015 GROUP BY d.month_start_date
),
gap_month AS (
  SELECT oq.month_start_date, oq.ordered_quantity, us.units_sold
  FROM oq JOIN us ON us.month_start_date = oq.month_start_date
  ORDER BY ABS(oq.ordered_quantity - us.units_sold) DESC, oq.month_start_date
  LIMIT 1
)
SELECT g.month_start_date, g.ordered_quantity AS month_ordered_quantity, g.units_sold AS month_units_sold,
       si.wwi_stock_item_id, si.stock_item, SUM(o.quantity) AS ordered_quantity
FROM wwi.fact_order o
JOIN wwi.dim_date d ON d.date_key = o.order_date
JOIN gap_month g ON g.month_start_date = d.month_start_date
JOIN wwi.dim_stock_item si ON si.stock_item_key = o.stock_item_key
GROUP BY g.month_start_date, g.ordered_quantity, g.units_sold, si.wwi_stock_item_id, si.stock_item
ORDER BY ordered_quantity DESC, si.wwi_stock_item_id
