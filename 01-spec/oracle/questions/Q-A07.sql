-- Q-A07 Average trip distance (total distance / trip count) by pickup borough, 2024.
SELECT pz.borough AS pickup_borough, SUM(f.trip_distance) AS total_distance, COUNT(*) AS trips,
       CAST(SUM(f.trip_distance) AS DOUBLE) / COUNT(*) AS average_trip_distance
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
WHERE d.calendar_year = 2024
GROUP BY pz.borough
ORDER BY pz.borough
