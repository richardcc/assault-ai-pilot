# -------------------------------
# Create assault-viewer structure
# -------------------------------

$root = "assault-viewer"

$folders = @(
    "$root/assets/maps",
    "$root/assets/counters",
    "$root/viewer",
    "$root/data"
)

Write-Host "Creating assault-viewer project structure..."

# Create root folder
New-Item -ItemType Directory -Path $root -Force | Out-Null

# Create subfolders
foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
}

# Create placeholder files
$files = @(
    "$root/main.py",
    "$root/README.md",
    "$root/viewer/grid.py",
    "$root/viewer/renderer.py",
    "$root/viewer/replay.py",
    "$root/viewer/ui.py",
    "$root/data/sample_replay.json"
)

foreach ($file in $files) {
    if (-Not (Test-Path $file)) {
        New-Item -ItemType File -Path $file | Out-Null
    }
}

Write-Host "assault-viewer structure created successfully."