@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   LumiWeave — 一键发布到 GitHub
echo ========================================
echo.

echo [1/6] 检查前端构建...
if not exist "builder\frontend\dist\index.html" (
    echo   构建前端...
    cd builder\frontend
    call npm install 2>nul
    call npx vite build 2>nul
    cd ..\..
)

echo [2/6] 复制到 static...
if not exist "builder\backend\static" mkdir "builder\backend\static"
xcopy /E /Y "builder\frontend\dist\*" "builder\backend\static\" >nul

echo [3/6] git add...
git add -A

echo [4/6] git commit...
git commit -m "v0.4.0: LumiWeave first release"

echo [5/6] git remote...
git remote remove origin 2>nul
git remote add origin https://github.com/momang85/lumiweave.git

echo [6/6] git push...
git branch -M main
git push -u origin main --force

echo.
echo ========================================
echo   完成！访问 github.com/momang85/lumiweave
echo ========================================
pause
