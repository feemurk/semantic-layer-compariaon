-- Q-N-M2-D3 Fare per mile by calendar month for pickups in the 'Airports' service zone, 2024 vs 2023.
SELECT d.calendar_month,
       CAST(SUM(CASE WHEN d.calendar_year = 2023 THEN f.fare_amount END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN d.calendar_year = 2023 THEN f.trip_distance END) AS DOUBLE), 0) AS fare_per_mile_2023,
       CAST(SUM(CASE WHEN d.calendar_year = 2024 THEN f.fare_amount END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN d.calendar_year = 2024 THEN f.trip_distance END) AS DOUBLE), 0) AS fare_per_mile_2024
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
WHERE pz.service_zone = 'Airports'
GROUP BY d.calendar_month
ORDER BY d.calendar_month
