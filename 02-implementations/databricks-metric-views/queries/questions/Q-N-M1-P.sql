-- Q-N-M1-P Distinct OD pairs by month, 2024 (exact COUNT(DISTINCT), evaluated by the view at each month).
SELECT pickup_month AS month_start_date, MEASURE(distinct_od_pairs) AS distinct_od_pairs
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_month) = 2024
GROUP BY pickup_month
ORDER BY month_start_date
