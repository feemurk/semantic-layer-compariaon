<#
.SYNOPSIS
  Deploy S1: the SQL Server 2025 PolyBase adapter, then the SSAS Multidimensional database, then process it.
.DESCRIPTION
  1. adapter/01_polybase.sql, 02_external_tables.sql, 03_statistics.sql on the adapter instance (sqlcmd variables from
     environment variables; no secret is stored in the repository).
  2. deploy/slc.xmla (XMLA Create, AllowOverwrite) on the SSAS instance, with the data source connection string and
     role members rewritten for the target environment.
  3. deploy/process_full.xmla.
  Requires the SqlServer PowerShell module (Invoke-Sqlcmd, Invoke-ASCmd).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $SsasServer,
  [Parameter(Mandatory)] [string] $SqlServer,
  [string] $RoleDomain = 'SLC',
  [switch] $SkipAdapter,
  [switch] $SkipProcess
)
$ErrorActionPreference = 'Stop'
Import-Module SqlServer
$root = Split-Path -Parent $PSScriptRoot

if (-not $SkipAdapter) {
  foreach ($name in 'DATABRICKS_HOST', 'DATABRICKS_HTTP_PATH', 'DATABRICKS_TOKEN', 'ADAPTER_MASTER_KEY_PASSWORD') {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "environment variable $name is not set" }
  }
  $vars = @(
    "DATABRICKS_HOST=$env:DATABRICKS_HOST",
    "DATABRICKS_HTTP_PATH=$env:DATABRICKS_HTTP_PATH",
    "DATABRICKS_TOKEN=$env:DATABRICKS_TOKEN",
    "ADAPTER_MASTER_KEY_PASSWORD=$env:ADAPTER_MASTER_KEY_PASSWORD"
  )
  foreach ($script in '01_polybase.sql', '02_external_tables.sql', '03_statistics.sql') {
    Write-Host "adapter: $script"
    Invoke-Sqlcmd -ServerInstance $SqlServer -InputFile (Join-Path $root "adapter/$script") -Variable $vars `
      -TrustServerCertificate -QueryTimeout 0
  }
}

[xml] $create = Get-Content -Raw -Path (Join-Path $root 'deploy/slc.xmla')
$ns = New-Object System.Xml.XmlNamespaceManager($create.NameTable)
$ns.AddNamespace('a', 'http://schemas.microsoft.com/analysisservices/2003/engine')
$cs = $create.SelectSingleNode('//a:DataSource/a:ConnectionString', $ns)
$cs.InnerText = $cs.InnerText -replace 'Data Source=[^;]+', "Data Source=$SqlServer"
foreach ($member in $create.SelectNodes('//a:Role/a:Members/a:Member/a:Name', $ns)) {
  $member.InnerText = $member.InnerText -replace '^[^\\]+\\', "$RoleDomain\"
}
$staged = Join-Path ([IO.Path]::GetTempPath()) 'slc_md_create.xmla'
$create.Save($staged)
Write-Host "ssas: create database slc on $SsasServer"
$result = Invoke-ASCmd -Server $SsasServer -InputFile $staged
if ($result -match '<Error ') { throw "XMLA Create failed: $result" }

if (-not $SkipProcess) {
  Write-Host 'ssas: ProcessFull'
  $result = Invoke-ASCmd -Server $SsasServer -InputFile (Join-Path $root 'deploy/process_full.xmla')
  if ($result -match '<Error ') { throw "ProcessFull failed: $result" }
}
