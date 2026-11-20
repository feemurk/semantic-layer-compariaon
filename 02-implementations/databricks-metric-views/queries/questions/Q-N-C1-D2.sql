-- Q-N-C1-D2 Borough with the lowest YoY % at 2024-06-30; its 10 pickup zones with the largest absolute YTD revenue decline.
-- Window measures are evaluated over the unfiltered view; the anchor is selected in outer SQL, so no query filter can truncate a window.
WITH b AS (
  SELECT pickup_date, pickup_borough, MEASURE(revenue_yoy_pct) AS yoy_pct
  FROM slc.semantic.nyc_trips GROUP BY pickup_date, pickup_borough
),
low AS (
  SELECT pickup_borough, yoy_pct FROM b
  WHERE pickup_date = DATE '2024-06-30' AND yoy_pct IS NOT NULL ORDER BY yoy_pct, pickup_borough LIMIT 1
),
z AS (
  SELECT pickup_date, pickup_borough, pickup_zone_id, pickup_zone, MEASURE(revenue_ytd) AS ytd_revenue,
         MEASURE(revenue_stly_ytd) AS stly_ytd_revenue
  FROM slc.semantic.nyc_trips GROUP BY pickup_date, pickup_borough, pickup_zone_id, pickup_zone
),
ranked AS (
  SELECT z.pickup_borough, low.yoy_pct AS borough_yoy_pct, z.pickup_zone_id, z.pickup_zone, z.ytd_revenue, z.stly_ytd_revenue,
         COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0) AS revenue_change,
         ROW_NUMBER() OVER (ORDER BY COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0), z.pickup_zone_id) AS rank_no
  FROM z JOIN low ON low.pickup_borough = z.pickup_borough
  WHERE z.pickup_date = DATE '2024-06-30'
)
SELECT pickup_borough AS borough, borough_yoy_pct, rank_no, pickup_zone_id AS pu_location_id, pickup_zone AS zone,
       ytd_revenue, stly_ytd_revenue, revenue_change
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
