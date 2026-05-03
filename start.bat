@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  iOS 云打印服务器 - 开发模式
echo ============================================
echo.

if not exist "logs" mkdir logs

python main.py

if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请检查 Python 环境和依赖。
    pause
)
