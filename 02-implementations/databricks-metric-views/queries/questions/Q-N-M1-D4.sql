-- Q-N-M1-D4 Among Manhattan pickup zones, the 10 with the most distinct OD pairs in 2024.
WITH z AS (
  SELECT pickup_zone_id, pickup_zone, MEASURE(distinct_od_pairs) AS distinct_od_pairs
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024 AND pickup_borough = 'Manhattan'
  GROUP BY pickup_zone_id, pickup_zone
),
ranked AS (SELECT z.*, ROW_NUMBER() OVER (ORDER BY distinct_od_pairs DESC, pickup_zone_id) AS rank_no FROM z)
SELECT rank_no, pickup_zone_id AS pu_location_id, pickup_zone AS zone, distinct_od_pairs
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
