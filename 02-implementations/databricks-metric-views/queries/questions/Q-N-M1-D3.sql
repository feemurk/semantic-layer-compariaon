-- Q-N-M1-D3 Distinct OD pairs served by each vendor, 2023 vs 2024.
WITH v AS (
  SELECT vendor_id, pickup_year, MEASURE(distinct_od_pairs) AS pairs FROM slc.semantic.nyc_trips GROUP BY vendor_id, pickup_year
)
SELECT vendor_id,
       COALESCE(MAX(CASE WHEN YEAR(pickup_year) = 2023 THEN pairs END), 0) AS distinct_od_pairs_2023,
       COALESCE(MAX(CASE WHEN YEAR(pickup_year) = 2024 THEN pairs END), 0) AS distinct_od_pairs_2024
FROM v
GROUP BY vendor_id
ORDER BY vendor_id
