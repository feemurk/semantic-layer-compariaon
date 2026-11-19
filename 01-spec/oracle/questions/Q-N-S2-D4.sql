-- Q-N-S2-D4 Card tips by payment type for 2024: a value for payment type 1 only; NULL for every other type, including
-- types with no 2024 trips (all codes of dim_payment_type are listed).
SELECT pt.payment_type, pt.payment_type_name, x.card_tips
FROM nyctaxi.dim_payment_type pt
LEFT JOIN (
  SELECT f.payment_type, SUM(CASE WHEN f.payment_type = 1 THEN f.tip_amount END) AS card_tips
  FROM nyctaxi.fact_trip f JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  WHERE d.calendar_year = 2024
  GROUP BY f.payment_type
) x ON x.payment_type = pt.payment_type
ORDER BY pt.payment_type
