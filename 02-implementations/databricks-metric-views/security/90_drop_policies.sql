-- Accelerated profile: remove the ABAC policies, because a metric view cannot be materialized when any source table
-- is governed by RLS, column masks or ABAC policies (SPEC B-01). DROP POLICY has no IF EXISTS; the deploy job treats
-- POLICY_NOT_FOUND as already removed.
DROP POLICY slc_wwi_sales_territory ON SCHEMA slc.wwi;
DROP POLICY slc_wwi_inventory_denied ON SCHEMA slc.wwi;
DROP POLICY slc_nyc_manhattan_pickup ON SCHEMA slc.nyctaxi;
