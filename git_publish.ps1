# ===============================
# Git auto-publish script
# Añade todo, commitea con fecha/hora y hace push
# ===============================

$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "Comprobando estado del repositorio..."

if (-not (Test-Path ".git")) {
    Write-Host "ERROR: Esta carpeta no es un repositorio Git (.git no existe)" -ForegroundColor Red
    exit 1
}

git status

Write-Host "Añadiendo todos los cambios..."
git add .

$changes = git status --porcelain
if (-not $changes) {
    Write-Host "No hay cambios nuevos. Nada que publicar." -ForegroundColor Green
    exit 0
}

$commitMessage = "Auto commit $timestamp"

Write-Host "Creando commit: $commitMessage"
git commit -m "$commitMessage"

Write-Host "Publicando en GitHub..."
git push

Write-Host "Publicación completada correctamente." -ForegroundColor Green
Write-Host "Commit: $commitMessage" -ForegroundColor Green
