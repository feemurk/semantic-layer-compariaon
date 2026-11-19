-- One-time prerequisite before `databricks bundle deploy`: the Unity Catalog connection
-- (type SQLSERVER) that the Lakeflow Connect gateway uses. Run in the Databricks SQL editor
-- as a metastore admin or a principal with CREATE CONNECTION.
-- Store credentials first (Databricks CLI):
--   databricks secrets create-scope slc
--   databricks secrets put-secret slc wwi_sqlserver_user
--   databricks secrets put-secret slc wwi_sqlserver_password
-- Replace the host value with the DNS name of the SQL Server 2025 instance holding the restored copy.
-- The connection name must match the bundle variable `sqlserver_connection`.
CREATE CONNECTION IF NOT EXISTS slc_wwi_sqlserver TYPE sqlserver
OPTIONS (
  host 'wwi-staging.slc.internal',
  port '1433',
  user secret ('slc', 'wwi_sqlserver_user'),
  password secret ('slc', 'wwi_sqlserver_password')
);
