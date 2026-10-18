@echo off
cd /d "C:\repos\python\assault"
echo =========================================================================
echo  INICIANDO EJECUCION EXTERNA DEL CURRICULUM (DESACOPLADO DE ANTIGRAVITY)
echo =========================================================================

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\repos\python\assault\run_external.ps1"

pause
