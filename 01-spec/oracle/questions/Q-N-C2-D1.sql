-- Q-N-C2-D1 MTD-to-YTD daily pace index at 2024-11-30 by pickup borough (day_of_month = 30, day_of_year = 335).
WITH m AS (
  SELECT pz.borough AS pickup_borough,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2024-11-01' AND DATE '2024-11-30' THEN 1 ELSE 0 END) AS mtd_trips,
         COUNT(*) AS ytd_trips
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  WHERE f.pickup_date BETWEEN DATE '2024-01-01' AND DATE '2024-11-30'
  GROUP BY pz.borough
)
SELECT m.pickup_borough, m.mtd_trips, d.day_of_month, m.ytd_trips, d.day_of_year,
       CAST(m.mtd_trips AS DOUBLE) / d.day_of_month / NULLIF(CAST(m.ytd_trips AS DOUBLE) / d.day_of_year, 0) AS pace_index
FROM m CROSS JOIN nyctaxi.dim_date d
WHERE d.date_key = DATE '2024-11-30'
ORDER BY m.pickup_borough
