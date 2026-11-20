-- Q-N-S1-D4 The 10 dropoff zones with the most 2024 revenue from JFK Airport pickups (Dropoff Zone role).
WITH z AS (
  SELECT dropoff_zone_id, dropoff_borough, dropoff_zone, MEASURE(gross_trip_revenue) AS revenue
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024 AND pickup_zone = 'JFK Airport'
  GROUP BY dropoff_zone_id, dropoff_borough, dropoff_zone
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY revenue DESC, dropoff_zone_id) AS rank_no FROM z)
SELECT rank_no, dropoff_zone_id AS do_location_id, dropoff_borough, dropoff_zone, revenue
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
