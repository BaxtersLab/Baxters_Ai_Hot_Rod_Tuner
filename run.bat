@echo off
title Hot Rod Tuner
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
echo Starting Hot Rod Tuner on http://127.0.0.1:8080 ...
python run_server.py
if %errorlevel% neq 0 (
    echo.
    echo Failed to start. Make sure Python 3.10+ is installed
    echo and run HRT_installer.bat first to install dependencies.
    pause
)
