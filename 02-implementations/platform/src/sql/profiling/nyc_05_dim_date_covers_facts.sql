-- P-NYC-05 nyctaxi.dim_date is gap-free over 2023-2025 and covers every pickup and dropoff date (SPEC § 5.4)
SELECT 'gap or range error' AS violation, CAST(NULL AS DATE) AS missing_date
FROM (SELECT COUNT(*) AS n, MIN(date_key) AS mn, MAX(date_key) AS mx FROM nyctaxi.dim_date) d
WHERE n <> DATEDIFF(mx, mn) + 1 OR mn <> DATE'2023-01-01' OR mx <> DATE'2025-12-31'
UNION ALL
SELECT 'fact date outside dim_date', f.d
FROM (
  SELECT pickup_date AS d FROM nyctaxi.fact_trip
  UNION SELECT dropoff_date FROM nyctaxi.fact_trip
) f
LEFT ANTI JOIN nyctaxi.dim_date d ON d.date_key = f.d
