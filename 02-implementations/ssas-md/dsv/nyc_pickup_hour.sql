-- DSV named query nyc_pickup_hour: database dimension Pickup Hour (0-23).
SELECT DISTINCT
  t.pickup_hour,
  CAST(t.pickup_hour AS VARCHAR(2)) AS pickup_hour_name
FROM nyctaxi.fact_trip t
