-- Run after installing the Databricks "utility objects script" (utility_script.sql) in BOTH
-- WideWorldImportersDW and WideWorldImporters, downloaded from:
--   https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/sql-server-utility
-- Table-level change tracking is enabled natively by 02_wwi_source_prep.sql; this call performs
-- the database-level Lakeflow setup only (@Tables = NULL), as the utility documentation allows.
-- sqlcmd variable: INGEST_LOGIN (same value as in 02_wwi_source_prep.sql).
SET NOCOUNT ON;
GO
USE [WideWorldImportersDW];
EXEC dbo.lakeflowSetupChangeTracking @Tables = NULL, @User = N'$(INGEST_LOGIN)', @Retention = '2 DAYS';
GO
USE [WideWorldImporters];
EXEC dbo.lakeflowSetupChangeTracking @Tables = NULL, @User = N'$(INGEST_LOGIN)', @Retention = '2 DAYS';
GO
