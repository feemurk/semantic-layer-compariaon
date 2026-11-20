-- DSV named query nyc_zone: database dimension Zone, role-played as Pickup Zone and Dropoff Zone.
SELECT
  z.location_id,
  CAST(z.location_id AS VARCHAR(5)) AS location_id_name,
  z.zone,
  z.borough,
  z.service_zone
FROM nyctaxi.dim_zone z
