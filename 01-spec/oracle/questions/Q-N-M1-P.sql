-- Q-N-M1-P Distinct origin-destination pairs (exact count of distinct od_pair_id) by month, 2024.
SELECT d.month_start_date, COUNT(DISTINCT f.od_pair_id) AS distinct_od_pairs
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.calendar_year = 2024
GROUP BY d.month_start_date
ORDER BY d.month_start_date
