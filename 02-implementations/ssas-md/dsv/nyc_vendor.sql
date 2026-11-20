-- DSV named query nyc_vendor: database dimension Vendor (TLC technology providers present in the trips).
SELECT DISTINCT
  t.vendor_id,
  CAST(t.vendor_id AS VARCHAR(5)) AS vendor_name
FROM nyctaxi.fact_trip t
