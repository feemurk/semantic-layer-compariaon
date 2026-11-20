-- Q-N-M1-D2 Distinct OD pairs by pickup hour, Q4 2024.
SELECT pickup_hour, MEASURE(distinct_od_pairs) AS distinct_od_pairs
FROM slc.semantic.nyc_trips WHERE pickup_quarter = DATE '2024-10-01'
GROUP BY pickup_hour
ORDER BY pickup_hour
