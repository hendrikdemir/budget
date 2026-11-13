# Builds dist\Budget\Budget.exe and dist\Budget-windows.zip. Run on Windows with Python 3 installed.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .venv-build)) { python -m venv .venv-build }
.venv-build\Scripts\pip install --quiet pyinstaller pywebview certifi
.venv-build\Scripts\pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\Budget-windows.spec

if (Test-Path dist\Budget-windows.zip) { Remove-Item dist\Budget-windows.zip }
Compress-Archive -Path dist\Budget -DestinationPath dist\Budget-windows.zip
Write-Host "Built dist\Budget\Budget.exe and dist\Budget-windows.zip"
