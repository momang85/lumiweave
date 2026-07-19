@echo off
chcp 65001 >nul
title LumiWeave

echo ========================================
echo   LumiWeave — AI Agent 协作工作台
echo ========================================
echo.

docker compose up -d

echo.
echo ========================================
echo   启动成功！
echo   浏览器打开: http://localhost:8000
echo ========================================
echo.
echo 管理命令:
echo   查看日志: docker compose logs -f
echo   停止服务: docker compose down
echo.
pause
