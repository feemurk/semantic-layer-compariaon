-- Q-N-C1-D3 YTD revenue and YoY % at 2024-12-31 by payment type.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH d AS (
  SELECT pickup_date, payment_type_name, MEASURE(revenue_ytd) AS ytd_revenue, MEASURE(revenue_stly_ytd) AS stly_ytd_revenue,
         MEASURE(revenue_yoy_pct) AS yoy_pct
  FROM slc.semantic.nyc_trips GROUP BY pickup_date, payment_type_name
)
SELECT payment_type_name, ytd_revenue, stly_ytd_revenue, yoy_pct
FROM d WHERE pickup_date = DATE '2024-12-31'
ORDER BY payment_type_name
