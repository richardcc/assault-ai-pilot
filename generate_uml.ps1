# ============================================
# AUTOMATIC UML GENERATION FOR PYTHON PROJECT
# ============================================

$ProjectRoot = Get-Location
$OutDir      = "$ProjectRoot\docs\uml"
$PlantUmlJar = "$OutDir\plantuml.jar"

$SrcFolders = @(
    "assault_model",
    "assault_sim",
    "assault_training"
)

Write-Host "=== UML DOCUMENTATION GENERATOR ===" -ForegroundColor Cyan

$env:PYTHONPATH = $ProjectRoot

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "Generating UML with pyreverse..." -ForegroundColor Cyan

pyreverse `
    -o plantuml `
    -k -a `
    -d $OutDir `
    -p architecture `
    $SrcFolders `
    2>$OutDir\pyreverse_errors.log

# Ensure PlantUML
if (!(Test-Path $PlantUmlJar)) {
    Invoke-WebRequest `
        -Uri "https://github.com/plantuml/plantuml/releases/latest/download/plantuml.jar" `
        -OutFile $PlantUmlJar
}

Write-Host "Generating SVG diagrams..." -ForegroundColor Cyan
java -jar $PlantUmlJar -tsvg "$OutDir\*.plantuml"

# ---- PDF via Inkscape ----
$inkscape = Get-Command inkscape -ErrorAction SilentlyContinue
if ($inkscape) {
    Write-Host "Converting SVG to PDF with Inkscape..." -ForegroundColor Cyan
    Get-ChildItem $OutDir -Filter *.svg | ForEach-Object {
        $pdf = [System.IO.Path]::ChangeExtension($_.FullName, ".pdf")
        inkscape $_.FullName --export-filename=$pdf
    }
} else {
    Write-Host "WARNING: Inkscape not found. SVG generated, PDF skipped." -ForegroundColor Yellow
}

Write-Host "UML documentation ready in: $OutDir" -ForegroundColor Green