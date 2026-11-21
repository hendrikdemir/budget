# Temporary helper: which static files does Defender flag, and from which line on?
$ErrorActionPreference = "Continue"
$mp = Get-ChildItem "C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
if (-not $mp) { $mp = Get-Item "$env:ProgramFiles\Windows Defender\MpCmdRun.exe" }
Write-Host "Scanner: $($mp.FullName)"
Get-MpComputerStatus | Select-Object AMServiceEnabled, AntivirusEnabled, AntivirusSignatureVersion, AntivirusSignatureLastUpdated | Format-List
& $mp.FullName -SignatureUpdate | Out-Host
Get-MpComputerStatus | Select-Object AntivirusSignatureVersion | Format-List

$work = Join-Path $env:RUNNER_TEMP "scan"
New-Item -ItemType Directory -Force $work | Out-Null

function Flagged([string]$path) {
  $out = & $mp.FullName -Scan -ScanType 3 -File $path -DisableRemediation 2>&1 | Out-String
  return ($out -match "found \d+ threats" -and $out -notmatch "found no threats") -or ($LASTEXITCODE -eq 2)
}

# Control: the harmless EICAR test string must be detected, or the scanner isn't working.
$eicar = Join-Path $work "eicar.txt"
Set-Content -NoNewline $eicar ('X5O!P%@AP[4\PZX54(P^)7CC)7}$' + 'EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*')
Write-Host "Control (EICAR) flagged: $(Flagged $eicar)"

$flagged = @()
foreach ($f in Get-ChildItem static -Recurse -File) {
  $copy = Join-Path $work $f.Name
  Copy-Item $f.FullName $copy
  $hit = Flagged $copy
  Write-Host ("{0,-6} {1}" -f $hit, $f.FullName.Substring($PWD.Path.Length + 1))
  if ($hit) { $flagged += $f }
}

# For each flagged file: the shortest start of the file that is still flagged.
foreach ($f in $flagged) {
  $lines = Get-Content $f.FullName
  $lo = 1; $hi = $lines.Count
  $part = Join-Path $work ("part-" + $f.Name)
  while ($lo -lt $hi) {
    $mid = [int][math]::Floor(($lo + $hi) / 2)
    Set-Content $part $lines[0..($mid - 1)]
    if (Flagged $part) { $hi = $mid } else { $lo = $mid + 1 }
  }
  Write-Host "== $($f.Name): flagged once line $hi is included =="
  $from = [math]::Max(0, $hi - 4)
  $lines[$from..($hi - 1)] | ForEach-Object { Write-Host "   $_" }
}
Get-MpThreatDetection | Select-Object -First 5 | Format-List | Out-Host
