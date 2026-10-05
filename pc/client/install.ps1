#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$InstallDir = "C:\sufyan"
$AppExe = Join-Path $InstallDir "SufyanPisoNetTimer.exe"
$ServiceExe = Join-Path $InstallDir "SufyanPisoNetTimerService.exe"
$UninstallerExe = Join-Path $InstallDir "uninstall_helper.exe"

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot "SufyanPisoNetTimer.exe") $AppExe -Force
Copy-Item (Join-Path $PSScriptRoot "SufyanPisoNetTimerService.exe") $ServiceExe -Force
Copy-Item (Join-Path $PSScriptRoot "uninstall_helper.exe") $UninstallerExe -Force
Copy-Item (Join-Path $PSScriptRoot "detail.json") (Join-Path $InstallDir "detail.json") -Force
Copy-Item (Join-Path $PSScriptRoot "*.jpg") $InstallDir -Force

netsh advfirewall firewall delete rule name="Sufyan PisoNetTimer TCP 5000" 2>$null
netsh advfirewall firewall delete rule name="Sufyan PisoNetTimer UDP 5051" 2>$null

netsh advfirewall firewall add rule name="Sufyan PisoNetTimer TCP 5000" dir=in action=allow protocol=TCP localport=5000
netsh advfirewall firewall add rule name="Sufyan PisoNetTimer UDP 5051" dir=in action=allow protocol=UDP localport=5051

& $ServiceExe install
& $ServiceExe start

Write-Host "Sufyan PisoNetTimer installed successfully in $InstallDir"
Write-Host "Firewall rules added for TCP 5000 and UDP 5051."
