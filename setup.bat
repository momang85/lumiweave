@echo off
setlocal EnableDelayedExpansion

REM UTF-8 support check (Windows 7+ compatible)
chcp 65001 >nul 2>&1
if errorlevel 1 chcp 437 >nul

echo ============================================
echo AI Agent Hub - Setup
echo ============================================
echo.

REM --- 1. Check Python ---
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
python -c "import sys; v=sys.version_info; exit(0 if v>=(3,10) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required.
    pause
    exit /b 1
)
echo [OK] Python detected.
echo.

REM --- 2. Check Node.js ---
echo [2/4] Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)
echo [OK] Node.js detected.
echo.

REM --- 3. Check file structure ---
echo [3/4] Checking project files...
set "MISSING=0"
if not exist "requirements-all.txt" (
    echo [WARN] requirements-all.txt missing
    set "MISSING=1"
)
if not exist "builder\backend\main.py" (
    echo [WARN] backend\main.py missing
    set "MISSING=1"
)
if not exist "builder\frontend\package.json" (
    echo [WARN] frontend\package.json missing
    set "MISSING=1"
)
if not exist "agents" (
    echo [WARN] agents\ directory missing
    set "MISSING=1"
)
if %MISSING%==1 (
    echo [ERROR] Required files missing. Please run this from the project root.
    pause
    exit /b 1
)
echo [OK] All files present.
echo.

REM --- 4. Install Python deps ---
echo [4/4] Installing Python dependencies...
python -m pip install --upgrade pip -q
python -m pip install -r requirements-all.txt
if errorlevel 1 (
    echo [ERROR] Python packages install failed.
    pause
    exit /b 1
)
echo [OK] Python packages installed.
echo.

REM --- 5. Install Node.js deps ---
echo [5/4] Installing frontend dependencies...
cd builder\frontend
if errorlevel 1 (
    echo [ERROR] Cannot enter builder\frontend directory
    pause
    exit /b 1
)
call npm install
if errorlevel 1 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
)
cd ..\..
echo [OK] Frontend dependencies installed.
echo.

REM --- 6. Check API keys (optional) ---
echo ============================================
echo Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Configure API key in Settings panel
echo   2. Or set environment variable:
echo      set DEEPSEEK_API_KEY=sk-xxxx
echo.
echo Start backend:  cd builder\backend ^&^& python main.py
echo Start frontend: cd builder\frontend ^&^& npm run dev
echo.
pause
