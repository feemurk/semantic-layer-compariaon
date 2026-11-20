-- Q-N-C1-P YTD revenue and YoY % vs STLY at each 2024 month end (anchor = last pickup date of each month).
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH m AS (
  SELECT pickup_month, MEASURE(revenue_ytd) AS ytd_revenue, MEASURE(revenue_stly_ytd) AS stly_ytd_revenue,
         MEASURE(revenue_yoy_pct) AS yoy_pct
  FROM slc.semantic.nyc_trips GROUP BY pickup_month
)
SELECT LAST_DAY(pickup_month) AS month_end_date, ytd_revenue, stly_ytd_revenue, yoy_pct
FROM m WHERE YEAR(pickup_month) = 2024
ORDER BY month_end_date
