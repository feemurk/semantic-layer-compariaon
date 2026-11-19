-- Q-N-C1-D2 Pickup borough with the lowest YoY % at 2024-06-30 (NULL YoY excluded; ties: name); its 10 pickup zones with the
-- largest absolute YTD revenue decline (YTD - STLY, most negative first; ties: location id).
WITH z AS (
  SELECT pz.borough, f.pu_location_id, pz.zone,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2024-01-01' AND DATE '2024-06-30' THEN f.total_amount END) AS ytd_revenue,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2023-01-01' AND DATE '2023-06-30' THEN f.total_amount END) AS stly_ytd_revenue
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  WHERE f.pickup_date BETWEEN DATE '2023-01-01' AND DATE '2024-06-30'
  GROUP BY pz.borough, f.pu_location_id, pz.zone
),
b AS (
  SELECT borough, CAST(SUM(ytd_revenue) - SUM(stly_ytd_revenue) AS DOUBLE) / NULLIF(CAST(SUM(stly_ytd_revenue) AS DOUBLE), 0) AS yoy_pct
  FROM z GROUP BY borough
),
low AS (SELECT borough, yoy_pct FROM b WHERE yoy_pct IS NOT NULL ORDER BY yoy_pct, borough LIMIT 1),
ranked AS (
  SELECT z.borough, low.yoy_pct AS borough_yoy_pct, z.pu_location_id, z.zone, z.ytd_revenue, z.stly_ytd_revenue,
         COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0) AS revenue_change,
         ROW_NUMBER() OVER (ORDER BY COALESCE(z.ytd_revenue, 0) - COALESCE(z.stly_ytd_revenue, 0), z.pu_location_id) AS rank_no
  FROM z JOIN low ON low.borough = z.borough
)
SELECT borough, borough_yoy_pct, rank_no, pu_location_id, zone, ytd_revenue, stly_ytd_revenue, revenue_change
FROM ranked WHERE rank_no <= 10
ORDER BY rank_no
