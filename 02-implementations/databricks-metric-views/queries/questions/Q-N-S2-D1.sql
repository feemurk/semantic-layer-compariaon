-- Q-N-S2-D1 Card tips by pickup hour, December 2024.
SELECT pickup_hour, MEASURE(card_tips) AS card_tips
FROM slc.semantic.nyc_trips WHERE pickup_month = DATE '2024-12-01'
GROUP BY pickup_hour
ORDER BY pickup_hour
