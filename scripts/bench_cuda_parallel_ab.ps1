param(
  [string]$Repo = "C:\repos\python\assault",
  [string]$BaseConfig = "assault_bench/configs/benchmark_config.yaml",
  [int]$CudaWorkers = 2,
  [int]$SeedCount = 5
)

$ErrorActionPreference = "Stop"
Set-Location $Repo

$py = Join-Path $Repo ".venv\Scripts\python.exe"
if (!(Test-Path $py)) { throw "No encuentro python del venv en $py" }

$runTs = Get-Date -Format "yyyyMMdd_HHmmss"
$outDir = Join-Path $Repo ("_artifacts\bench_ab_" + $runTs)
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$configA = Join-Path $outDir "bench_seq.yaml"
$configB = Join-Path $outDir "bench_cuda_parallel.yaml"

# Genera dos configs desde el base:
# A) Secuencial en CUDA (workers=1)
# B) Paralelo CUDA opt-in (workers=$CudaWorkers)
$base = Get-Content -Raw -Path $BaseConfig

$cfgA = $base `
  -replace '(?m)^(\s*num_workers:\s*).*$','$1 1' `
  -replace '(?m)^(\s*allow_cuda_parallel:\s*).*$','$1 false'

$cfgB = $base `
  -replace '(?m)^(\s*num_workers:\s*).*$',('$1 ' + [string]$CudaWorkers) `
  -replace '(?m)^(\s*allow_cuda_parallel:\s*).*$','$1 true' `
  -replace '(?m)^(\s*cuda_parallel_workers:\s*).*$',('$1 ' + [string]$CudaWorkers)

if ($SeedCount -lt 1) { $SeedCount = 1 }
$seedList = (1..$SeedCount) -join ", "
$cfgA = $cfgA -replace '(?m)^(\s*seeds:\s*)\[[^\]]*\]\s*$',('$1[' + $seedList + ']')
$cfgB = $cfgB -replace '(?m)^(\s*seeds:\s*)\[[^\]]*\]\s*$',('$1[' + $seedList + ']')

Set-Content -Path $configA -Value $cfgA -Encoding UTF8
Set-Content -Path $configB -Value $cfgB -Encoding UTF8

$logA = Join-Path $outDir "A_seq.log"
$logB = Join-Path $outDir "B_parallel.log"

Write-Host "== RUN A (CUDA secuencial) ==" -ForegroundColor Cyan
$prevNativePref = $null
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -Scope Global -ErrorAction SilentlyContinue) {
  $prevNativePref = $Global:PSNativeCommandUseErrorActionPreference
  $Global:PSNativeCommandUseErrorActionPreference = $false
}
& cmd /c "`"$py`" -m assault_bench.runner --config `"$configA`" 2>&1" | Tee-Object -FilePath $logA
if ($LASTEXITCODE -ne 0) {
  throw "RUN A failed with exit code $LASTEXITCODE"
}

Write-Host "== RUN B (CUDA paralelo) ==" -ForegroundColor Cyan
& cmd /c "`"$py`" -m assault_bench.runner --config `"$configB`" 2>&1" | Tee-Object -FilePath $logB
if ($LASTEXITCODE -ne 0) {
  throw "RUN B failed with exit code $LASTEXITCODE"
}
if ($null -ne $prevNativePref) {
  $Global:PSNativeCommandUseErrorActionPreference = $prevNativePref
}

# Extrae resumen final (wall_s y eps) de la línea [Bench] completed
$lineA = Select-String -Path $logA -Pattern "\[Bench\] completed" | Select-Object -Last 1
$lineB = Select-String -Path $logB -Pattern "\[Bench\] completed" | Select-Object -Last 1

function Parse-Metric([string]$line, [string]$key) {
  if ($line -match ($key + "=([0-9]+(\.[0-9]+)?)")) { return [double]$Matches[1] }
  return $null
}

$wallA = Parse-Metric $lineA.Line "wall_s"
$wallB = Parse-Metric $lineB.Line "wall_s"
$epsA  = Parse-Metric $lineA.Line "eps"
$epsB  = Parse-Metric $lineB.Line "eps"

Write-Host ""
Write-Host "===== RESUMEN A/B =====" -ForegroundColor Yellow
Write-Host ("A (seq) line: " + $lineA.Line)
Write-Host ("B (par) line: " + $lineB.Line)

if ($wallA -ne $null -and $wallB -ne $null -and $wallA -gt 0) {
  $speedup = $wallA / $wallB
  Write-Host ("Wall time A: {0:N2}s | B: {1:N2}s | speedup: {2:N2}x" -f $wallA, $wallB, $speedup)
}
if ($epsA -ne $null -and $epsB -ne $null -and $epsA -gt 0) {
  $gain = (($epsB - $epsA) / $epsA) * 100.0
  Write-Host ("EPS A: {0:N3} | B: {1:N3} | delta: {2:N1}%" -f $epsA, $epsB, $gain)
}

Write-Host ""
Write-Host ("Logs y configs en: " + $outDir) -ForegroundColor Green
