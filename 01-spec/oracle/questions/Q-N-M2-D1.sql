-- Q-N-M2-D1 Manhattan -> Manhattan trips in 2024: the 10 pickup zones with the highest fare per mile among zones with
-- at least 10,000 such trips (ties: location id).
WITH z AS (
  SELECT f.pu_location_id, pz.zone, COUNT(*) AS trips,
         CAST(SUM(f.fare_amount) AS DOUBLE) / NULLIF(CAST(SUM(f.trip_distance) AS DOUBLE), 0) AS fare_per_mile
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
  WHERE d.calendar_year = 2024 AND pz.borough = 'Manhattan' AND dz.borough = 'Manhattan'
  GROUP BY f.pu_location_id, pz.zone
  HAVING COUNT(*) >= 10000
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY fare_per_mile DESC, pu_location_id) AS rank_no FROM z)
SELECT rank_no, pu_location_id, zone, trips, fare_per_mile FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
