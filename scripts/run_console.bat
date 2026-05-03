@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo ============================================
echo  iOS 云打印服务器 - 控制台
echo ============================================
echo.

if not exist "logs" mkdir logs

python -m console
