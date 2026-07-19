@echo off
title AI Agent Hub Backend (port 8000)
cd /d "%~dp0"

echo ========================================
echo   AI Agent Hub - Backend
echo   http://localhost:8000
echo   http://localhost:8000/docs
echo ========================================
echo.

cd builder\backend
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
python main.py
pause
