Name "WKS Storyboard Template"
RequestExecutionLevel user
OutFile "wks_storyboard_setup.exe"
Unicode True

!include "MUI2.nsh"
!define APP "Blender (v2.93)"
!define MUI_ABORTWARNING
!define UNINSTALL_EXE "$INSTDIR\uninstaller.exe"
!define UNINSTALL_LNK "$SMPROGRAMS\Uninstall WKS_Storyboard.lnk"
!define TEMPLATE_DIR "$APPDATA\Blender Foundation\Blender\2.93\scripts\startup\bl_app_templates_user"
!define ADDON_DIR "$APPDATA\Blender Foundation\Blender\2.93\scripts\addons"

InstallDir "${TEMPLATE_DIR}\WKS_Storyboard"

!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of Warnakala Studios' Storyboard Application Template for ${APP}.$\r$\n$\r$\n$_CLICK"
!define MUI_FINISHPAGE_TEXT "$(^NameDA) has been installed on your computer (and an uninstaller placed in the Start Menu).$\r$\n$\r$\nYou can now access it in ${APP}'s New File menu."
!define MUI_FINISHPAGE_NOAUTOCLOSE
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section
  SetOutPath $INSTDIR
  File /r /x .git WKS_Storyboard\*.*
  WriteUninstaller "${UNINSTALL_EXE}"
  CreateShortcut "${UNINSTALL_LNK}" "${UNINSTALL_EXE}"
SectionEnd

Section "Uninstall"
  Delete "${UNINSTALL_LNK}"
  Delete "${UNINSTALL_EXE}"
  RMDir /r $INSTDIR
  RMDir "${TEMPLATE_DIR}"
SectionEnd

Section "Start Menu "
SectionEnd
