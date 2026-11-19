-- Q-A09 Tip amount (all payment types) vs card tips by payment type, 2024.
SELECT pt.payment_type, pt.payment_type_name, SUM(f.tip_amount) AS tip_amount,
       SUM(CASE WHEN f.payment_type = 1 THEN f.tip_amount END) AS card_tips
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
WHERE d.calendar_year = 2024
GROUP BY pt.payment_type, pt.payment_type_name
ORDER BY pt.payment_type
