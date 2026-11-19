-- Restore the official WideWorldImporters samples (v1.0 release) onto SQL Server 2025.
-- sqlcmd variables:
--   BACKUP_DIR  directory holding WideWorldImportersDW-Full.bak and WideWorldImporters-Full.bak
--   DATA_DIR    directory for the restored data and log files
-- Source: https://github.com/Microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0
-- This is the dedicated staging copy for ingestion; REPLACE overwrites an earlier restore.
SET NOCOUNT ON;

RESTORE DATABASE [WideWorldImportersDW]
FROM DISK = N'$(BACKUP_DIR)/WideWorldImportersDW-Full.bak'
WITH REPLACE,
     MOVE N'WWI_Primary' TO N'$(DATA_DIR)/WideWorldImportersDW.mdf',
     MOVE N'WWI_UserData' TO N'$(DATA_DIR)/WideWorldImportersDW_UserData.ndf',
     MOVE N'WWI_Log' TO N'$(DATA_DIR)/WideWorldImportersDW.ldf',
     MOVE N'WWIDW_InMemory_Data_1' TO N'$(DATA_DIR)/WideWorldImportersDW_InMemory_Data_1';
GO

RESTORE DATABASE [WideWorldImporters]
FROM DISK = N'$(BACKUP_DIR)/WideWorldImporters-Full.bak'
WITH REPLACE,
     MOVE N'WWI_Primary' TO N'$(DATA_DIR)/WideWorldImporters.mdf',
     MOVE N'WWI_UserData' TO N'$(DATA_DIR)/WideWorldImporters_UserData.ndf',
     MOVE N'WWI_Log' TO N'$(DATA_DIR)/WideWorldImporters.ldf',
     MOVE N'WWI_InMemory_Data_1' TO N'$(DATA_DIR)/WideWorldImporters_InMemory_Data_1';
GO
