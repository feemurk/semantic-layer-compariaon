-- Q-N-M2-P Fare per mile (sum(fare_amount) / sum(trip_distance)) by pickup borough x dropoff borough, 2024.
SELECT pz.borough AS pickup_borough, dz.borough AS dropoff_borough,
       SUM(f.fare_amount) AS fare_amount, SUM(f.trip_distance) AS trip_distance,
       CAST(SUM(f.fare_amount) AS DOUBLE) / NULLIF(CAST(SUM(f.trip_distance) AS DOUBLE), 0) AS fare_per_mile
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
WHERE d.calendar_year = 2024
GROUP BY pz.borough, dz.borough
ORDER BY pz.borough, dz.borough
