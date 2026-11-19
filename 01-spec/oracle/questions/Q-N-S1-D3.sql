-- Q-N-S1-D3 Monthly gross trip revenue for pickups in the 'Airports' service zone, 2024 vs 2023.
SELECT d.calendar_month,
       SUM(CASE WHEN d.calendar_year = 2023 THEN f.total_amount END) AS revenue_2023,
       SUM(CASE WHEN d.calendar_year = 2024 THEN f.total_amount END) AS revenue_2024,
       CAST(SUM(CASE WHEN d.calendar_year = 2024 THEN f.total_amount END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN d.calendar_year = 2023 THEN f.total_amount END) AS DOUBLE), 0) - 1 AS change_pct
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
WHERE pz.service_zone = 'Airports'
GROUP BY d.calendar_month
ORDER BY d.calendar_month
