-- Q-N-C1-D1 YoY % of YTD gross trip revenue at 2024-06-30 by pickup borough (YTD 2024-01-01..06-30 vs 2023-01-01..06-30).
WITH b AS (
  SELECT pz.borough AS pickup_borough,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2024-01-01' AND DATE '2024-06-30' THEN f.total_amount END) AS ytd_revenue,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2023-01-01' AND DATE '2023-06-30' THEN f.total_amount END) AS stly_ytd_revenue
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_zone pz ON pz.location_id = f.pu_location_id
  WHERE f.pickup_date BETWEEN DATE '2023-01-01' AND DATE '2024-06-30'
  GROUP BY pz.borough
)
SELECT pickup_borough, ytd_revenue, stly_ytd_revenue,
       CAST(ytd_revenue - stly_ytd_revenue AS DOUBLE) / NULLIF(CAST(stly_ytd_revenue AS DOUBLE), 0) AS yoy_pct
FROM b
ORDER BY pickup_borough
