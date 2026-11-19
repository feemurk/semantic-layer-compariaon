-- Q-N-S1-D4 The 10 dropoff zones with the most 2024 gross trip revenue from trips picked up at JFK Airport (ties: location id).
WITH z AS (
  SELECT f.do_location_id, dz.borough AS dropoff_borough, dz.zone AS dropoff_zone, SUM(f.total_amount) AS revenue
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  JOIN nyctaxi.dim_zone dz ON dz.location_id = f.do_location_id
  WHERE d.calendar_year = 2024 AND pz.zone = 'JFK Airport'
  GROUP BY f.do_location_id, dz.borough, dz.zone
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY revenue DESC, do_location_id) AS rank_no FROM z)
SELECT rank_no, do_location_id, dropoff_borough, dropoff_zone, revenue FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
