# ================================
# Assault-Env Documentation Build
# ================================

Write-Host "=== Building Assault-Env Documentation ===" -ForegroundColor Cyan
$ErrorActionPreference = "Stop"

# Base paths (script lives inside docs/)
$DOCS_DIR = $PSScriptRoot
$BUILD_DIR = Join-Path $DOCS_DIR "_build"

# Mermaid source and static output
$DIAGRAMS_SRC = Join-Path $DOCS_DIR "diagrams"
$STATIC_DIR   = Join-Path $DOCS_DIR "_static"
$DIAGRAMS_DST = Join-Path $STATIC_DIR "diagrams"

# ------------------------------------------------
# Step 1: Clean previous build
# ------------------------------------------------
Write-Host "Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path $BUILD_DIR) {
    Remove-Item -Recurse -Force $BUILD_DIR
}

# ------------------------------------------------
# Step 2: Render Mermaid diagrams to _static
# ------------------------------------------------
if (Test-Path $DIAGRAMS_SRC) {
    Write-Host "Rendering Mermaid diagrams..." -ForegroundColor Yellow

    if (-not (Test-Path $DIAGRAMS_DST)) {
        New-Item -ItemType Directory -Path $DIAGRAMS_DST -Force | Out-Null
    }

    Get-ChildItem $DIAGRAMS_SRC -Filter *.mmd | ForEach-Object {
        $outputFile = Join-Path $DIAGRAMS_DST "$($_.BaseName).svg"
        Write-Host "  - $($_.Name) -> _static/diagrams/$($_.BaseName).svg"
        npx mmdc -i $_.FullName -o $outputFile
    }
} else {
    Write-Host "No Mermaid source folder found (docs/diagrams). Skipping diagram rendering." -ForegroundColor DarkGray
}

# ------------------------------------------------
# Step 3: Build Sphinx documentation
# ------------------------------------------------
Write-Host "Running Sphinx build..." -ForegroundColor Yellow
Set-Location $DOCS_DIR
sphinx-build -b html . _build/html

# ------------------------------------------------
# Done
# ------------------------------------------------
Write-Host "=== Documentation build complete ===" -ForegroundColor Green
Write-Host "HTML output in: docs/_build/html"