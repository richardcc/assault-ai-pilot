@echo off
setlocal
cd /d "%~dp0"

echo ================================================================================
echo  ASSAULT - VP ACCELERATION CURRICULUM (START FROM SCRATCH - TABULA RASA)
echo ================================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_vp_curriculum_from_scratch.ps1"

pause
