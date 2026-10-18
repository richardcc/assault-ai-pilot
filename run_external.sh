#!/usr/bin/env bash
set -e

REPO_DIR="C:/repos/python/assault"
cd "$REPO_DIR"

echo "================================================================="
echo " INICIANDO EJECUCION EXTERNA DEL CURRICULUM (GIT BASH / SH)"
echo "================================================================="

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$REPO_DIR/run_external.ps1"
