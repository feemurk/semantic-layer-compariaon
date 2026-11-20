-- Q-A09 Tip amount (all payment types) vs card tips by payment type, 2024.
SELECT payment_type, payment_type_name, MEASURE(tip_amount) AS tip_amount, MEASURE(card_tips) AS card_tips
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY payment_type, payment_type_name
ORDER BY payment_type
