@echo off
setlocal
cd /d "%~dp0"
echo =========================================================================
echo  ASSAULT UNIT ^& FORMATION EDITOR (PORT 8780)
echo =========================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_unit_editor.ps1" -OpenWindow
