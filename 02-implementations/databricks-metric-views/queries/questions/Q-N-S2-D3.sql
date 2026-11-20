-- Q-N-S2-D3 Card tips per card trip by calendar month, 2023 vs 2024 (trip count filtered to payment type 1).
WITH m AS (
  SELECT pickup_month, MEASURE(card_tips) AS card_tips, MEASURE(trip_count) AS card_trips
  FROM slc.semantic.nyc_trips WHERE payment_type = 1
  GROUP BY pickup_month
)
SELECT MONTH(pickup_month) AS calendar_month,
       CAST(SUM(CASE WHEN YEAR(pickup_month) = 2023 THEN card_tips END) AS DOUBLE)
         / NULLIF(SUM(CASE WHEN YEAR(pickup_month) = 2023 THEN card_trips END), 0) AS card_tips_per_card_trip_2023,
       CAST(SUM(CASE WHEN YEAR(pickup_month) = 2024 THEN card_tips END) AS DOUBLE)
         / NULLIF(SUM(CASE WHEN YEAR(pickup_month) = 2024 THEN card_trips END), 0) AS card_tips_per_card_trip_2024
FROM m
GROUP BY MONTH(pickup_month)
ORDER BY calendar_month
