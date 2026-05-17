; iOSPrintServer Inno Setup 安装脚本
; 使用 Inno Setup 6.x + VCL Style 皮肤

#define MyAppName "iOSPrintServer"
#define MyAppVersion "3.10.2"
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

[Languages]
Name: "chinesesimplified"; MessagesFile: "installer_ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\iOSPrintServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "certs\cert.pem"; DestDir: "{app}\certs"; Flags: ignoreversion
Source: "certs\key.pem"; DestDir: "{app}\certs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName} --tray"; Flags: uninsdeletevalue

[Run]
; 先 kill 旧进程（更新时）
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden skipifdoesntexist
Filename: "taskkill"; Parameters: "/F /IM {#MyUpdateServiceExe}"; Flags: runhidden skipifdoesntexist
; 注册更新服务
Filename: "{app}\{#MyUpdateServiceExe}"; Parameters: "--install"; Flags: runhidden
; 安装完成后启动（以原始用户身份运行，确保 GUI 显示在用户桌面）
Filename: "{app}\{#MyAppExeName}"; WorkingDir: {app}; Description: "启动 {#MyAppName}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[Code]

var
  DeleteUserData: Boolean;

// 卸载开始时最先执行，返回值 True 继续卸载，False 取消卸载
function InitializeUninstall: Boolean;
begin
  Result := True;
  DeleteUserData := MsgBox('是否同时删除用户数据？' + #13#10
    + #13#10 + '包括：配置文件、数据库、日志、上传文件等' + #13#10
    + #13#10 + '建议保留：重新安装后无需重新配置',
    mbConfirmation, MB_YESNO) = mrYes;
end;

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
    if DeleteUserData then
    begin
      DelTree(ExpandConstant('{userappdata}\iOSPrintServer'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\iOSPrintServer'), True, True, True);
      DelTree(ExpandConstant('{commonappdata}\iOSPrintServer'), True, True, True);
    end;
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
