-- SPEC § 10 row-level security, governed profile: row filter functions.
-- Parameters are qualified with the function name inside the subqueries so they cannot be captured by a column of the
-- same name in the lookup table.
CREATE SCHEMA IF NOT EXISTS slc.security COMMENT 'Row filter functions for the study security scenario (SPEC § 10).';

CREATE OR REPLACE FUNCTION slc.security.rls_wwi_southeast(city_key INT)
RETURNS BOOLEAN
COMMENT 'Territory Analyst - Southeast: sale and order rows whose as-was city is in the Southeast sales territory.'
RETURN EXISTS (
  SELECT 1 FROM slc.wwi.dim_city c
  WHERE c.city_key = rls_wwi_southeast.city_key AND c.sales_territory = 'Southeast'
);

CREATE OR REPLACE FUNCTION slc.security.rls_deny_all()
RETURNS BOOLEAN
COMMENT 'No rows: inventory facts carry no geography, so the territory analyst sees no stock (W-M2 and W-C2 return NULL).'
RETURN FALSE;

CREATE OR REPLACE FUNCTION slc.security.rls_nyc_manhattan_pickup(pu_location_id INT)
RETURNS BOOLEAN
COMMENT 'Manhattan Pickup Analyst: trips whose pickup zone is in Manhattan; the dropoff role is not restricted.'
RETURN EXISTS (
  SELECT 1 FROM slc.nyctaxi.dim_zone z
  WHERE z.location_id = rls_nyc_manhattan_pickup.pu_location_id AND z.borough = 'Manhattan'
);
