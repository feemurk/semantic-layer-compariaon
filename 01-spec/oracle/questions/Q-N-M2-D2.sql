-- Q-N-M2-D2 Fare per mile by pickup hour for Manhattan -> Manhattan trips, 2024.
SELECT f.pickup_hour,
       CAST(SUM(f.fare_amount) AS DOUBLE) / NULLIF(CAST(SUM(f.trip_distance) AS DOUBLE), 0) AS fare_per_mile
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
WHERE d.calendar_year = 2024 AND pz.borough = 'Manhattan' AND dz.borough = 'Manhattan'
GROUP BY f.pickup_hour
ORDER BY f.pickup_hour
