-- Q-N-C2-D4 Pickup zone with the highest pace index at 2024-11-30 among zones with >= 50,000 YTD trips; daily trips in November 2024.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH z AS (
  SELECT pickup_date, pickup_zone_id, pickup_zone, MEASURE(trips_ytd) AS ytd_trips, MEASURE(pace_index) AS pace_index,
         MEASURE(trip_count) AS trips
  FROM slc.semantic.nyc_trips GROUP BY pickup_date, pickup_zone_id, pickup_zone
),
top_zone AS (
  SELECT pickup_zone_id, pickup_zone, pace_index FROM z
  WHERE pickup_date = DATE '2024-11-30' AND ytd_trips >= 50000
  ORDER BY pace_index DESC, pickup_zone_id LIMIT 1
)
SELECT t.pickup_zone_id AS pu_location_id, t.pickup_zone AS zone, t.pace_index, z.pickup_date, z.trips
FROM z JOIN top_zone t ON t.pickup_zone_id = z.pickup_zone_id
WHERE z.pickup_date BETWEEN DATE '2024-11-01' AND DATE '2024-11-30'
ORDER BY z.pickup_date
