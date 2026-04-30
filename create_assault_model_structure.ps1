# ==========================================
# Assault – Canonical Model Structure Creator
# ==========================================

Write-Host "Creating Assault canonical model structure..." -ForegroundColor Cyan
$ErrorActionPreference = "Stop"

$ROOT = Get-Location

# Root model folder
$MODEL_ROOT = Join-Path $ROOT "assault_model"

# Define folder structure
$folders = @(
    "$MODEL_ROOT",
    "$MODEL_ROOT/core",
    "$MODEL_ROOT/units",
    "$MODEL_ROOT/map",
    "$MODEL_ROOT/actions",
    "$MODEL_ROOT/rulesets"
)

# Create folders
foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
        Write-Host "Created folder: $folder"
    } else {
        Write-Host "Folder already exists: $folder" -ForegroundColor Yellow
    }
}

# Define files to scaffold
$files = @{
    "core/game_state.py"        = "# Canonical GameState model`n"
    "core/scenario.py"          = "# Scenario definition (engine entry point)`n"
    "core/replay.py"            = "# Replay / trace of game states`n"

    "units/unit_type.py"        = "# Static unit type definition`n"
    "units/unit_instance.py"    = "# Runtime unit instance`n"
    "units/attributes.py"       = "# Unit attributes and stats`n"

    "map/map.py"                = "# Final assembled map model`n"
    "map/map_piece.py"          = "# Reusable map piece definition`n"
    "map/hex.py"                = "# Hex tile definition`n"
    "map/terrain.py"            = "# Terrain semantic model`n"

    "actions/action.py"         = "# Abstract action definition`n"
    "actions/movement.py"       = "# Movement actions`n"
    "actions/combat.py"         = "# Combat actions`n"
    "actions/resolution.py"     = "# Action resolution contracts`n"

    "rulesets/ruleset.py"       = "# Ruleset interface / specification`n"
}

# Create files with placeholders
foreach ($relativePath in $files.Keys) {
    $fullPath = Join-Path $MODEL_ROOT $relativePath
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType File -Path $fullPath | Out-Null
        Set-Content -Path $fullPath -Value $files[$relativePath]
        Write-Host "Created file: $fullPath"
    } else {
        Write-Host "File already exists: $fullPath" -ForegroundColor Yellow
    }
}

# Create __init__.py files in all subfolders
Get-ChildItem $MODEL_ROOT -Directory -Recurse | ForEach-Object {
    $initFile = Join-Path $_.FullName "__init__.py"
    if (-not (Test-Path $initFile)) {
        New-Item -ItemType File -Path $initFile | Out-Null
        Write-Host "Created __init__.py in $($_.FullName)"
    }
}

# Also create root __init__.py
$rootInit = Join-Path $MODEL_ROOT "__init__.py"
if (-not (Test-Path $rootInit)) {
    New-Item -ItemType File -Path $rootInit | Out-Null
    Write-Host "Created root __init__.py"
}

Write-Host "Assault canonical model structure created successfully." -ForegroundColor Green