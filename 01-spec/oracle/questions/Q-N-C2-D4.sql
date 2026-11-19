-- Q-N-C2-D4 Pickup zone with the highest pace index at 2024-11-30 among zones with >= 50,000 YTD trips (ties: location id);
-- its daily trip counts for November 2024 (every calendar day listed; NULL where no trips).
WITH z AS (
  SELECT f.pu_location_id,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2024-11-01' AND DATE '2024-11-30' THEN 1 ELSE 0 END) AS mtd_trips,
         COUNT(*) AS ytd_trips
  FROM nyctaxi.fact_trip f
  WHERE f.pickup_date BETWEEN DATE '2024-01-01' AND DATE '2024-11-30'
  GROUP BY f.pu_location_id
  HAVING COUNT(*) >= 50000
),
top_zone AS (
  SELECT pu_location_id, CAST(mtd_trips AS DOUBLE) / 30 / (CAST(ytd_trips AS DOUBLE) / 335) AS pace_index
  FROM z ORDER BY CAST(mtd_trips AS DOUBLE) / 30 / (CAST(ytd_trips AS DOUBLE) / 335) DESC, pu_location_id LIMIT 1
),
days AS (SELECT date_key FROM nyctaxi.dim_date WHERE month_start_date = DATE '2024-11-01'),
counts AS (
  SELECT f.pickup_date, COUNT(*) AS trips
  FROM nyctaxi.fact_trip f JOIN top_zone t ON t.pu_location_id = f.pu_location_id
  WHERE f.pickup_date BETWEEN DATE '2024-11-01' AND DATE '2024-11-30'
  GROUP BY f.pickup_date
)
SELECT t.pu_location_id, pz.zone, t.pace_index, d.date_key AS pickup_date, c.trips
FROM days d
CROSS JOIN top_zone t
JOIN nyctaxi.dim_zone pz ON pz.location_id = t.pu_location_id
LEFT JOIN counts c ON c.pickup_date = d.date_key
ORDER BY d.date_key
