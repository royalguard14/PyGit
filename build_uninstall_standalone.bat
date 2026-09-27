@echo off
setlocal
cd /d "%~dp0"

set "OUTDIR=%~dp0pc\client\standalone"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo ==========================================
echo   BUILD STANDALONE UNINSTALLER
echo ==========================================
echo.

python -m PyInstaller ^
 --noconsole ^
 --onefile ^
 --clean ^
 --name PisoNetStandaloneUninstall ^
 --distpath "%OUTDIR%" ^
 --workpath "%~dp0build\PisoNetStandaloneUninstall" ^
 --specpath "%~dp0build\PisoNetStandaloneUninstall" ^
 "%~dp0pc\client\uninstall_standalone.py"

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

if not exist "%OUTDIR%\PisoNetStandaloneUninstall.exe" (
    echo.
    echo UNINSTALLER EXE WAS NOT CREATED.
    pause
    exit /b 1
)

echo.
echo BUILD SUCCESSFUL:
echo %OUTDIR%\PisoNetStandaloneUninstall.exe
echo.
pause
