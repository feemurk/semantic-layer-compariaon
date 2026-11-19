-- Q-N-M2-D4 Trips picked up at JFK Airport in 2024: fare per mile by dropoff borough x payment type; is_highest marks the
-- highest combination (ties: borough, payment type).
WITH c AS (
  SELECT dz.borough AS dropoff_borough, pt.payment_type_name, COUNT(*) AS trips,
         CAST(SUM(f.fare_amount) AS DOUBLE) / NULLIF(CAST(SUM(f.trip_distance) AS DOUBLE), 0) AS fare_per_mile
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
  JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
  WHERE d.calendar_year = 2024 AND pz.zone = 'JFK Airport'
  GROUP BY dz.borough, pt.payment_type_name
),
top_c AS (SELECT dropoff_borough, payment_type_name FROM c ORDER BY fare_per_mile DESC, dropoff_borough, payment_type_name LIMIT 1)
SELECT c.dropoff_borough, c.payment_type_name, c.trips, c.fare_per_mile,
       c.dropoff_borough = t.dropoff_borough AND c.payment_type_name = t.payment_type_name AS is_highest
FROM c CROSS JOIN top_c t
ORDER BY c.dropoff_borough, c.payment_type_name
