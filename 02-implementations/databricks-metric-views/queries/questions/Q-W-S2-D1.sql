-- Q-W-S2-D1 2015 month with the largest |ordered quantity - units sold|; ordered quantity by stock item in that month.
WITH oq AS (
  SELECT month_start_date, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year = 2015 GROUP BY month_start_date
),
us AS (
  SELECT month_start_date, MEASURE(units_sold) AS units_sold
  FROM slc.semantic.wwi_sales WHERE calendar_year = 2015 GROUP BY month_start_date
),
gap_month AS (
  SELECT oq.month_start_date, oq.ordered_quantity, us.units_sold
  FROM oq JOIN us ON us.month_start_date = oq.month_start_date
  ORDER BY ABS(oq.ordered_quantity - us.units_sold) DESC, oq.month_start_date
  LIMIT 1
),
by_item AS (
  SELECT month_start_date, wwi_stock_item_id, stock_item, MEASURE(ordered_quantity) AS ordered_quantity
  FROM slc.semantic.wwi_orders WHERE calendar_year = 2015
  GROUP BY month_start_date, wwi_stock_item_id, stock_item
)
SELECT g.month_start_date, g.ordered_quantity AS month_ordered_quantity, g.units_sold AS month_units_sold,
       b.wwi_stock_item_id, b.stock_item, b.ordered_quantity
FROM by_item b JOIN gap_month g ON g.month_start_date = b.month_start_date
ORDER BY b.ordered_quantity DESC, b.wwi_stock_item_id
