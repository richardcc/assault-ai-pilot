# Ejecucion Externa de Curriculum (Independiente del IDE / Antigravity)
$ErrorActionPreference = "Stop"
$Repo = "C:\repos\python\assault"
Set-Location $Repo



# 2. Activar venv de Python si existe
$venvPython = Join-Path $Repo ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $env:PATH = (Join-Path $Repo ".venv\Scripts") + ";" + $env:PATH
    Write-Host "[Python] Usando entorno virtual: $venvPython" -ForegroundColor Green
} else {
    Write-Host "[Python] Usando Python del sistema" -ForegroundColor Yellow
}

$env:MLFLOW_TRACKING_URI = "http://127.0.0.1:5001"

# 3. Buscar el ultimo checkpoint valido en runs_curriculum
$ckpt = Get-ChildItem -Path (Join-Path $Repo "runs_curriculum") -Recurse -File -Filter "*.pt" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "efficientzero_v2_.+\\checkpoints\\(final|iter_\d+)\.pt$" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$ckptPath = if ($ckpt) { $ckpt.FullName } else { "" }

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  CURRICULUM EXTERNO (FASE 8 / FINAL: phase6_self_only_stabilize)" -ForegroundColor Cyan
Write-Host "  Repositorio: $Repo" -ForegroundColor Gray
Write-Host "  Checkpoint inicial: $ckptPath" -ForegroundColor Magenta
Write-Host "=================================================================" -ForegroundColor Cyan

$scriptArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $Repo "curriculums\common\run_dynamic_gated_curriculum.ps1"),
    "-CurriculumYaml", (Join-Path $Repo "curriculums\self_vs_self_vs_random_2scenarios_v1\curriculum.yaml"),
    "-StartPhase", "phase6_self_only_stabilize",
    "-StopOnPhaseError"
)

if (-not [string]::IsNullOrWhiteSpace($ckptPath) -and (Test-Path $ckptPath)) {
    $scriptArgs += @("-ExplicitStartCheckpoint", $ckptPath)
}

& powershell.exe @scriptArgs
