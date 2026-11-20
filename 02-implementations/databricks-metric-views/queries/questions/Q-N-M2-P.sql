-- Q-N-M2-P Fare per mile by pickup borough x dropoff borough, 2024 (composed ratio of sums).
SELECT pickup_borough, dropoff_borough, MEASURE(fare_amount) AS fare_amount, MEASURE(total_trip_distance) AS trip_distance,
       MEASURE(fare_per_mile) AS fare_per_mile
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY pickup_borough, dropoff_borough
ORDER BY pickup_borough, dropoff_borough
