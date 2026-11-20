-- Q-A10 Fare amount per trip by vendor by month, 2024.
SELECT vendor_id, pickup_month AS month_start_date, MEASURE(fare_amount) AS fare_amount, MEASURE(trip_count) AS trips,
       CAST(MEASURE(fare_amount) AS DOUBLE) / MEASURE(trip_count) AS fare_per_trip
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_month) = 2024
GROUP BY vendor_id, pickup_month
ORDER BY vendor_id, month_start_date
