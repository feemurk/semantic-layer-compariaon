-- Q-N-S2-P Card tips by vendor by month, 2024 (measure-scoped filter payment_type = 1).
SELECT vendor_id, pickup_month AS month_start_date, MEASURE(card_tips) AS card_tips
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_month) = 2024
GROUP BY vendor_id, pickup_month
ORDER BY vendor_id, month_start_date
