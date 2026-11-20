-- Q-N-S1-P Gross trip revenue by pickup borough by month, 2024.
SELECT pickup_borough, pickup_month AS month_start_date, MEASURE(gross_trip_revenue) AS revenue
FROM slc.semantic.nyc_trips
WHERE YEAR(pickup_month) = 2024
GROUP BY pickup_borough, pickup_month
ORDER BY pickup_borough, month_start_date
