-- Q-N-C1-D3 YTD gross trip revenue and YoY % at 2024-12-31 by payment type (YTD = calendar 2024 vs STLY = calendar 2023).
WITH p AS (
  SELECT pt.payment_type_name,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2024-01-01' AND DATE '2024-12-31' THEN f.total_amount END) AS ytd_revenue,
         SUM(CASE WHEN f.pickup_date BETWEEN DATE '2023-01-01' AND DATE '2023-12-31' THEN f.total_amount END) AS stly_ytd_revenue
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
  GROUP BY pt.payment_type_name
)
SELECT payment_type_name, ytd_revenue, stly_ytd_revenue,
       CAST(ytd_revenue - stly_ytd_revenue AS DOUBLE) / NULLIF(CAST(stly_ytd_revenue AS DOUBLE), 0) AS yoy_pct
FROM p
ORDER BY payment_type_name
