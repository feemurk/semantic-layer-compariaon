-- Q-N-C2-P MTD-to-YTD daily pace index at each month end of 2024: (trips MTD / day_of_month) / (trips YTD / day_of_year).
WITH daily AS (SELECT pickup_date, COUNT(*) AS trips FROM nyctaxi.fact_trip GROUP BY pickup_date),
anchors AS (
  SELECT d.month_start_date, d.date_key AS t, d.day_of_month, d.day_of_year
  FROM nyctaxi.dim_date d
  JOIN (SELECT month_start_date, MAX(date_key) AS t FROM nyctaxi.dim_date WHERE calendar_year = 2024 GROUP BY month_start_date) m
    ON m.t = d.date_key
),
v AS (
  SELECT a.t, a.day_of_month, a.day_of_year,
         SUM(CASE WHEN x.pickup_date BETWEEN a.month_start_date AND a.t THEN x.trips END) AS mtd_trips,
         SUM(x.trips) AS ytd_trips
  FROM anchors a LEFT JOIN daily x ON x.pickup_date BETWEEN make_date(year(a.t), 1, 1) AND a.t
  GROUP BY a.t, a.day_of_month, a.day_of_year
)
SELECT t AS month_end_date, mtd_trips, day_of_month, ytd_trips, day_of_year,
       CAST(COALESCE(mtd_trips, 0) AS DOUBLE) / day_of_month / NULLIF(CAST(ytd_trips AS DOUBLE) / day_of_year, 0) AS pace_index
FROM v
ORDER BY t
