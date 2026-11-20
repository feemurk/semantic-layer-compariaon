-- Q-N-C2-P MTD-to-YTD daily pace index at each 2024 month end.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH m AS (SELECT pickup_month, MEASURE(trips_mtd) AS mtd_trips, MEASURE(days_elapsed_in_month) AS day_of_month,
         MEASURE(trips_ytd) AS ytd_trips, MEASURE(days_elapsed_in_year) AS day_of_year, MEASURE(pace_index) AS pace_index FROM slc.semantic.nyc_trips GROUP BY pickup_month)
SELECT LAST_DAY(pickup_month) AS month_end_date, mtd_trips, day_of_month, ytd_trips, day_of_year, pace_index
FROM m WHERE YEAR(pickup_month) = 2024
ORDER BY month_end_date
