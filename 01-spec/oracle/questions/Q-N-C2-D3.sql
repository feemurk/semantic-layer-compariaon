-- Q-N-C2-D3 Pace index at 2024-03-15 vs 2023-03-15 (day_of_year 75 vs 74: 2024 is a leap year).
WITH anchors AS (
  SELECT date_key AS t, month_start_date, day_of_month, day_of_year
  FROM nyctaxi.dim_date WHERE date_key IN (DATE '2023-03-15', DATE '2024-03-15')
),
v AS (
  SELECT a.t, a.day_of_month, a.day_of_year,
         SUM(CASE WHEN f.pickup_date BETWEEN a.month_start_date AND a.t THEN 1 ELSE 0 END) AS mtd_trips,
         COUNT(f.trip_id) AS ytd_trips
  FROM anchors a
  LEFT JOIN nyctaxi.fact_trip f ON f.pickup_date BETWEEN make_date(year(a.t), 1, 1) AND a.t
  GROUP BY a.t, a.day_of_month, a.day_of_year
)
SELECT t AS anchor_date, mtd_trips, day_of_month, ytd_trips, day_of_year,
       CAST(mtd_trips AS DOUBLE) / day_of_month / NULLIF(CAST(ytd_trips AS DOUBLE) / day_of_year, 0) AS pace_index
FROM v
ORDER BY t
