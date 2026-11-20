-- Q-N-C1-D4 Revenue for dropoff dates in 2024 vs pickup dates in 2024 (Dropoff Date vs Pickup Date roles) and the difference.
WITH p AS (SELECT MEASURE(gross_trip_revenue) AS revenue FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024),
d AS (SELECT MEASURE(gross_trip_revenue) AS revenue FROM slc.semantic.nyc_trips WHERE dropoff_year = 2024)
SELECT p.revenue AS revenue_pickup_2024, d.revenue AS revenue_dropoff_2024, d.revenue - p.revenue AS difference
FROM p CROSS JOIN d
