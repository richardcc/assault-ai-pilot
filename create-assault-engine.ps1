# Crear proyecto Assault Engine
$ProjectName = "assault-engine"

Write-Host "Creando proyecto: $ProjectName"

# Raíz del proyecto
New-Item -ItemType Directory -Name $ProjectName -Force | Out-Null
Set-Location $ProjectName

# Archivos base
New-Item pyproject.toml -ItemType File | Out-Null
New-Item README.md -ItemType File | Out-Null
New-Item LICENSE -ItemType File | Out-Null

# Código fuente
New-Item src/assault -ItemType Directory -Force | Out-Null
New-Item src/assault/__init__.py -ItemType File | Out-Null

New-Item src/assault/core -ItemType Directory -Force | Out-Null
New-Item src/assault/core/__init__.py -ItemType File | Out-Null
New-Item src/assault/core/hex.py -ItemType File | Out-Null
New-Item src/assault/core/unit.py -ItemType File | Out-Null
New-Item src/assault/core/terrain.py -ItemType File | Out-Null
New-Item src/assault/core/game_state.py -ItemType File | Out-Null

New-Item src/assault/core/combat -ItemType Directory -Force | Out-Null
New-Item src/assault/core/combat/__init__.py -ItemType File | Out-Null
New-Item src/assault/core/combat/close_combat.py -ItemType File | Out-Null

New-Item src/assault/utils -ItemType Directory -Force | Out-Null
New-Item src/assault/utils/__init__.py -ItemType File | Out-Null
New-Item src/assault/utils/dice.py -ItemType File | Out-Null

# Tests
New-Item tests -ItemType Directory -Force | Out-Null
New-Item tests/__init__.py -ItemType File | Out-Null

# Documentación (Sphinx)
New-Item docs -ItemType Directory -Force | Out-Null
New-Item docs/conf.py -ItemType File | Out-Null
New-Item docs/index.rst -ItemType File | Out-Null
New-Item docs/architecture.rst -ItemType File | Out-Null
New-Item docs/core.rst -ItemType File | Out-Null
New-Item docs/combat.rst -ItemType File | Out-Null

New-Item docs/api -ItemType Directory -Force | Out-Null
New-Item docs/api/assault.rst -ItemType File | Out-Null

New-Item docs/_static -ItemType Directory -Force | Out-Null
New-Item docs/_templates -ItemType Directory -Force | Out-Null

Write-Host "✅ Estructura del proyecto creada correctamente"