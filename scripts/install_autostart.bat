@echo off
chcp 65001 >nul
echo ============================================
echo  安装开机自启 - iOS 云打印控制台
echo ============================================
echo.

cd /d "%~dp0.."
set "SCRIPT_PATH=%~dp0run_console.bat"

:: 写入 HKCU Run 键（用户级，无需管理员）
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "iOSPrintConsole" /t REG_SZ /d "\"%SCRIPT_PATH%\"" /f >nul

if %errorlevel% equ 0 (
    echo 安装成功！
    echo 下次登录时自动启动控制台。
    echo 脚本路径: %SCRIPT_PATH%
    echo.
    echo 手动运行: %SCRIPT_PATH%
    echo.
) else (
    echo 安装失败。
)

pause
