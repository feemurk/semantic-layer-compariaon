-- SQL Server 2025 adapter for S1 (SSAS Multidimensional): PolyBase ODBC-generic access to Databricks serverless SQL.
-- Why: ODBC data sources are not supported for multidimensional models, and ROLAP storage requires a SQL Server
-- relational source (https://learn.microsoft.com/en-us/analysis-services/multidimensional-models/
-- supported-data-sources-ssas-multidimensional, checked 2026-11-20). PolyBase external tables keep Databricks the
-- single physical source (SPEC D-08) while SSAS connects to SQL Server through MSOLEDBSQL.
-- PolyBase ODBC generic: https://learn.microsoft.com/en-us/sql/relational-databases/polybase/polybase-configure-odbc-generic
-- Databricks ODBC driver settings: https://docs.databricks.com/aws/en/integrations/odbc/authentication (checked 2026-11-20).
-- Run with sqlcmd variables; no secret is stored in the repository:
--   sqlcmd -S slc-sql2025 -i 01_polybase.sql -v DATABRICKS_HOST="<workspace host>" DATABRICKS_HTTP_PATH="<warehouse path>"
--          DATABRICKS_TOKEN="<token from the secret store>" ADAPTER_MASTER_KEY_PASSWORD="<from the secret store>"
-- deploy.ps1 passes these from environment variables of the CI runner.

EXEC sp_configure @configname = N'polybase enabled', @configvalue = 1;
RECONFIGURE;
GO

IF DB_ID(N'slc_adapter') IS NULL
  CREATE DATABASE slc_adapter;
GO

USE slc_adapter;
GO

IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##')
  CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'$(ADAPTER_MASTER_KEY_PASSWORD)';
GO

IF EXISTS (SELECT 1 FROM sys.external_data_sources WHERE name = N'slc_databricks')
  DROP EXTERNAL DATA SOURCE slc_databricks;
GO

IF EXISTS (SELECT 1 FROM sys.database_scoped_credentials WHERE name = N'slc_databricks_token')
  DROP DATABASE SCOPED CREDENTIAL slc_databricks_token;
GO

-- Databricks ODBC token authentication (AuthMech=3): the identity is the literal "token", the secret the token.
CREATE DATABASE SCOPED CREDENTIAL slc_databricks_token
  WITH IDENTITY = N'token', SECRET = N'$(DATABRICKS_TOKEN)';
GO

-- PUSHDOWN = ON sends partition predicates and aggregations of ROLAP queries to the SQL warehouse.
CREATE EXTERNAL DATA SOURCE slc_databricks
WITH (
  LOCATION = 'odbc://$(DATABRICKS_HOST):443',
  PUSHDOWN = ON,
  CONNECTION_OPTIONS = 'Driver={Databricks ODBC Driver};Host=$(DATABRICKS_HOST);Port=443;HTTPPath=$(DATABRICKS_HTTP_PATH);SSL=1;ThriftTransport=2;AuthMech=3',
  CREDENTIAL = slc_databricks_token
);
GO
