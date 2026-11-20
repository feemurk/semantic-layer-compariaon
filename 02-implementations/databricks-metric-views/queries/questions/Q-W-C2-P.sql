-- Q-W-C2-P Days of supply at each calendar month end of 2015 (closing_units semi-additive; units_sold_91d trailing 91 days inclusive).
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH m AS (
  SELECT snapshot_month, MEASURE(closing_units) AS closing_units, MEASURE(units_sold_91d) AS units_sold_91d,
         MEASURE(days_of_supply) AS days_of_supply
  FROM slc.semantic.wwi_stock GROUP BY snapshot_month
)
SELECT LAST_DAY(snapshot_month) AS month_end_date, closing_units, units_sold_91d, days_of_supply
FROM m WHERE YEAR(snapshot_month) = 2015
ORDER BY month_end_date
