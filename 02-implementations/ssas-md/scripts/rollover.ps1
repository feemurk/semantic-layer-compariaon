<#
.SYNOPSIS
  E6 monthly rollover of the NYC measure groups: create and process the closed month, re-slice the ROLAP hot
  partition, retire partitions beyond 24 months, clear the hot partition cache (jobs/partition_rollover.py).
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $SsasServer,
  [Parameter(Mandatory)] [ValidatePattern('^\d{4}-(0[1-9]|1[0-2])$')] [string] $CloseMonth
)
$ErrorActionPreference = 'Stop'
Import-Module SqlServer
$root = Split-Path -Parent $PSScriptRoot

[xml] $cube = Invoke-ASCmd -Server $SsasServer -Query @"
<Discover xmlns="urn:schemas-microsoft-com:xml-analysis">
  <RequestType>DISCOVER_XML_METADATA</RequestType>
  <Restrictions><RestrictionList><DatabaseID>slc</DatabaseID><CubeID>NYC</CubeID><ObjectExpansion>ExpandFull</ObjectExpansion></RestrictionList></Restrictions>
  <Properties><PropertyList/></Properties>
</Discover>
"@
$partitions = $cube.GetElementsByTagName('Partition') | ForEach-Object { $_.ID } | Where-Object { $_ }
if (-not $partitions) { throw 'no partitions found in cube NYC' }

$work = Join-Path ([IO.Path]::GetTempPath()) "slc_rollover_$CloseMonth"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$batch = Join-Path $work 'rollover.xmla'
$clear = Join-Path $work 'clear_cache.xmla'
python (Join-Path $root 'jobs/partition_rollover.py') --close $CloseMonth --current ($partitions -join ',') `
  --out $batch --clear-cache-out $clear
if ($LASTEXITCODE -ne 0) { throw 'partition_rollover.py failed' }

foreach ($file in $batch, $clear) {
  Write-Host "ssas: $(Split-Path -Leaf $file)"
  $result = Invoke-ASCmd -Server $SsasServer -InputFile $file
  if ($result -match '<Error ') { throw "$(Split-Path -Leaf $file) failed: $result" }
}
