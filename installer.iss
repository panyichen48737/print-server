; iOSPrintServer Inno Setup 安装脚本
; 使用 Inno Setup 6.x + VCL Style 皮肤

#define MyAppName "iOSPrintServer"
#define MyAppVersion "2.6.5"
#define MyAppExeName "iOSPrintServer.exe"
#define MyUpdateServiceExe "update_service.exe"
#define MyAppPublisher "TechFlow Solutions Inc."
#define MyAppURL "https://github.com/panyichen48737/print-server"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={commonpf64}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=dist
OutputBaseFilename=iOSPrintServer-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; VCL Style 皮肤（可选，自动使用 if installed）
; 从 https://github.com/VclStyles/Inno-Setup-VCL-Style 获取
; #define VCLStyle "Dark"
; #include "VCLStyles.iss"

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer_ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Files]
Source: "dist\iOSPrintServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName} --tray"; Flags: uninsdeletevalue

[Run]
; 先 kill 旧进程（更新时）
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden skipifdoesntexist
Filename: "taskkill"; Parameters: "/F /IM {#MyUpdateServiceExe}"; Flags: runhidden skipifdoesntexist
; 注册更新服务
Filename: "{app}\{#MyUpdateServiceExe}"; Parameters: "--install"; Flags: runhidden
; 安装完成后启动
Filename: "{app}\{#MyAppExeName}"; WorkingDir: {app}; Description: "启动 {#MyAppName}"; Flags: postinstall nowait skipifsilent

[Code]

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    Exec('taskkill', '/F /IM iOSPrintServer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill', '/F /IM update_service.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('taskkill', '/F /IM iOSPrintServer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill', '/F /IM update_service.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\update_service.exe'), '--uninstall', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('是否同时删除用户数据（配置文件、数据库、日志等）？', mbConfirmation, MB_YESNO) = mrYes then
    begin
      DelTree(ExpandConstant('{userappdata}\iOSPrintServer'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\iOSPrintServer'), True, True, True);
      DelTree(ExpandConstant('{commonappdata}\iOSPrintServer'), True, True, True);
    end;
  end;
end;