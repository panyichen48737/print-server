!define PRODUCT_NAME "iOS 云打印服务器"
!define PRODUCT_VERSION "1.6.0"
!define PRODUCT_EXE "iOSPrintServer.exe"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "${PRODUCT_NAME}-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$LOCALAPPDATA\iOSPrintServer"

Section "Install"
  SetOutPath "$INSTDIR"
  File "${PRODUCT_EXE}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"
  WriteUninstaller "$INSTDIR\uninst.exe"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}.lnk"
  Delete "$INSTDIR\${PRODUCT_EXE}"
  RMDir "$INSTDIR"
SectionEnd