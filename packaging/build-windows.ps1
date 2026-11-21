# Builds dist\Budget\Budget.exe, the installer dist\Budget-setup.exe and dist\Budget-windows.zip.
# Run on Windows with Python 3 and Inno Setup 6 installed (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .venv-build)) { python -m venv .venv-build }
# PyInstaller's ready-made bootloader is shared with lots of malware, so antivirus often flags it.
# Compiling our own (from the source package, which needs the C compiler from Visual Studio)
# avoids most of those false alarms.
$env:PYINSTALLER_COMPILE_BOOTLOADER = "1"
.venv-build\Scripts\pip install --quiet --force-reinstall --no-cache-dir --no-binary pyinstaller pyinstaller
.venv-build\Scripts\pip install --quiet pywebview certifi
.venv-build\Scripts\pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\Budget-windows.spec
Copy-Item packaging\Budget.exe.config dist\Budget\Budget.exe.config

if (Test-Path dist\Budget-windows.zip) { Remove-Item dist\Budget-windows.zip }
Compress-Archive -Path dist\Budget -DestinationPath dist\Budget-windows.zip
$version = .venv-build\Scripts\python -c "from app import VERSION; print(VERSION)"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 isn't installed. Install it with: winget install JRSoftware.InnoSetup" }
& $iscc /Q "/DVersion=$version" packaging\Budget.iss
if ($LASTEXITCODE -ne 0) { throw "Building the installer failed" }

Write-Host "Built dist\Budget\Budget.exe, dist\Budget-setup.exe and dist\Budget-windows.zip (version $version)"
