@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  安装 Windows 服务 - iOS 云打印服务器
echo ============================================
echo.

:: 检查 nssm 是否可用
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 nssm，请先安装: https://nssm.cc/download
    echo.
    echo 或者手动注册服务：
    echo   sc create iOSPrintServer binPath="%~dp0main.py" start=auto
    pause
    exit /b 1
)

set "PYTHON_PATH=python"
set "SCRIPT_PATH=%~dp0main.py"

echo 安装服务: iOSPrintServer
echo 显示名称: iOS 云打印服务器
echo Python: %PYTHON_PATH%
echo 脚本: %SCRIPT_PATH%
echo.

nssm install iOSPrintServer "%PYTHON_PATH%" "%SCRIPT_PATH%"
if %errorlevel% equ 0 (
    nssm set iOSPrintServer DisplayName "iOS 云打印服务器"
    nssm set iOSPrintServer Description "iOS 设备通过 Scriptable 脚本提交打印任务到本地打印机"
    nssm set iOSPrintServer AppStdout "%~dp0logs\nssm_stdout.log"
    nssm set iOSPrintServer AppStderr "%~dp0logs\nssm_stderr.log"
    nssm set iOSPrintServer AppRotateFiles 1
    nssm set iOSPrintServer AppRotateSeconds 86400
    nssm set iOSPrintServer Start SERVICE_AUTO_START
    echo.
    echo 安装成功！服务已设为自动启动。
    echo.
    echo 启动服务: nssm start iOSPrintServer
    echo 停止服务: nssm stop iOSPrintServer
    echo 查看状态: nssm status iOSPrintServer
) else (
    echo.
    echo 安装失败。
)

pause
