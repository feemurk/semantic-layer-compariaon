-- P-NYC-02 every fact_trip row satisfies the valid trip predicate (SPEC § 5.3 rule 1)
SELECT trip_id, pickup_ts, dropoff_ts, trip_distance, fare_amount, total_amount
FROM nyctaxi.fact_trip
WHERE NOT (
      pickup_ts < dropoff_ts
  AND trip_distance > 0 AND trip_distance <= 200
  AND fare_amount >= 0
  AND total_amount >= 0
  AND pickup_date BETWEEN DATE'2023-01-01' AND DATE'2024-12-31'
)
