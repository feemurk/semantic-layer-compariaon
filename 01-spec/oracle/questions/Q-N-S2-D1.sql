-- Q-N-S2-D1 Card tips by pickup hour for December 2024.
SELECT f.pickup_hour, SUM(CASE WHEN f.payment_type = 1 THEN f.tip_amount END) AS card_tips
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.month_start_date = DATE '2024-12-01'
GROUP BY f.pickup_hour
ORDER BY f.pickup_hour
