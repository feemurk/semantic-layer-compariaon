-- Q-A06 Trip count by pickup hour and ISO day of week, 2024.
SELECT f.pickup_hour, d.day_of_week, d.day_name, COUNT(*) AS trips
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.calendar_year = 2024
GROUP BY f.pickup_hour, d.day_of_week, d.day_name
ORDER BY f.pickup_hour, d.day_of_week
