# ===============================
# Git auto-publish script
# Añade todo, commitea con fecha/hora y hace push
# ===============================

# Salir si hay errores
$ErrorActionPreference = "Stop"

# Obtener fecha y hora actual
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "🔍 Comprobando estado del repositorio..." -ForegroundColor Cyan

# Comprobar que estamos en un repo git
if (-not (Test-Path ".git")) {
    Write-Host "❌ ERROR: Esta carpeta no es un repositorio Git (.git no existe)" -ForegroundColor Red
    exit 1
}

git status

Write-Host "➕ Añadiendo todos los cambios..." -ForegroundColor Cyan
git add .

# Comprobar si hay algo para commitear
$changes = git status --porcelain
if (-not $changes) {
    Write-Host "✅ No hay cambios nuevos. Nada que publicar." -ForegroundColor Green
    exit 0
}

# Mensaje del commit
$commitMessage = "Auto commit $timestamp"

Write-Host "📝 Creando commit: $commitMessage" -ForegroundColor Cyan
git commit -m "$commitMessage"

Write-Host "🚀 Publicando en GitHub..." -ForegroundColor Cyan
git push

Write-Host "✅ Publicación completada correctamente." -ForegroundColor Green
Write-Host "📅 Commit: $commitMessage" -ForegroundColor Green