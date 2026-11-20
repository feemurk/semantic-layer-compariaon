-- Q-N-S1-D3 Monthly revenue for pickups in the 'Airports' service zone, 2024 vs 2023.
WITH m AS (
  SELECT pickup_month, MEASURE(gross_trip_revenue) AS revenue
  FROM slc.semantic.nyc_trips WHERE pickup_service_zone = 'Airports'
  GROUP BY pickup_month
)
SELECT MONTH(pickup_month) AS calendar_month,
       SUM(CASE WHEN YEAR(pickup_month) = 2023 THEN revenue END) AS revenue_2023,
       SUM(CASE WHEN YEAR(pickup_month) = 2024 THEN revenue END) AS revenue_2024,
       CAST(SUM(CASE WHEN YEAR(pickup_month) = 2024 THEN revenue END) AS DOUBLE)
         / NULLIF(CAST(SUM(CASE WHEN YEAR(pickup_month) = 2023 THEN revenue END) AS DOUBLE), 0) - 1 AS change_pct
FROM m
GROUP BY MONTH(pickup_month)
ORDER BY calendar_month
