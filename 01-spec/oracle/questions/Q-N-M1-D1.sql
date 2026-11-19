-- Q-N-M1-D1 Distinct OD pairs by payment type for 2024 (grain 'payment_type'), the overall total (grain 'total') and the
-- sum of the payment-type values (grain 'sum_of_members'), which exceeds the total because one pair occurs under several payment types.
WITH y AS (
  SELECT f.od_pair_id, pt.payment_type_name
  FROM nyctaxi.fact_trip f
  JOIN nyctaxi.dim_date d ON d.date_key = f.pickup_date
  JOIN nyctaxi.dim_payment_type pt ON pt.payment_type = f.payment_type
  WHERE d.calendar_year = 2024
),
by_type AS (SELECT payment_type_name, COUNT(DISTINCT od_pair_id) AS distinct_od_pairs FROM y GROUP BY payment_type_name)
SELECT grain, payment_type_name, distinct_od_pairs
FROM (
  SELECT 'payment_type' AS grain, payment_type_name, distinct_od_pairs FROM by_type
  UNION ALL
  SELECT 'total', CAST(NULL AS STRING), COUNT(DISTINCT od_pair_id) FROM y
  UNION ALL
  SELECT 'sum_of_members', CAST(NULL AS STRING), SUM(distinct_od_pairs) FROM by_type
) r
ORDER BY grain, payment_type_name NULLS FIRST
