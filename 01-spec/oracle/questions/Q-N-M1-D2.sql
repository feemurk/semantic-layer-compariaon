-- Q-N-M1-D2 Distinct OD pairs by pickup hour, Q4 2024.
SELECT f.pickup_hour, COUNT(DISTINCT f.od_pair_id) AS distinct_od_pairs
FROM nyctaxi.fact_trip f
JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
WHERE d.calendar_year = 2024 AND d.calendar_quarter = 4
GROUP BY f.pickup_hour
ORDER BY f.pickup_hour
