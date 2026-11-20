-- Q-N-C2-D3 Pace index at 2024-03-15 vs 2023-03-15 (calendar days elapsed 75 vs 74).
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (SELECT pickup_date, MEASURE(trips_mtd) AS mtd_trips, MEASURE(days_elapsed_in_month) AS day_of_month,
         MEASURE(trips_ytd) AS ytd_trips, MEASURE(days_elapsed_in_year) AS day_of_year, MEASURE(pace_index) AS pace_index FROM slc.semantic.nyc_trips GROUP BY pickup_date)
SELECT pickup_date AS anchor_date, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index
FROM d WHERE pickup_date IN (DATE '2023-03-15', DATE '2024-03-15')
ORDER BY anchor_date
