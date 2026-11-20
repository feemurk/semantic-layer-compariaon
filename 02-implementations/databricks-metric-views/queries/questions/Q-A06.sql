-- Q-A06 Trip count by pickup hour and ISO day of week, 2024.
SELECT pickup_hour, pickup_day_of_week AS day_of_week, pickup_day_name AS day_name, MEASURE(trip_count) AS trips
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY pickup_hour, pickup_day_of_week, pickup_day_name
ORDER BY pickup_hour, day_of_week
