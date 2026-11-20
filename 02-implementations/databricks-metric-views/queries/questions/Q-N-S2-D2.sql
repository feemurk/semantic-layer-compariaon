-- Q-N-S2-D2 Card tips by pickup borough x dropoff borough, 2024 (two roles of the zone dimension).
SELECT pickup_borough, dropoff_borough, MEASURE(card_tips) AS card_tips
FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024
GROUP BY pickup_borough, dropoff_borough
ORDER BY pickup_borough, dropoff_borough
