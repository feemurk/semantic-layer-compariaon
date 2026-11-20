-- DSV named query nyc_trips: measure groups Trips and OD Pairs (trip grain). Partitions append a pickup_date range
-- to this query (build_model.py). card_tip and card_trip carry the payment-type-1 scope of N-S2 into additive sums.
SELECT
  t.trip_id,
  YEAR(t.pickup_date) * 10000 + MONTH(t.pickup_date) * 100 + DAY(t.pickup_date) AS pickup_date_id,
  YEAR(t.dropoff_date) * 10000 + MONTH(t.dropoff_date) * 100 + DAY(t.dropoff_date) AS dropoff_date_id,
  t.pickup_hour,
  t.pu_location_id,
  t.do_location_id,
  t.payment_type,
  t.vendor_id,
  t.od_pair_id,
  t.trip_distance,
  t.fare_amount,
  t.tip_amount,
  t.tolls_amount,
  t.total_amount,
  CASE WHEN t.payment_type = 1 THEN t.tip_amount ELSE 0 END AS card_tip,
  CASE WHEN t.payment_type = 1 THEN 1 ELSE 0 END AS card_trip
FROM nyctaxi.fact_trip t
