-- P-NYC-03 every quarantine row carries the first failed rule, in SPEC § 5.3 rule 1 order
SELECT trip_id, reject_reason, expected_reason
FROM (
  SELECT trip_id, reject_reason,
         CASE
           WHEN NOT COALESCE(pickup_ts < dropoff_ts, FALSE) THEN 'pickup_not_before_dropoff'
           WHEN NOT COALESCE(trip_distance > 0 AND trip_distance <= 200, FALSE) THEN 'trip_distance_out_of_range'
           WHEN NOT COALESCE(fare_amount >= 0, FALSE) THEN 'negative_fare_amount'
           WHEN NOT COALESCE(total_amount >= 0, FALSE) THEN 'negative_total_amount'
           WHEN NOT COALESCE(pickup_date BETWEEN DATE'2023-01-01' AND DATE'2024-12-31', FALSE) THEN 'pickup_outside_window'
         END AS expected_reason
  FROM nyctaxi.fact_trip_quarantine
) q
WHERE expected_reason IS NULL OR reject_reason <> expected_reason
