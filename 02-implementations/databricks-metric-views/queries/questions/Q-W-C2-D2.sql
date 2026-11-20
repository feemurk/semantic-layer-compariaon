-- Q-W-C2-D2 The 10 items with the lowest days of supply at 2015-12-31, excluding items without sales in the trailing 91 days.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (
  SELECT snapshot_date, wwi_stock_item_id, stock_item, MEASURE(closing_units) AS closing_units,
         MEASURE(units_sold_91d) AS units_sold_91d, MEASURE(days_of_supply) AS days_of_supply
  FROM slc.semantic.wwi_stock GROUP BY snapshot_date, wwi_stock_item_id, stock_item
),
ranked AS (
  SELECT d.*, ROW_NUMBER() OVER (ORDER BY days_of_supply, wwi_stock_item_id) AS rank_no
  FROM d WHERE snapshot_date = DATE '2015-12-31' AND units_sold_91d > 0
)
SELECT rank_no, wwi_stock_item_id, stock_item, closing_units, units_sold_91d, days_of_supply
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
