!define PRODUCT_NAME "iOS 云打印服务器"
!define PRODUCT_VERSION "1.6.0"
!define PRODUCT_EXE "iOSPrintServer.exe"
!define UPDATE_SERVICE_EXE "update_service.exe"
!define SOURCE_DIR "dist\iOSPrintServer"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\iOSPrintServer-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\iOSPrintServer"

RequestExecutionLevel admin

Section "Install"
  SetOutPath "$INSTDIR"

  # 递归复制整个程序目录
  File /r "${SOURCE_DIR}\*.*"

  # Start menu shortcut
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"

  # Desktop shortcut
  CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"

  # Registry autostart
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}" "$INSTDIR\${PRODUCT_EXE}"

  # Register update service
  ExecWait '"$INSTDIR\${UPDATE_SERVICE_EXE}" --install'

  # Uninstall registration
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${PRODUCT_NAME}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "Developer"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1

  WriteUninstaller "$INSTDIR\uninst.exe"

  # Run after install
  ExecShell "" "$INSTDIR\${PRODUCT_EXE}"
SectionEnd

Section "Uninstall"
  # Kill running processes before uninstalling
  ExecWait 'taskkill /F /IM "${PRODUCT_EXE}"'
  ExecWait 'taskkill /F /IM "${UPDATE_SERVICE_EXE}"'

  # Ask user if they want to remove personal data
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同时删除用户数据（配置文件、数据库、日志等）？" IDNO skip_data

  # Remove user data directories
  RMDir /r "$APPDATA\iOSPrintServer"
  RMDir /r "$LOCALAPPDATA\iOSPrintServer"

  skip_data:
  Delete "$SMPROGRAMS\${PRODUCT_NAME}.lnk"
  Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${PRODUCT_NAME}"
  DeleteRegKey HKLM "${UNINSTALL_KEY}"

  # Unregister update service
  ExecWait '"$INSTDIR\${UPDATE_SERVICE_EXE}" --uninstall'

  RMDir /r "$INSTDIR"
SectionEnd
