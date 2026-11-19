-- Prepare the restored WideWorldImporters copy for Lakeflow Connect change tracking ingestion.
-- Idempotent. Run as a sysadmin with sqlcmd variables:
--   INGEST_LOGIN     SQL login the Unity Catalog connection uses
--   INGEST_PASSWORD  its password (supply from a secret store; never commit it)
--
-- Why indexes are dropped: SQL Server rejects both change tracking and CDC on tables with a
-- clustered columnstore index (Msg 35353), and every WideWorldImportersDW fact table has one.
-- Dropping the index leaves the rows and the primary key unchanged; the table becomes a
-- rowstore heap that change tracking accepts. Verified on SQL Server 2025 with row counts and
-- [Total Excluding Tax] sums identical before and after.
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

USE [master];
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'$(INGEST_LOGIN)')
    CREATE LOGIN [$(INGEST_LOGIN)] WITH PASSWORD = N'$(INGEST_PASSWORD)', CHECK_POLICY = ON;
GRANT VIEW ANY DATABASE TO [$(INGEST_LOGIN)];
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(INGEST_LOGIN)')
    CREATE USER [$(INGEST_LOGIN)] FOR LOGIN [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.databases TO [$(INGEST_LOGIN)];
GRANT EXECUTE ON OBJECT::sp_tables TO [$(INGEST_LOGIN)];
GRANT EXECUTE ON OBJECT::sp_columns_100 TO [$(INGEST_LOGIN)];
GRANT EXECUTE ON OBJECT::sp_pkeys TO [$(INGEST_LOGIN)];
GRANT EXECUTE ON OBJECT::sp_statistics_100 TO [$(INGEST_LOGIN)];
GO

-- ---------------------------------------------------------------- WideWorldImportersDW
USE [WideWorldImportersDW];

DECLARE @cci TABLE (schema_name sysname, table_name sysname, index_name sysname);
INSERT @cci VALUES
    (N'Fact', N'Sale', N'CCX_Fact_Sale'),
    (N'Fact', N'Order', N'CCX_Fact_Order'),
    (N'Fact', N'Movement', N'CCX_Fact_Movement'),
    (N'Fact', N'Stock Holding', N'CCX_Fact_Stock_Holding');

DECLARE @s sysname, @t sysname, @i sysname, @sql nvarchar(max);
DECLARE cci CURSOR LOCAL FAST_FORWARD FOR SELECT schema_name, table_name, index_name FROM @cci;
OPEN cci;
FETCH NEXT FROM cci INTO @s, @t, @i;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = @i AND object_id = OBJECT_ID(QUOTENAME(@s) + N'.' + QUOTENAME(@t)))
    BEGIN
        SET @sql = N'DROP INDEX ' + QUOTENAME(@i) + N' ON ' + QUOTENAME(@s) + N'.' + QUOTENAME(@t) + N';';
        EXEC sys.sp_executesql @sql;
    END;
    FETCH NEXT FROM cci INTO @s, @t, @i;
END;
CLOSE cci;
DEALLOCATE cci;
GO

USE [WideWorldImportersDW];
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_databases WHERE database_id = DB_ID())
    ALTER DATABASE CURRENT SET CHANGE_TRACKING = ON (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(INGEST_LOGIN)')
    CREATE USER [$(INGEST_LOGIN)] FOR LOGIN [$(INGEST_LOGIN)];
GRANT VIEW DATABASE PERFORMANCE STATE TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.indexes TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.index_columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.tables TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.fulltext_index_columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.fulltext_indexes TO [$(INGEST_LOGIN)];

DECLARE @tables TABLE (schema_name sysname, table_name sysname);
INSERT @tables VALUES
    (N'Fact', N'Sale'), (N'Fact', N'Order'), (N'Fact', N'Movement'), (N'Fact', N'Stock Holding'),
    (N'Dimension', N'Stock Item'), (N'Dimension', N'Customer'), (N'Dimension', N'City'),
    (N'Dimension', N'Employee'), (N'Dimension', N'Date');

DECLARE @s sysname, @t sysname, @obj nvarchar(300), @sql nvarchar(max);
DECLARE ct CURSOR LOCAL FAST_FORWARD FOR SELECT schema_name, table_name FROM @tables;
OPEN ct;
FETCH NEXT FROM ct INTO @s, @t;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @obj = QUOTENAME(@s) + N'.' + QUOTENAME(@t);
    IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_tables WHERE object_id = OBJECT_ID(@obj))
    BEGIN
        SET @sql = N'ALTER TABLE ' + @obj + N' ENABLE CHANGE_TRACKING;';
        EXEC sys.sp_executesql @sql;
    END;
    SET @sql = N'GRANT SELECT, VIEW CHANGE TRACKING ON OBJECT::' + @obj + N' TO [$(INGEST_LOGIN)];';
    EXEC sys.sp_executesql @sql;
    FETCH NEXT FROM ct INTO @s, @t;
END;
CLOSE ct;
DEALLOCATE ct;
GO

-- ---------------------------------------------------------------- WideWorldImporters (OLTP)
USE [WideWorldImporters];
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_databases WHERE database_id = DB_ID())
    ALTER DATABASE CURRENT SET CHANGE_TRACKING = ON (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(INGEST_LOGIN)')
    CREATE USER [$(INGEST_LOGIN)] FOR LOGIN [$(INGEST_LOGIN)];
GRANT VIEW DATABASE PERFORMANCE STATE TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.indexes TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.index_columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.tables TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.fulltext_index_columns TO [$(INGEST_LOGIN)];
GRANT SELECT ON OBJECT::sys.fulltext_indexes TO [$(INGEST_LOGIN)];

-- Warehouse.StockGroups is system-versioned temporal; change tracking applies to the current table.
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_tables WHERE object_id = OBJECT_ID(N'Warehouse.StockGroups'))
    ALTER TABLE [Warehouse].[StockGroups] ENABLE CHANGE_TRACKING;
IF NOT EXISTS (SELECT 1 FROM sys.change_tracking_tables WHERE object_id = OBJECT_ID(N'Warehouse.StockItemStockGroups'))
    ALTER TABLE [Warehouse].[StockItemStockGroups] ENABLE CHANGE_TRACKING;
GRANT SELECT, VIEW CHANGE TRACKING ON OBJECT::[Warehouse].[StockGroups] TO [$(INGEST_LOGIN)];
GRANT SELECT, VIEW CHANGE TRACKING ON OBJECT::[Warehouse].[StockItemStockGroups] TO [$(INGEST_LOGIN)];
GO
