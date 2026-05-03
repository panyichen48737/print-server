@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  卸载 Windows 服务 - iOS 云打印服务器
echo ============================================
echo.

nssm stop iOSPrintServer >nul 2>&1
nssm remove iOSPrintServer confirm >nul 2>&1

if %errorlevel% equ 0 (
    echo 服务 iOSPrintServer 已卸载。
) else (
    echo 尝试 sc delete 方式卸载...
    sc stop iOSPrintServer >nul 2>&1
    sc delete iOSPrintServer >nul 2>&1
    if %errorlevel% equ 0 (
        echo 服务 iOSPrintServer 已卸载。
    ) else (
        echo 未找到服务或卸载失败。
        echo 请确认服务名称: iOSPrintServer
    )
)

pause
