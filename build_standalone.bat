@echo off
setlocal
cd /d "%~dp0"

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
 --distpath "%~dp0pc\client" ^
 "%~dp0pc\client\PisoNetStandalone.py"

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

if not exist "%~dp0pc\client\PisoNetStandalone.exe" (
    echo.
    echo EXE WAS NOT CREATED.
    pause
    exit /b 1
)

echo.
echo BUILD SUCCESSFUL:
echo %~dp0pc\client\PisoNetStandalone.exe
echo.
pause
