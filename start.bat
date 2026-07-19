@echo off
chcp 65001 >nul
title LumiWeave

echo ========================================
echo   LumiWeave — AI Agent 协作工作台
echo ========================================
echo.

:: 检查 Docker
where docker >nul 2>&1
if %errorlevel% equ 0 (
    echo [Docker] 启动中...
    docker compose up -d
    goto :done
)

:: 检查 Python
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo [Python] 安装依赖...
    pip install -q fastapi uvicorn pyyaml pydantic openai httpx 2>nul
    echo [Python] 启动服务...
    start http://localhost:8000
    python -c "import os;os.chdir('builder/backend');import uvicorn;uvicorn.run('main:app',host='0.0.0.0',port=8000)"
    goto :done
)

echo [ERROR] 未找到 Docker 或 Python，请先安装
pause
exit /b 1

:done
echo.
echo ========================================
echo   浏览器打开: http://localhost:8000
echo ========================================
pause
