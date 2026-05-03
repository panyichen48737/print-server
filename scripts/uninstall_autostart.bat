@echo off
chcp 65001 >nul
echo ============================================
echo  卸载开机自启 - iOS 云打印控制台
echo ============================================
echo.

reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "iOSPrintConsole" /f >nul 2>&1

if %errorlevel% equ 0 (
    echo 已删除开机自启。
) else (
    echo 未找到开机自启项或删除失败。
)

pause
