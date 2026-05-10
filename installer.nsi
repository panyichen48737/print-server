!define PRODUCT_NAME "iOSPrintServer"
!define PRODUCT_VERSION "2.4.1"
!define PRODUCT_EXE "iOSPrintServer.exe"
!define UPDATE_SERVICE_EXE "update_service.exe"
!define SOURCE_DIR "dist\iOSPrintServer"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

; ── Modern UI 2 ──
!include "MUI2.nsh"

; ── 界面设置 ──
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\iOSPrintServer-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\iOSPrintServer"
RequestExecutionLevel admin

; MUI2 中文字体
!define MUI_FONT_DEFAULT "Microsoft YaHei"
!define MUI_FONT_HEADER "Microsoft YaHei"
!define MUI_LANGDLL_ALWAYSSHOW
!define MUI_LANGDLL_REGISTRY_ROOT "HKLM"
!define MUI_LANGDLL_REGISTRY_KEY "${UNINSTALL_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "Installer Language"

; ── 品牌图片 ──
; 将 150x57 像素的 bmp 放在 installer.nsi 同目录，放置于 ${NSISDIR}/Contrib/Graphics/ 或自行提供
; !define MUI_HEADERIMAGE
; !define MUI_HEADERIMAGE_BITMAP "header.bmp"
; !define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"

; ── 页面 ──
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; ── 语言 ──
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ── 安装页面文本 ──
LangString INST_TITLE ${LANG_SIMPCHINESE} "正在安装 ${PRODUCT_NAME} ${PRODUCT_VERSION}"
LangString INST_TITLE ${LANG_ENGLISH} "Installing ${PRODUCT_NAME} ${PRODUCT_VERSION}"
LangString INST_SUBTITLE ${LANG_SIMPCHINESE} "请等待安装程序完成..."
LangString INST_SUBTITLE ${LANG_ENGLISH} "Please wait while the installer completes..."
LangString UNINST_TITLE ${LANG_SIMPCHINESE} "正在卸载 ${PRODUCT_NAME}"
LangString UNINST_TITLE ${LANG_ENGLISH} "Uninstalling ${PRODUCT_NAME}"
LangString UNINST_SUBTITLE ${LANG_SIMPCHINESE} "请等待卸载程序完成..."
LangString UNINST_SUBTITLE ${LANG_ENGLISH} "Please wait while the uninstaller completes..."

; ── 安装 ──
Section "Install"
  ; Kill running processes before updating
  ExecWait 'taskkill /F /IM "${PRODUCT_EXE}"'
  ExecWait 'taskkill /F /IM "${UPDATE_SERVICE_EXE}"'

  SetOutPath "$INSTDIR"

  ; 递归复制整个程序目录
  File /r "${SOURCE_DIR}\*.*"

  ; Start menu shortcut
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"

  ; Desktop shortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"

  ; Registry autostart
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\${PRODUCT_EXE}"

  ; Register update service
  ExecWait '"$INSTDIR\${UPDATE_SERVICE_EXE}" --install'

  ; Uninstall registration
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "TechFlow Solutions Inc."
  WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\uninst.exe"

  ; Run after install
  ExecShell "" "$INSTDIR\${PRODUCT_EXE}"
SectionEnd

; ── 卸载 ──
Section "Uninstall"
  ; Kill running processes before uninstalling
  ExecWait 'taskkill /F /IM "${PRODUCT_EXE}"'
  ExecWait 'taskkill /F /IM "${UPDATE_SERVICE_EXE}"'

  ; Ask user if they want to remove personal data
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据（配置文件、数据库、日志等）？" IDNO skip_data

  ; Remove user data directories
  RMDir /r "$APPDATA\iOSPrintServer"
  RMDir /r "$LOCALAPPDATA\iOSPrintServer"

  skip_data:
  Delete "$SMPROGRAMS\${PRODUCT_NAME}.lnk"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  DeleteRegKey HKLM "${UNINSTALL_KEY}"

  ; Unregister update service
  ExecWait '"$INSTDIR\${UPDATE_SERVICE_EXE}" --uninstall'

  RMDir /r "$INSTDIR"
SectionEnd