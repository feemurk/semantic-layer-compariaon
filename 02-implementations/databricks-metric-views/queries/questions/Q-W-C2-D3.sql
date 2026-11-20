-- Q-W-C2-D3 Days of supply for chiller vs non-chiller items at each calendar quarter end of 2015.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH q AS (
  SELECT snapshot_quarter, is_chiller_stock, MEASURE(closing_units) AS closing_units, MEASURE(units_sold_91d) AS units_sold_91d,
         MEASURE(days_of_supply) AS days_of_supply
  FROM slc.semantic.wwi_stock GROUP BY snapshot_quarter, is_chiller_stock
)
SELECT CAST(QUARTER(snapshot_quarter) AS INT) AS calendar_quarter, LAST_DAY(ADD_MONTHS(snapshot_quarter, 2)) AS quarter_end_date,
       is_chiller_stock, closing_units, units_sold_91d, days_of_supply
FROM q WHERE YEAR(snapshot_quarter) = 2015
ORDER BY calendar_quarter, is_chiller_stock
