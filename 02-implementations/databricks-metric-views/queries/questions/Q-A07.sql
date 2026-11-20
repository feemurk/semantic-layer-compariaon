-- Q-A07 Average trip distance (total distance / trip count) by pickup borough, 2024: an ad hoc ratio of two view measures.
SELECT pickup_borough, MEASURE(total_trip_distance) AS total_distance, MEASURE(trip_count) AS trips,
       CAST(MEASURE(total_trip_distance) AS DOUBLE) / MEASURE(trip_count) AS average_trip_distance
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY pickup_borough
ORDER BY pickup_borough
