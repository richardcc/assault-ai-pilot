Write-Host "== Creating assault-web application structure =="

# Root web app folder
$webRoot = "assault-web"

# Create folders
$folders = @(
    "$webRoot",
    "$webRoot\data",
    "$webRoot\assets",
    "$webRoot\assets\units",
    "$webRoot\assets\maps"
)

foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder | Out-Null
        Write-Host "Created folder: $folder"
    } else {
        Write-Host "Folder already exists: $folder"
    }
}

# Create base files if they don't exist
$files = @(
    "$webRoot\index.html",
    "$webRoot\style.css",
    "$webRoot\app.js",
    "$webRoot\data\replay_demo.json",
    "$webRoot\data\unit_defs.json",
    "$webRoot\data\brigade_defs.json"
)

foreach ($file in $files) {
    if (-not (Test-Path $file)) {
        New-Item -ItemType File -Path $file | Out-Null
        Write-Host "Created file: $file"
    } else {
        Write-Host "File already exists: $file"
    }
}

Write-Host "== assault-web structure ready =="

# Optional: show git status
if (Test-Path ".git") {
    Write-Host ""
    Write-Host "== Git status =="
    git status
} else {
    Write-Host "Warning: this folder is not a git repository."
}