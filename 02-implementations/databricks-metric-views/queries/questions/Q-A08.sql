-- Q-A08 Total tolls by dropoff borough for trips picked up at LaGuardia Airport, 2024.
SELECT dropoff_borough, MEASURE(tolls_amount) AS tolls_amount
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024 AND pickup_zone = 'LaGuardia Airport'
GROUP BY dropoff_borough
ORDER BY dropoff_borough
