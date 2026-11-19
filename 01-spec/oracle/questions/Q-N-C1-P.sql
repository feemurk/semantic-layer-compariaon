-- Q-N-C1-P YTD gross trip revenue and YoY % vs STLY at each month end of 2024 (t = month end; STLY = Jan 1 2023 .. t - 1 year).
WITH daily AS (
  SELECT pickup_date, SUM(total_amount) AS revenue FROM nyctaxi.fact_trip GROUP BY pickup_date
),
anchors AS (
  SELECT month_start_date, MAX(date_key) AS t FROM nyctaxi.dim_date WHERE calendar_year = 2024 GROUP BY month_start_date
),
v AS (
  SELECT a.month_start_date, a.t,
         SUM(CASE WHEN d.pickup_date BETWEEN make_date(year(a.t), 1, 1) AND a.t THEN d.revenue END) AS ytd_revenue,
         SUM(CASE WHEN d.pickup_date BETWEEN make_date(year(a.t) - 1, 1, 1) AND CAST(a.t - INTERVAL '1' YEAR AS DATE)
                  THEN d.revenue END) AS stly_ytd_revenue
  FROM anchors a LEFT JOIN daily d ON d.pickup_date BETWEEN make_date(year(a.t) - 1, 1, 1) AND a.t
  GROUP BY a.month_start_date, a.t
)
SELECT t AS month_end_date, ytd_revenue, stly_ytd_revenue,
       CAST(ytd_revenue - stly_ytd_revenue AS DOUBLE) / NULLIF(CAST(stly_ytd_revenue AS DOUBLE), 0) AS yoy_pct
FROM v
ORDER BY t
