# ==========================================
# Assault – Incremental assault_sim Generator
# ==========================================

Write-Host "Incrementally preparing assault_sim..." -ForegroundColor Cyan
$ErrorActionPreference = "Stop"

$ROOT = Get-Location
$SIM_ROOT = Join-Path $ROOT "assault_sim"

# -------------------------
# 1. Ensure base structure
# -------------------------
$folders = @(
    "$SIM_ROOT",
    "$SIM_ROOT/adapters",
    "$SIM_ROOT/heuristics",
    "$SIM_ROOT/runners",
    "$SIM_ROOT/rewards",
    "$SIM_ROOT/analysis",
    "$SIM_ROOT/series",
    "$SIM_ROOT/session",
    "$SIM_ROOT/explanation"
)

foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
        Write-Host "Created folder: $folder"
    }
}

# -------------------------
# 2. Ensure key files exist
# -------------------------
$files = @{
    "sim_env.py"        = "# Simulation environment (step / reset / run loop)`n"
    "action_catalog.py" = "# Discrete action catalog -> model Action mapping`n"
}

foreach ($file in $files.Keys) {
    $fullPath = Join-Path $SIM_ROOT $file
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType File -Path $fullPath | Out-Null
        Set-Content -Path $fullPath -Value $files[$file]
        Write-Host "Created file: $fullPath"
    }
}

# -------------------------
# 3. Move existing folders (if present)
# -------------------------
$moveMap = @{
    "analysis"     = "analysis"
    "rewards"      = "rewards"
    "series"       = "series"
    "session"      = "session"
    "explanation"  = "explanation"
}

foreach ($src in $moveMap.Keys) {
    $srcPath = Join-Path $ROOT $src
    $dstPath = Join-Path $SIM_ROOT $moveMap[$src]

    if (Test-Path $srcPath) {
        if (-not (Test-Path $dstPath)) {
            Move-Item -Path $srcPath -Destination $dstPath
            Write-Host "Moved '$src' -> assault_sim\$($moveMap[$src])"
        } else {
            Write-Host "Folder '$src' already moved, skipping"
        }
    }
}

# -------------------------
# 4. Move root-level sim files (if present)
# -------------------------
$rootFiles = @(
    "policies.py",
    "rl_runner.py",
    "replay.py"
)

foreach ($file in $rootFiles) {
    $srcPath = Join-Path $ROOT $file
    $dstPath = Join-Path $SIM_ROOT $file

    if (Test-Path $srcPath) {
        if (-not (Test-Path $dstPath)) {
            Move-Item -Path $srcPath -Destination $dstPath
            Write-Host "Moved file: $file -> assault_sim"
        }
    }
}

# -------------------------
# 5. Ensure __init__.py everywhere
# -------------------------
Get-ChildItem $SIM_ROOT -Directory -Recurse | ForEach-Object {
    $initFile = Join-Path $_.FullName "__init__.py"
    if (-not (Test-Path $initFile)) {
        New-Item -ItemType File -Path $initFile | Out-Null
    }
}
New-Item -ItemType File -Path (Join-Path $SIM_ROOT "__init__.py") -Force | Out-Null

Write-Host "assault_sim incremental setup complete." -ForegroundColor Green
