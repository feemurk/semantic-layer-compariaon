-- Q-N-S2-D3 Card tips per card trip (card tips / trip count for payment type 1) by calendar month, 2023 vs 2024.
SELECT d.calendar_month,
       CAST(SUM(CASE WHEN d.calendar_year = 2023 AND f.payment_type = 1 THEN f.tip_amount END) AS DOUBLE)
         / NULLIF(SUM(CASE WHEN d.calendar_year = 2023 AND f.payment_type = 1 THEN 1 ELSE 0 END), 0) AS card_tips_per_card_trip_2023,
       CAST(SUM(CASE WHEN d.calendar_year = 2024 AND f.payment_type = 1 THEN f.tip_amount END) AS DOUBLE)
         / NULLIF(SUM(CASE WHEN d.calendar_year = 2024 AND f.payment_type = 1 THEN 1 ELSE 0 END), 0) AS card_tips_per_card_trip_2024
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
GROUP BY d.calendar_month
ORDER BY d.calendar_month
