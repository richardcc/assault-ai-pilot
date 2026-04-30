# ============================================================
# publish-docs.ps1
#
# Build Sphinx documentation and publish it to GitHub Pages
# using a dedicated git worktree.
#
# SAFETY FEATURES:
# - Automatically switches to main branch if needed
# - Refuses to run if tracked files are dirty
# - Validates every critical step
# - Aborts immediately on errors
# ============================================================

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------

$REPO_DIR  = Get-Location
$HTML_DIR  = Join-Path $REPO_DIR "docs\_build\html"
$PAGES_DIR = Join-Path $REPO_DIR "..\assault-ai-pilot-pages"

Write-Host "==> Starting documentation publish process..."

# ------------------------------------------------------------
# Git sanity checks
# ------------------------------------------------------------

Write-Host "==> Checking git status (tracked files only)..."

# Block only if TRACKED files are dirty
$dirtyTracked = git status --porcelain | Where-Object {
    $_ -match '^[ MADRC]'
}

if ($dirtyTracked) {
    Write-Error "Tracked files have uncommitted changes. Commit or stash them before publishing."
}

# ------------------------------------------------------------
# Ensure main branch
# ------------------------------------------------------------

$currentBranch = git branch --show-current
if ($currentBranch -ne "main") {
    Write-Host "==> Switching to 'main' branch..."
    git checkout main
}

$currentBranch = git branch --show-current
if ($currentBranch -ne "main") {
    Write-Error "Failed to switch to 'main' branch."
}

# ------------------------------------------------------------
# Build documentation
# ------------------------------------------------------------

Write-Host "==> Building Sphinx documentation..."
sphinx-build -b html docs docs\_build\html

if (!(Test-Path $HTML_DIR)) {
    Write-Error "HTML output directory not found: $HTML_DIR"
}

# ------------------------------------------------------------
# Prepare gh-pages worktree
# ------------------------------------------------------------

if (!(Test-Path $PAGES_DIR)) {
    Write-Host "==> Creating gh-pages worktree..."
    git worktree add $PAGES_DIR gh-pages
} else {
    Write-Host "==> gh-pages worktree already exists."
}

# ------------------------------------------------------------
# Switch to gh-pages worktree
# ------------------------------------------------------------

Set-Location $PAGES_DIR

$currentBranch = git branch --show-current
if ($currentBranch -ne "gh-pages") {
    Write-Error "Not on gh-pages worktree. Aborting."
}

# ------------------------------------------------------------
# Clean previous HTML content
# ------------------------------------------------------------

Write-Host "==> Cleaning old HTML content..."
Get-ChildItem -Force | Where-Object {
    $_.Name -ne ".git"
} | Remove-Item -Recurse -Force

# ------------------------------------------------------------
# Copy new HTML
# ------------------------------------------------------------

Write-Host "==> Copying new HTML content..."
Copy-Item "$HTML_DIR\*" . -Recurse -Force

# ------------------------------------------------------------
# Ensure .nojekyll exists
# ------------------------------------------------------------

if (!(Test-Path ".nojekyll")) {
    Write-Host "==> Creating .nojekyll file..."
    New-Item ".nojekyll" -ItemType File | Out-Null
}

# ------------------------------------------------------------
# Commit and push
# ------------------------------------------------------------

Write-Host "==> Committing documentation..."
git add .

$changes = git status --porcelain
if (!$changes) {
    Write-Host "==> No changes to publish. Aborting."
    Set-Location $REPO_DIR
    exit 0
}

git commit -m "Publish Sphinx documentation"

Write-Host "==> Pushing to origin/gh-pages..."
git push origin gh-pages --force

# ------------------------------------------------------------
# Return to repository
# ------------------------------------------------------------

Set-Location $REPO_DIR

Write-Host "✅ Documentation published successfully."