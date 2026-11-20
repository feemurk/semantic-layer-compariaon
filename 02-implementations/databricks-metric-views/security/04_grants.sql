-- SPEC § 10, governed profile: the two restricted roles query the semantic layer only. Any principal with SELECT on a
-- metric view can query it, and the view reads its sources with its owner's privileges
-- (https://docs.databricks.com/aws/en/uc-semantics/metric-views/manage), so no grant on slc.wwi or slc.nyctaxi is issued.
-- That the ABAC policies on those schemas still filter by the querying principal is verification item V-27.
GRANT USE CATALOG ON CATALOG slc TO `slc_territory_southeast`;
GRANT USE SCHEMA, SELECT ON SCHEMA slc.semantic TO `slc_territory_southeast`;
GRANT USE CATALOG ON CATALOG slc TO `slc_pickup_manhattan`;
GRANT USE SCHEMA, SELECT ON SCHEMA slc.semantic TO `slc_pickup_manhattan`;
