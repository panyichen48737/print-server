@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  iOS 云打印服务器 - 开发模式
echo ============================================
echo.

echo 启动后台守护进程（控制台关闭后仍运行）...
echo 管理命令:
echo   python -m console --status    查看状态
echo   python -m console --stop      停止服务
echo   python -m console --start     启动服务
echo.
python -m console --start
echo.

if %errorlevel% neq 0 (
    echo 启动失败，请检查 Python 环境和依赖。
    pause
)
