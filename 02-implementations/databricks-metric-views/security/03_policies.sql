-- SPEC § 10, governed profile: ABAC row filter policies. Principals are the account groups of the two restricted roles.
CREATE OR REPLACE POLICY slc_wwi_sales_territory
ON SCHEMA slc.wwi
COMMENT 'Territory Analyst - Southeast: sales and orders restricted to the Southeast sales territory.'
ROW FILTER slc.security.rls_wwi_southeast
TO `slc_territory_southeast`
FOR TABLES
WHEN has_tag_value('slc_rls_scope', 'sales_territory')
MATCH COLUMNS has_tag_value('slc_rls_key', 'city_key') AS city_key
USING COLUMNS (city_key);

CREATE OR REPLACE POLICY slc_wwi_inventory_denied
ON SCHEMA slc.wwi
COMMENT 'Territory Analyst - Southeast: no inventory access.'
ROW FILTER slc.security.rls_deny_all
TO `slc_territory_southeast`
FOR TABLES
WHEN has_tag_value('slc_rls_scope', 'inventory');

CREATE OR REPLACE POLICY slc_nyc_manhattan_pickup
ON SCHEMA slc.nyctaxi
COMMENT 'Manhattan Pickup Analyst: trips restricted to Manhattan pickup zones.'
ROW FILTER slc.security.rls_nyc_manhattan_pickup
TO `slc_pickup_manhattan`
FOR TABLES
WHEN has_tag_value('slc_rls_scope', 'pickup_borough')
MATCH COLUMNS has_tag_value('slc_rls_key', 'pu_location_id') AS pu_location_id
USING COLUMNS (pu_location_id);
