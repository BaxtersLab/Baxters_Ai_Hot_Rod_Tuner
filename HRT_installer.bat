@echo off
setlocal enabledelayedexpansion
title Hot Rod Tuner — Installer
echo ============================================================
echo   Baxter's AI Hot Rod Tuner — Installer
echo ============================================================
echo.

:: ── Locate project root (same folder as this .bat) ──
set "HRT_ROOT=%~dp0"
cd /d "%HRT_ROOT%"

:: ── 1. Check for Python ──
echo [1/4] Checking Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   Python not found on PATH.
    echo   Please install Python 3.10+ from https://python.org
    echo   and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>nul') do set "PYVER=%%v"
echo   OK: !PYVER!
echo.

:: ── 2. Install pip dependencies ──
echo [2/4] Installing dependencies...
python -m pip install --quiet --upgrade pip 2>nul
python -m pip install --quiet -r "%HRT_ROOT%requirements.txt" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   WARNING: Some packages may have failed. Checking key deps...
    python -c "import fastapi, uvicorn, psutil, pydantic" 2>nul
    if %errorlevel% neq 0 (
        echo   ERROR: Core dependencies missing. Check output above.
        pause
        exit /b 1
    )
    echo   Core dependencies OK (fastapi, uvicorn, psutil, pydantic).
)
echo   Dependencies installed.
echo.

:: ── 3. Quick smoke test ──
echo [3/4] Running smoke test...
set "PYTHONPATH=%HRT_ROOT%src"
python -c "from hotrod_tuner.app import app; print('  OK: FastAPI app loads')" 2>&1
if %errorlevel% neq 0 (
    echo   ERROR: App failed to load. Check output above.
    pause
    exit /b 1
)
python -m pytest "%HRT_ROOT%tests" -q 2>&1
echo.

:: ── 4. Create Start Menu shortcut + launcher ──
echo [4/4] Creating launcher and Start Menu shortcut...

:: Create a small launcher script
(
echo @echo off
echo cd /d "%HRT_ROOT%"
echo set "PYTHONPATH=%HRT_ROOT%src"
echo set "HOTROD_PORT=8090"
echo echo Starting Hot Rod Tuner on http://127.0.0.1:8090 ...
echo start "" "http://127.0.0.1:8090"
echo python run_server.py
) > "%HRT_ROOT%HRT_launch.bat"

set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Baxters Office Suite"
if not exist "%STARTMENU%" mkdir "%STARTMENU%"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTMENU%\Hot Rod Tuner.lnk'); $s.TargetPath = '%HRT_ROOT%HRT_launch.bat'; $s.WorkingDirectory = '%HRT_ROOT%'; $s.Description = 'Baxters AI Hot Rod Tuner - Hardware Monitor'; $s.Save()"
if %errorlevel% equ 0 (
    echo   OK: Shortcut created in Start Menu ^> Baxters Office Suite
) else (
    echo   WARNING: Shortcut creation failed. Use HRT_launch.bat directly.
)

echo.
echo ============================================================
echo   Installation complete!
echo   Run: HRT_launch.bat   (or Start Menu shortcut)
echo   GUI: http://127.0.0.1:8090
echo ============================================================
echo.
pause
