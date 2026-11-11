$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pyinstaller pywin32

$release = Join-Path $PSScriptRoot "release"
$payload = Join-Path $PSScriptRoot ".installer_payload"
$work = Join-Path $PSScriptRoot ".build_work"

# The release folder contains only the single installer distributed to clients.
foreach ($path in @($release, $payload, $work)) {
    if (Test-Path $path) { Remove-Item $path -Recurse -Force }
}
New-Item -ItemType Directory -Path $release, $payload, $work | Out-Null

try {
    python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "SufyanPisoNetTimer" --distpath $payload --workpath (Join-Path $work "app") --specpath $work --hidden-import=win32timezone "PisoNetTimer.py"
    if ($LASTEXITCODE -ne 0) { throw "Failed to build PisoNetTimer application." }

    python -m PyInstaller --noconfirm --clean --onefile --console --name "SufyanPisoNetTimerService" --distpath $payload --workpath (Join-Path $work "service") --specpath $work --hidden-import=servicemanager --hidden-import=win32timezone "service.py"
    if ($LASTEXITCODE -ne 0) { throw "Failed to build PisoNetTimer Windows service." }

    python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "uninstall_helper" --distpath $payload --workpath (Join-Path $work "uninstaller") --specpath $work "uninstall_helper.py"
    if ($LASTEXITCODE -ne 0) { throw "Failed to build uninstaller helper." }

    Copy-Item "sufyan\*" $payload -Force

    python -m PyInstaller --noconfirm --clean --onefile --noconsole --uac-admin --name "PisoNetSetup" --distpath $release --workpath (Join-Path $work "installer") --specpath $work --add-binary "$payload\SufyanPisoNetTimer.exe;." --add-binary "$payload\SufyanPisoNetTimerService.exe;." --add-binary "$payload\uninstall_helper.exe;." --add-data "$payload\detail.json;." --add-data "$payload\wallpapersden.com_valorant-hd-gaming_1920x1080.jpg;." "installer.py"
    if ($LASTEXITCODE -ne 0) { throw "Failed to build PisoNetSetup.exe." }

    Write-Host ""
    Write-Host "Build completed. Final release contains one file:"
    Write-Host (Join-Path $release "PisoNetSetup.exe")
}
finally {
    if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
    if (Test-Path $work) { Remove-Item $work -Recurse -Force }
}
