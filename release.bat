```bat
@echo off
setlocal EnableExtensions

title PisoNet Release Builder
cd /d "%~dp0"

echo.
echo ==========================================
echo       PISONET RELEASE BUILDER
echo ==========================================
echo.

REM ==========================================
REM 1. PULL LATEST GITHUB VERSION
REM ==========================================
echo [1/5] Pulling latest changes from GitHub...
echo.

git pull origin main

if errorlevel 1 (
    echo.
    echo ERROR: git pull failed.
    echo Fix the Git problem first.
    pause
    exit /b 1
)

echo.
echo Git pull successful.
echo.

REM ==========================================
REM 2. BUILD PISONET.EXE
REM ==========================================
echo [2/5] Building PisoNet.exe...
echo.

python -m PyInstaller ^
 --noconsole ^
 --onefile ^
 --clean ^
 --name PisoNet ^
 --hidden-import=tkinter ^
 --hidden-import=ntplib ^
 --hidden-import=pycaw ^
 --hidden-import=comtypes ^
 --hidden-import=PIL ^
 --distpath "%~dp0pc\client" ^
 "%~dp0pc\client\PisoNetTimer.py"

if errorlevel 1 (
    echo.
    echo ERROR: PisoNet.exe build failed.
    pause
    exit /b 1
)

if not exist "%~dp0pc\client\PisoNet.exe" (
    echo.
    echo ERROR: PisoNet.exe was not created.
    pause
    exit /b 1
)

echo.
echo PisoNet.exe created successfully.
echo.

rem  ==========================================
rem  3. BUILD UNINSTALLER
rem  ==========================================
rem echo [3/5] Building PisoNetUninstall.exe...
rem echo.

rem python -m PyInstaller ^
rem  --noconsole ^
rem  --onefile ^
rem  --clean ^
rem  --name PisoNetUninstall ^
rem  --distpath "%~dp0pc\client" ^
rem  "%~dp0pc\client\uninstall.py"

rem if errorlevel 1 (
rem     echo.
rem     echo ERROR: PisoNetUninstall.exe build failed.
rem     pause
rem     exit /b 1
rem )

rem if not exist "%~dp0pc\client\PisoNetUninstall.exe" (
rem     echo.
rem     echo ERROR: PisoNetUninstall.exe was not created.
rem     pause
rem     exit /b 1
rem )

rem echo.
rem echo PisoNetUninstall.exe created successfully.
rem echo.

REM ==========================================
REM 4. GIT ADD + COMMIT
REM ==========================================
echo [4/5] Preparing Git commit...
echo.

git add -f pc/client/PisoNet.exe
git add -f pc/client/PisoNetUninstall.exe
git add pc/client/PisoNetTimer.py
git add pc/client/control.json
git add pc/client/uninstall.py

if errorlevel 1 (
    echo.
    echo ERROR: git add failed.
    pause
    exit /b 1
)

git diff --cached --quiet

if %errorlevel%==0 (
    echo.
    echo No changes to commit.
    goto PUSH
)

git commit -m "Release PisoNet client"

if errorlevel 1 (
    echo.
    echo ERROR: git commit failed.
    pause
    exit /b 1
)

REM ==========================================
REM 5. PUSH
REM ==========================================
:PUSH

echo.
echo [5/5] Pushing release to GitHub...
echo.

git push origin main

if errorlevel 1 (
    echo.
    echo ==========================================
    echo PUSH FAILED
    echo ==========================================
    echo.
    echo No automatic merge was performed.
    echo Check the Git error above.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo       RELEASE SUCCESSFUL!
echo ==========================================
echo.
echo GitHub has the new PisoNet.exe.
echo.
echo Existing installed clients can now
echo detect the new version and self-update.
echo.
pause
```
