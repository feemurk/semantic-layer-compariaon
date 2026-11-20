-- Q-W-C2-D1 Days of supply at 2015-12-31 by stock group.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (
  SELECT snapshot_date, stock_group, MEASURE(closing_units) AS closing_units, MEASURE(units_sold_91d) AS units_sold_91d,
         MEASURE(days_of_supply) AS days_of_supply
  FROM slc.semantic.wwi_stock_by_stock_group GROUP BY snapshot_date, stock_group
)
SELECT stock_group AS stock_group_name, closing_units, units_sold_91d, days_of_supply
FROM d WHERE snapshot_date = DATE '2015-12-31'
ORDER BY stock_group
