-- Q-N-M2-D4 JFK Airport pickups 2024: fare per mile by dropoff borough x payment type; highest combination flagged.
WITH c AS (
  SELECT dropoff_borough, payment_type_name, MEASURE(trip_count) AS trips, MEASURE(fare_per_mile) AS fare_per_mile
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024 AND pickup_zone = 'JFK Airport'
  GROUP BY dropoff_borough, payment_type_name
),
top_c AS (SELECT dropoff_borough, payment_type_name FROM c ORDER BY fare_per_mile DESC, dropoff_borough, payment_type_name LIMIT 1)
SELECT c.dropoff_borough, c.payment_type_name, c.trips, c.fare_per_mile,
       c.dropoff_borough = t.dropoff_borough AND c.payment_type_name = t.payment_type_name AS is_highest
FROM c CROSS JOIN top_c t
ORDER BY c.dropoff_borough, c.payment_type_name
