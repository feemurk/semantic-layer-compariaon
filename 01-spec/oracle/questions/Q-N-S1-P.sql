-- Q-N-S1-P Gross trip revenue by pickup borough by month, 2024.
SELECT pz.borough AS pickup_borough, d.month_start_date, SUM(f.total_amount) AS revenue
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
WHERE d.calendar_year = 2024
GROUP BY pz.borough, d.month_start_date
ORDER BY pz.borough, d.month_start_date
