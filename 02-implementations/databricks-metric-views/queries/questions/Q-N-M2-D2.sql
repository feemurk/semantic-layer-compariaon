-- Q-N-M2-D2 Fare per mile by pickup hour for Manhattan -> Manhattan trips, 2024.
SELECT pickup_hour, MEASURE(fare_per_mile) AS fare_per_mile
FROM slc.semantic.nyc_trips
WHERE YEAR(pickup_year) = 2024 AND pickup_borough = 'Manhattan' AND dropoff_borough = 'Manhattan'
GROUP BY pickup_hour
ORDER BY pickup_hour
