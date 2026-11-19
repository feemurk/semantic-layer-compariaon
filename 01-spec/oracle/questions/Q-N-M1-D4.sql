-- Q-N-M1-D4 Among Manhattan pickup zones, the 10 with the most distinct OD pairs in 2024 (ties: location id).
WITH z AS (
  SELECT f.pu_location_id, pz.zone, COUNT(DISTINCT f.od_pair_id) AS distinct_od_pairs
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  WHERE d.calendar_year = 2024 AND pz.borough = 'Manhattan'
  GROUP BY f.pu_location_id, pz.zone
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY distinct_od_pairs DESC, pu_location_id) AS rank_no FROM z)
SELECT rank_no, pu_location_id, zone, distinct_od_pairs FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
