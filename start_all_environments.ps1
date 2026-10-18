<#
.SYNOPSIS
    Levanta todos los entornos del proyecto Assault en pestañas de PowerShell (Windows Terminal)
    y deja 2 pestañas adicionales en la raíz del proyecto con el entorno virtual (.venv) activado.

.DESCRIPTION
    Abre una ventana de Windows Terminal con 6 pestañas organizadas:
      1. Reporting Viewer V2 (Puerto 8777) - Visor de Modelos y Currículum
      2. SB3 Eval Viewer (Puerto 8765)     - Visor histórico de evaluaciones
      3. Backend API Simulador (Puerto 8001) - FastAPI / Uvicorn
      4. Frontend Simulador (Puerto 5173)   - Vite Dev Server (assault_ai_ui)
      5. Terminal Dev 1 (venv)             - Consola interactiva con .venv activo
      6. Terminal Dev 2 (venv)             - Consola interactiva con .venv activo

    Si Windows Terminal (wt.exe) no está instalado o se pasa -SeparateWindows,
    los procesos se abrirán en ventanas independientes de PowerShell.

.EXAMPLE
    .\start_all_environments.ps1
    .\start_all_environments.ps1 -SeparateWindows
#>

[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\repos\python\assault",
    [switch]$SeparateWindows,
    [switch]$SkipLegacySB3
)

$ErrorActionPreference = "Stop"

# Resolver ruta canónica
if (-not (Test-Path $RepoRoot)) {
    $RepoRoot = $PSScriptRoot
}
$RepoRoot = (Resolve-Path $RepoRoot).Path
$UiRoot = Join-Path $RepoRoot "assault_ai_ui"
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Iniciando Entornos de Desarrollo - Assault Engine       " -ForegroundColor Yellow
Write-Host "  Raiz del repositorio: $RepoRoot" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

# Verificaciones previas
if (-not (Test-Path $VenvActivate)) {
    Write-Warning "No se encontro el entorno virtual en '$VenvActivate'. Por favor verifica la instalacion."
}
if (-not (Test-Path (Join-Path $UiRoot "node_modules"))) {
    Write-Warning "No se encontro 'node_modules' en '$UiRoot'. Si el frontend falla, ejecuta 'npm install' en esa carpeta."
}

# Definir comandos de cada pestaña
$cmdReporting = "Write-Host '========================================' -ForegroundColor Cyan; " +
    "Write-Host ' [1/6] Visor de Modelos y Curriculum   ' -ForegroundColor Yellow; " +
    "Write-Host ' URL: http://127.0.0.1:8777/            ' -ForegroundColor Green; " +
    "Write-Host '========================================' -ForegroundColor Cyan; " +
    "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    ".\scripts\run_curriculum_reporting_viewer.ps1 -Dev"

$cmdSb3Viewer = "Write-Host '========================================' -ForegroundColor Cyan; " +
    "Write-Host ' [2/6] Visor Historico SB3 Eval        ' -ForegroundColor Yellow; " +
    "Write-Host ' URL: http://127.0.0.1:8765/            ' -ForegroundColor Green; " +
    "Write-Host '========================================' -ForegroundColor Cyan; " +
    "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    "python scripts/sb3_eval_viewer.py --host 127.0.0.1 --port 8765"

$cmdBackend = "Write-Host '========================================' -ForegroundColor Cyan; " +
    "Write-Host ' [3/6] Backend API Simulador (FastAPI) ' -ForegroundColor Yellow; " +
    "Write-Host ' URL: http://127.0.0.1:8001/            ' -ForegroundColor Green; " +
    "Write-Host ' Docs: http://127.0.0.1:8001/docs       ' -ForegroundColor Gray; " +
    "Write-Host '========================================' -ForegroundColor Cyan; " +
    "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    "python -m uvicorn assault_backend.main:app --host 127.0.0.1 --port 8001 --reload"

$cmdUnitEditor = "Write-Host '========================================' -ForegroundColor Cyan; " +
    "Write-Host ' Unit Catalog Editor & Approval Workflow' -ForegroundColor Yellow; " +
    "Write-Host ' URL: http://127.0.0.1:8780/            ' -ForegroundColor Green; " +
    "Write-Host '========================================' -ForegroundColor Cyan; " +
    "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    "python tools/unit_editor_server.py --port 8780"

$cmdFrontend = "Write-Host '========================================' -ForegroundColor Cyan; " +
    "Write-Host ' Frontend Simulador Tactico (Vite)     ' -ForegroundColor Yellow; " +
    "Write-Host ' URL: http://localhost:5173/            ' -ForegroundColor Green; " +
    "Write-Host '========================================' -ForegroundColor Cyan; " +
    "npm run dev -- --host"

$cmdShell1 = "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    "Clear-Host; " +
    "Write-Host '===================================================' -ForegroundColor Green; " +
    "Write-Host ' Terminal Dev 1 - Entorno .venv Activo             ' -ForegroundColor Yellow; " +
    "Write-Host ' Carpeta: $RepoRoot' -ForegroundColor Gray; " +
    "Write-Host ' Listo para ejecutar comandos y scripts             ' -ForegroundColor Cyan; " +
    "Write-Host '===================================================' -ForegroundColor Green; " +
    "python --version"

$cmdShell2 = "if (Test-Path '$VenvActivate') { . '$VenvActivate' }; " +
    "Clear-Host; " +
    "Write-Host '===================================================' -ForegroundColor Green; " +
    "Write-Host ' Terminal Dev 2 - Entorno .venv Activo             ' -ForegroundColor Yellow; " +
    "Write-Host ' Carpeta: $RepoRoot' -ForegroundColor Gray; " +
    "Write-Host ' Listo para ejecutar comandos y scripts             ' -ForegroundColor Cyan; " +
    "Write-Host '===================================================' -ForegroundColor Green; " +
    "python --version"

# Lista de especificaciones de pestañas
$tabSpecs = @(
    @{ Title = "Reporting-8777";   Dir = $RepoRoot; Cmd = $cmdReporting },
    @{ Title = "UnitEditor-8780";  Dir = $RepoRoot; Cmd = $cmdUnitEditor }
)

if (-not $SkipLegacySB3) {
    $tabSpecs += @{ Title = "SB3-Viewer-8765"; Dir = $RepoRoot; Cmd = $cmdSb3Viewer }
}

$tabSpecs += @(
    @{ Title = "Backend-8001";     Dir = $RepoRoot; Cmd = $cmdBackend },
    @{ Title = "TacticalUI-5173";  Dir = $UiRoot;   Cmd = $cmdFrontend },
    @{ Title = "Dev-1 (venv)";     Dir = $RepoRoot; Cmd = $cmdShell1 },
    @{ Title = "Dev-2 (venv)";     Dir = $RepoRoot; Cmd = $cmdShell2 }
)

# Comprobar si wt.exe está disponible y no se forzó ventanas separadas
$hasWt = (Get-Command wt.exe -ErrorAction SilentlyContinue) -ne $null

if ($hasWt -and -not $SeparateWindows) {
    Write-Host "Abriendo ventana con pestanas en Windows Terminal..." -ForegroundColor Cyan

    $tabCommands = @()
    for ($i = 0; $i -lt $tabSpecs.Count; $i++) {
        $spec = $tabSpecs[$i]
        $title = $spec.Title
        $dir = $spec.Dir
        $cmd = $spec.Cmd

        if ($i -eq 0) {
            # Primera pestaña (abre la nueva ventana con -w new)
            $tabCommands += "-w new --title `"$title`" -d `"$dir`" powershell.exe -NoExit -ExecutionPolicy Bypass -Command `"$cmd`""
        } else {
            # Pestañas subsiguientes
            $tabCommands += "new-tab --title `"$title`" -d `"$dir`" powershell.exe -NoExit -ExecutionPolicy Bypass -Command `"$cmd`""
        }
    }

    $wtFullArgs = $tabCommands -join " ; "
    Start-Process "wt.exe" -ArgumentList $wtFullArgs
    Write-Host "Ventana de Windows Terminal lanzada exitosamente con $($tabSpecs.Count) pestanas." -ForegroundColor Green
} else {
    Write-Host "Lanzando $($tabSpecs.Count) ventanas independientes de PowerShell..." -ForegroundColor Cyan

    foreach ($spec in $tabSpecs) {
        $title = $spec.Title
        $dir = $spec.Dir
        $cmd = $spec.Cmd
        $wrapped = "`$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $cmd"

        Start-Process "powershell.exe" -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $wrapped
    }
    Write-Host "Ventanas de PowerShell lanzadas correctamente." -ForegroundColor Green
}
