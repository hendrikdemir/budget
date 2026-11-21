# Builds dist\Budget\Budget.exe and dist\Budget-windows.zip. Run on Windows with Python 3 installed.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .venv-build)) { python -m venv .venv-build }
# PyInstaller's ready-made bootloader is shared with lots of malware, so antivirus often flags it.
# Compiling our own (from the source package, which needs the C compiler from Visual Studio)
# avoids most of those false alarms.
$env:PYINSTALLER_COMPILE_BOOTLOADER = "1"
.venv-build\Scripts\pip install --verbose --force-reinstall --no-cache-dir --no-binary pyinstaller pyinstaller
.venv-build\Scripts\pip install --quiet pywebview certifi
.venv-build\Scripts\pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\Budget-windows.spec

if (Test-Path dist\Budget-windows.zip) { Remove-Item dist\Budget-windows.zip }
Compress-Archive -Path dist\Budget -DestinationPath dist\Budget-windows.zip
Write-Host "Built dist\Budget\Budget.exe and dist\Budget-windows.zip"
