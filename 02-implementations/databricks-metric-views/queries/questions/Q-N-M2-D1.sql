-- Q-N-M2-D1 Manhattan -> Manhattan 2024: the 10 pickup zones with the highest fare per mile among zones with >= 10,000 such trips.
WITH z AS (
  SELECT pickup_zone_id, pickup_zone, MEASURE(trip_count) AS trips, MEASURE(fare_per_mile) AS fare_per_mile
  FROM slc.semantic.nyc_trips
  WHERE YEAR(pickup_year) = 2024 AND pickup_borough = 'Manhattan' AND dropoff_borough = 'Manhattan'
  GROUP BY pickup_zone_id, pickup_zone
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY fare_per_mile DESC, pickup_zone_id) AS rank_no FROM z WHERE trips >= 10000)
SELECT rank_no, pickup_zone_id AS pu_location_id, pickup_zone AS zone, trips, fare_per_mile
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
