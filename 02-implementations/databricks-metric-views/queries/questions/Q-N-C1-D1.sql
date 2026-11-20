-- Q-N-C1-D1 YoY % of YTD revenue at 2024-06-30 by pickup borough.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (
  SELECT pickup_date, pickup_borough, MEASURE(revenue_ytd) AS ytd_revenue, MEASURE(revenue_stly_ytd) AS stly_ytd_revenue,
         MEASURE(revenue_yoy_pct) AS yoy_pct
  FROM slc.semantic.nyc_trips GROUP BY pickup_date, pickup_borough
)
SELECT pickup_borough, ytd_revenue, stly_ytd_revenue, yoy_pct
FROM d WHERE pickup_date = DATE '2024-06-30'
ORDER BY pickup_borough
