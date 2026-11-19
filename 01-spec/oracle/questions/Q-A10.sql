-- Q-A10 Fare amount per trip by vendor by month, 2024.
SELECT f.vendor_id, d.month_start_date, SUM(f.fare_amount) AS fare_amount, COUNT(*) AS trips,
       CAST(SUM(f.fare_amount) AS DOUBLE) / COUNT(*) AS fare_per_trip
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.calendar_year = 2024
GROUP BY f.vendor_id, d.month_start_date
ORDER BY f.vendor_id, d.month_start_date
