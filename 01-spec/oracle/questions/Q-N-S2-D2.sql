-- Q-N-S2-D2 Card tips by pickup borough x dropoff borough (two roles of dim_zone), 2024.
SELECT pz.borough AS pickup_borough, dz.borough AS dropoff_borough,
       SUM(CASE WHEN f.payment_type = 1 THEN f.tip_amount END) AS card_tips
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
WHERE d.calendar_year = 2024
GROUP BY pz.borough, dz.borough
ORDER BY pz.borough, dz.borough
