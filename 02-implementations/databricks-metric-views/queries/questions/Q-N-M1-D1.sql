-- Q-N-M1-D1 Distinct OD pairs by payment type for 2024, the overall total (separate view evaluation, not a sum), and the sum of members.
WITH by_type AS (
  SELECT payment_type_name, MEASURE(distinct_od_pairs) AS distinct_od_pairs
  FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024 GROUP BY payment_type_name
),
total AS (SELECT MEASURE(distinct_od_pairs) AS distinct_od_pairs FROM slc.semantic.nyc_trips WHERE YEAR(pickup_year) = 2024)
SELECT grain, payment_type_name, distinct_od_pairs
FROM (
  SELECT 'payment_type' AS grain, payment_type_name, distinct_od_pairs FROM by_type
  UNION ALL SELECT 'total', CAST(NULL AS STRING), distinct_od_pairs FROM total
  UNION ALL SELECT 'sum_of_members', CAST(NULL AS STRING), SUM(distinct_od_pairs) FROM by_type
) r
ORDER BY grain, payment_type_name NULLS FIRST
