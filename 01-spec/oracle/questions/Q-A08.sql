-- Q-A08 Total tolls by dropoff borough for trips picked up at LaGuardia Airport, 2024.
SELECT dz.borough AS dropoff_borough, SUM(f.tolls_amount) AS tolls_amount
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
WHERE d.calendar_year = 2024 AND pz.zone = 'LaGuardia Airport'
GROUP BY dz.borough
ORDER BY dz.borough
