-- Q-N-C2-D2 Pace index at 2024-11-30 by payment type.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (SELECT pickup_date, payment_type_name, MEASURE(trips_mtd) AS mtd_trips, MEASURE(days_elapsed_in_month) AS day_of_month,
         MEASURE(trips_ytd) AS ytd_trips, MEASURE(days_elapsed_in_year) AS day_of_year, MEASURE(pace_index) AS pace_index FROM slc.semantic.nyc_trips GROUP BY pickup_date, payment_type_name)
SELECT payment_type_name, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index
FROM d WHERE pickup_date = DATE '2024-11-30'
ORDER BY payment_type_name
