# generate_uml.ps1
# Generates PlantUML package diagram and renders SVG + PDF

$ProjectRoot = Get-Location
$Folders = @("assault_model", "assault_sim", "assault_training")
$OutDir = "$ProjectRoot\docs\uml"
$BaseName = "architecture_uml"
$PumlFile = "$OutDir\$BaseName.puml"

Write-Host "Generating UML for:" $Folders -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$uml = @()
$uml += "@startuml"
$uml += "skinparam packageStyle rectangle"
$uml += ""

foreach ($folder in $Folders) {
    if (Test-Path "$ProjectRoot\$folder") {
        $uml += "package $folder {"
        $uml += "}"
        $uml += ""
    }
}

$uml += "assault_training --> assault_sim"
$uml += "assault_sim --> assault_model"
$uml += "@enduml"

