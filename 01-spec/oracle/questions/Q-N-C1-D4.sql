-- Q-N-C1-D4 Gross trip revenue for dropoff dates in 2024 vs pickup dates in 2024 (Dropoff Date vs Pickup Date roles) and the difference.
SELECT SUM(CASE WHEN p.calendar_year = 2024 THEN f.total_amount END) AS revenue_pickup_2024,
       SUM(CASE WHEN dd.calendar_year = 2024 THEN f.total_amount END) AS revenue_dropoff_2024,
       SUM(CASE WHEN dd.calendar_year = 2024 THEN f.total_amount END)
         - SUM(CASE WHEN p.calendar_year = 2024 THEN f.total_amount END) AS difference
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date p ON p.date_key = f.pickup_date
JOIN nyctaxi.dim_date dd ON dd.date_key = f.dropoff_date
