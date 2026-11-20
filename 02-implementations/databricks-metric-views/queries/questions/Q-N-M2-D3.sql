-- Q-N-M2-D3 Fare per mile by calendar month for pickups in the 'Airports' service zone, 2024 vs 2023.
WITH m AS (
  SELECT pickup_month, MEASURE(fare_per_mile) AS fpm
  FROM slc.semantic.nyc_trips WHERE pickup_service_zone = 'Airports'
  GROUP BY pickup_month
)
SELECT MONTH(pickup_month) AS calendar_month,
       MAX(CASE WHEN YEAR(pickup_month) = 2023 THEN fpm END) AS fare_per_mile_2023,
       MAX(CASE WHEN YEAR(pickup_month) = 2024 THEN fpm END) AS fare_per_mile_2024
FROM m
GROUP BY MONTH(pickup_month)
ORDER BY calendar_month
