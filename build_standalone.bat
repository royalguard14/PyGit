@echo off
setlocal
cd /d "%~dp0"

set "OUTDIR=%~dp0pc\client\standalone"

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo ==========================================
echo   BUILD STANDALONE PISONET TEST EXE
echo ==========================================
echo.

python -m PyInstaller ^
 --noconsole ^
 --onefile ^
 --clean ^
 --name PisoNetStandalone ^
 --hidden-import=keyboard ^
 --hidden-import=pycaw ^
 --hidden-import=comtypes ^
 --hidden-import=PIL ^
 --distpath "%OUTDIR%" ^
 --workpath "%~dp0build\PisoNetStandalone" ^
 --specpath "%~dp0build\PisoNetStandalone" ^
 "%~dp0pc\client\PisoNetStandalone.py"

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

if not exist "%OUTDIR%\PisoNetStandalone.exe" (
    echo.
    echo EXE WAS NOT CREATED.
    pause
    exit /b 1
)

echo.
echo BUILD SUCCESSFUL:
echo %OUTDIR%\PisoNetStandalone.exe
echo.
pause
