@echo off
chcp 65001 >nul
title 论辩 Wiki 启动器
cd /d "%~dp0\..\.."

echo ========================================
echo  论辩 Wiki · 启动中...
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.12+
    pause
    exit /b 1
)

:: 检查 PostgreSQL
pg_isready >nul 2>&1
if errorlevel 1 (
    echo [提示] PostgreSQL 未运行，正在尝试启动...
    net start postgresql-x64-16 2>nul
    timeout /t 3 /nobreak >nul
)

:: 启动后端（同时提供前端页面）
echo [1/2] 启动后端服务 (http://0.0.0.0:8000)...
start "论辩Wiki-后端" cmd /k "cd backend && set DATABASE_URL=postgresql+psycopg://lingdebate:lingdebate@localhost:5432/lingdebate && ..\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000"

echo.
echo ========================================
echo  启动完成！
echo.
echo  本机访问: http://localhost:8000
echo  局域网访问: http://你的电脑IP:8000
echo  （在 cmd 输入 ipconfig 查看 IPv4 地址）
echo.
echo  账号: demo-owner / demo1234
echo ========================================
echo.
pause
