<#
.SYNOPSIS
    Levanta todos los entornos del proyecto Assault en pestañas de PowerShell (Windows Terminal)
    y deja 2 pestañas adicionales en la raíz del proyecto con el entorno virtual (.venv) activado.

.DESCRIPTION
    Abre una ventana de Windows Terminal con 6 pestañas organizadas:
      1. Reporting Viewer V2 (Puerto 8777) - Visor de Modelos y Currículum
      2. Unit & Formation Editor (Puerto 8780) - Editor de Unidades y Formaciones
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
    [bool]$SkipLegacySB3 = $true
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

# Rutas de scripts lanzadores dedicados (sin punto y coma interno para evitar problemas con wt.exe)
$scriptReporting  = Join-Path $RepoRoot "scripts\run_curriculum_reporting_viewer.ps1"
$scriptUnitEditor = Join-Path $RepoRoot "scripts\run_unit_editor.ps1"
$scriptSb3Viewer  = Join-Path $RepoRoot "scripts\run_sb3_viewer.ps1"
$scriptBackend    = Join-Path $RepoRoot "scripts\run_backend.ps1"
$scriptFrontend   = Join-Path $RepoRoot "scripts\run_frontend.ps1"
$scriptDev        = Join-Path $RepoRoot "scripts\run_dev_terminal.ps1"

# Lista de especificaciones de pestañas
$tabSpecs = @(
    @{ Title = "Reporting-8777";   Dir = $RepoRoot; File = $scriptReporting;  Args = @("-Dev") },
    @{ Title = "UnitEditor-8780";  Dir = $RepoRoot; File = $scriptUnitEditor; Args = @() }
)

if (-not $SkipLegacySB3) {
    $tabSpecs += @{ Title = "SB3-Viewer-8765"; Dir = $RepoRoot; File = $scriptSb3Viewer; Args = @() }
}

$tabSpecs += @(
    @{ Title = "Backend-8001";     Dir = $RepoRoot; File = $scriptBackend;    Args = @() },
    @{ Title = "TacticalUI-5173";  Dir = $UiRoot;   File = $scriptFrontend;   Args = @() },
    @{ Title = "Dev-1 (venv)";     Dir = $RepoRoot; File = $scriptDev;        Args = @("-Index", "1") },
    @{ Title = "Dev-2 (venv)";     Dir = $RepoRoot; File = $scriptDev;        Args = @("-Index", "2") }
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
        $file = $spec.File
        $argsStr = if ($spec.Args.Count -gt 0) { " " + ($spec.Args -join " ") } else { "" }

        # Invocacion powershell limpia sin puntos y coma internos
        $subCmd = "powershell.exe -NoExit -ExecutionPolicy Bypass -File `"$file`"$argsStr"

        if ($i -eq 0) {
            # Primera pestaña (abre la nueva ventana con -w new)
            $tabCommands += "-w new --title `"$title`" -d `"$dir`" $subCmd"
        } else {
            # Pestañas subsiguientes
            $tabCommands += "new-tab --title `"$title`" -d `"$dir`" $subCmd"
        }
    }

    $wtFullArgs = $tabCommands -join " ; "
    Start-Process "wt.exe" -ArgumentList $wtFullArgs
    Write-Host "Ventana de Windows Terminal lanzada exitosamente con $($tabSpecs.Count) pestanas." -ForegroundColor Green
    Start-Sleep -Seconds 1
    Start-Process "http://127.0.0.1:8780/"
} else {
    Write-Host "Lanzando $($tabSpecs.Count) ventanas independientes de PowerShell..." -ForegroundColor Cyan

    foreach ($spec in $tabSpecs) {
        $title = $spec.Title
        $dir = $spec.Dir
        $file = $spec.File
        $argsList = @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", $file) + $spec.Args

        Start-Process "powershell.exe" -ArgumentList $argsList -WorkingDirectory $dir
    }
    Write-Host "Ventanas de PowerShell lanzadas correctamente." -ForegroundColor Green
    Start-Sleep -Seconds 1
    Start-Process "http://127.0.0.1:8780/"
}
