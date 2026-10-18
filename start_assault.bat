@echo off
setlocal
cd /d "%~dp0"
echo =========================================================================
echo  INICIANDO PLATAFORMA ASSAULT (WINDOWS TERMINAL CON MULTIPESTANAS)
echo =========================================================================
echo  - Reporting Viewer V2   : http://127.0.0.1:8777
echo  - Unit Catalog Editor   : http://127.0.0.1:8780
echo  - Backend API FastAPI   : http://127.0.0.1:8001
echo  - Frontend Simulador    : http://localhost:5173
echo  - Terminales de Dev     : Consolas interactivas con .venv activo
echo =========================================================================

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all_environments.ps1"
