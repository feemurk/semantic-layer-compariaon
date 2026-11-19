-- Q-N-S2-P Card tips (tip_amount where payment_type = 1) by vendor by month, 2024.
SELECT f.vendor_id, d.month_start_date, SUM(CASE WHEN f.payment_type = 1 THEN f.tip_amount END) AS card_tips
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.calendar_year = 2024
GROUP BY f.vendor_id, d.month_start_date
ORDER BY f.vendor_id, d.month_start_date
