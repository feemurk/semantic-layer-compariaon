-- Q-N-S1-D2 For the 2024 month with the highest revenue: gross trip revenue by pickup hour and payment type.
WITH top_month AS (
  SELECT d.month_start_date
  FROM nyctaxi.fact_trip f JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  WHERE d.calendar_year = 2024
  GROUP BY d.month_start_date ORDER BY SUM(f.total_amount) DESC, d.month_start_date LIMIT 1
)
SELECT t.month_start_date, f.pickup_hour, pt.payment_type_name, SUM(f.total_amount) AS revenue
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
JOIN top_month t ON t.month_start_date = d.month_start_date
JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
GROUP BY t.month_start_date, f.pickup_hour, pt.payment_type_name
ORDER BY f.pickup_hour, pt.payment_type_name
