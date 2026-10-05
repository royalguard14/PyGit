$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pyinstaller pywin32

$dist = Join-Path $PSScriptRoot "release"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null

python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "SufyanPisoNetTimer" --hidden-import=win32timezone "PisoNetTimer.py"
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "SufyanPisoNetTimerService" --hidden-import=win32timezone "service.py"
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "uninstall_helper" "uninstall_helper.py"

Copy-Item "dist\SufyanPisoNetTimer.exe" $dist
Copy-Item "dist\SufyanPisoNetTimerService.exe" $dist
Copy-Item "dist\uninstall_helper.exe" $dist
Copy-Item "sufyan\*" $dist -Force

Write-Host "Release files prepared in: $dist"

Copy-Item "install.ps1" $dist
