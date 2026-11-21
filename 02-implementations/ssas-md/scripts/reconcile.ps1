<#
.SYNOPSIS
  E1/E2 reconciliation of S1: run queries/metrics/*.mdx and queries/questions/*.mdx through ADOMD.NET, flatten each
  cell set to CSV, and compare with the oracle (tools/compare.py).
.DESCRIPTION
  Flattening rules (documented in SSAS_MD_GUIDE.md § 7):
  - metric files: each "// @branch grain=... rows=... values=label:[Measures].[M],..." statement yields contract rows
    (grain, measure, member_1..3, value); member_i is the caption of the row member on the i-th declared hierarchy.
  - question files: "// @column name = source" lines give the output columns in order; a source is a row hierarchy
    (its member caption) or a measure on the COLUMNS axis (its cell value).
  - an All member flattens to an empty value; numbers use the invariant culture, doubles round-trip ("R").
  Timings: the first run of each statement is the cold run; -Repeat further runs give the warm median.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string] $SsasServer,
  [string] $Select = '*',
  [int] $Repeat = 1,
  [string] $OutDir = (Join-Path ([IO.Path]::GetTempPath()) 'slc_md_reconcile'),
  [switch] $FailOnMismatch
)
$ErrorActionPreference = 'Stop'
Import-Module SqlServer
$root = Split-Path -Parent $PSScriptRoot
$adomd = Get-ChildItem -Path (Get-Module SqlServer).ModuleBase -Recurse -Filter 'Microsoft.AnalysisServices.AdomdClient.dll' |
  Select-Object -First 1
if (-not $adomd) { throw 'Microsoft.AnalysisServices.AdomdClient.dll not found in the SqlServer module' }
Add-Type -Path $adomd.FullName
$inv = [Globalization.CultureInfo]::InvariantCulture

function Format-Value($v) {
  if ($null -eq $v) { return '' }
  if ($v -is [double] -or $v -is [single]) { return $v.ToString('R', $inv) }
  if ($v -is [decimal]) { return $v.ToString($inv) }
  if ($v -is [IFormattable]) { return $v.ToString($null, $inv) }
  return [string] $v
}

function Get-Caption($tuple, [string] $hierarchy) {
  foreach ($m in $tuple.Members) {
    if ($m.ParentLevel.ParentHierarchy.UniqueName -eq $hierarchy) {
      if ($m.LevelDepth -eq 0) { return '' }
      return $m.Caption
    }
  }
  throw "row hierarchy $hierarchy not found on the ROWS axis"
}

function Invoke-Mdx($conn, [string] $mdx) {
  $times = @()
  $cs = $null
  for ($i = 0; $i -lt [Math]::Max(1, $Repeat); $i++) {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = $mdx
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $cs = $cmd.ExecuteCellSet()
    $sw.Stop()
    $times += $sw.Elapsed.TotalSeconds
  }
  return @{ CellSet = $cs; Seconds = $times }
}

function ConvertTo-CsvLine([string[]] $values) {
  ($values | ForEach-Object { '"' + ($_ -replace '"', '""') + '"' }) -join ','
}

$conn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=$SsasServer;Catalog=slc")
$conn.Open()
$timings = @()
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir 'metrics'), (Join-Path $OutDir 'questions') | Out-Null

foreach ($file in Get-ChildItem (Join-Path $root 'queries/metrics') -Filter "$Select.mdx") {
  $text = Get-Content -Raw $file.FullName
  $lines = @(ConvertTo-CsvLine @('grain', 'measure', 'member_1', 'member_2', 'member_3', 'value'))
  $parts = [regex]::Split($text, '(?m)^(?=// @branch )') | Where-Object { $_ -match '^// @branch ' }
  foreach ($part in $parts) {
    $m = [regex]::Match($part, '^// @branch grain=(\S+) rows=(.*?) values=(.+?)\s*$', 'Multiline')
    $grain = $m.Groups[1].Value
    $rows = @($m.Groups[2].Value -split ';' | Where-Object { $_ })
    $values = [regex]::Split($m.Groups[3].Value, ',(?=[A-Z]-[A-Z0-9])') | ForEach-Object {
      $i = $_.IndexOf(':[Measures]'); @{ Label = $_.Substring(0, $i); Measure = $_.Substring($i + 1) } }
    $stmt = $part.Substring($m.Length).Trim()
    $r = Invoke-Mdx $conn $stmt
    $timings += [pscustomobject]@{ query = "$($file.BaseName)/$grain"; seconds = $r.Seconds }
    $cs = $r.CellSet
    $colIndex = @{}
    for ($c = 0; $c -lt $cs.Axes[0].Positions.Count; $c++) {
      $colIndex[$cs.Axes[0].Positions[$c].Members[0].UniqueName] = $c
    }
    $rowCount = if ($cs.Axes.Count -gt 1) { $cs.Axes[1].Positions.Count } else { 1 }
    for ($p = 0; $p -lt $rowCount; $p++) {
      $members = @('', '', '')
      if ($cs.Axes.Count -gt 1) {
        for ($k = 0; $k -lt $rows.Count; $k++) { $members[$k] = Get-Caption $cs.Axes[1].Positions[$p] $rows[$k] }
      }
      foreach ($v in $values) {
        $c = $colIndex[$v.Measure]
        $cell = if ($cs.Axes.Count -gt 1) { $cs.Cells[$c, $p] } else { $cs.Cells[$c] }
        $lines += ConvertTo-CsvLine @($grain, $v.Label, $members[0], $members[1], $members[2], (Format-Value $cell.Value))
      }
    }
  }
  Set-Content -Path (Join-Path $OutDir "metrics/$($file.BaseName).csv") -Value $lines -Encoding utf8NoBOM
}

foreach ($file in Get-ChildItem (Join-Path $root 'queries/questions') -Filter "$Select.mdx") {
  $text = Get-Content -Raw $file.FullName
  $columns = [regex]::Matches($text, '(?m)^// @column (\w+) = (.+?)\s*$') | ForEach-Object {
    @{ Name = $_.Groups[1].Value; Source = $_.Groups[2].Value } }
  $r = Invoke-Mdx $conn $text
  $timings += [pscustomobject]@{ query = $file.BaseName; seconds = $r.Seconds }
  $cs = $r.CellSet
  $colIndex = @{}
  for ($c = 0; $c -lt $cs.Axes[0].Positions.Count; $c++) {
    $colIndex[$cs.Axes[0].Positions[$c].Members[0].UniqueName] = $c
  }
  $lines = @(ConvertTo-CsvLine @($columns | ForEach-Object { $_.Name }))
  $rowCount = if ($cs.Axes.Count -gt 1) { $cs.Axes[1].Positions.Count } else { 1 }
  for ($p = 0; $p -lt $rowCount; $p++) {
    $out = foreach ($col in $columns) {
      if ($col.Source.StartsWith('[Measures].')) {
        $c = $colIndex[$col.Source]
        $cell = if ($cs.Axes.Count -gt 1) { $cs.Cells[$c, $p] } else { $cs.Cells[$c] }
        Format-Value $cell.Value
      } else {
        Get-Caption $cs.Axes[1].Positions[$p] $col.Source
      }
    }
    $lines += ConvertTo-CsvLine @($out)
  }
  Set-Content -Path (Join-Path $OutDir "questions/$($file.BaseName).csv") -Value $lines -Encoding utf8NoBOM
}
$conn.Close()
$timings | ConvertTo-Json -Depth 3 | Set-Content -Path (Join-Path $OutDir 'timings.json') -Encoding utf8NoBOM

python (Join-Path $root 'tools/compare.py') --actual $OutDir --select $Select --report (Join-Path $OutDir 'report.json')
if ($LASTEXITCODE -ne 0 -and $FailOnMismatch) { throw 'reconciliation found differences from the oracle' }
