-- Q-N-S1-D2 For the 2024 month with the highest revenue: revenue by pickup hour and payment type.
WITH top_month AS (
  SELECT pickup_month FROM (
    SELECT pickup_month, MEASURE(gross_trip_revenue) AS revenue FROM slc.semantic.nyc_trips
    WHERE YEAR(pickup_month) = 2024 GROUP BY pickup_month
  ) m ORDER BY revenue DESC, pickup_month LIMIT 1
),
h AS (
  SELECT pickup_month, pickup_hour, payment_type_name, MEASURE(gross_trip_revenue) AS revenue
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_month) = 2024
  GROUP BY pickup_month, pickup_hour, payment_type_name
)
SELECT h.pickup_month AS month_start_date, h.pickup_hour, h.payment_type_name, h.revenue
FROM h JOIN top_month t ON t.pickup_month = h.pickup_month
ORDER BY h.pickup_hour, h.payment_type_name
