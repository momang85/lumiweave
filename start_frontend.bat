@echo off
title AI Agent Hub Frontend (port 3000)
cd /d "%~dp0"

echo ========================================
echo   AI Agent Hub - Frontend
echo   http://localhost:3000
echo ========================================
echo.

cd builder\frontend

REM Ensure Node.js is accessible
set "PATH=D:\Node;%PATH%"

echo Starting Vite...
call npx vite --host 0.0.0.0 --port 3000
pause
