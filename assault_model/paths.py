"""
Canonical system paths for Assault game assets, catalogs, rules, scenarios, and art.
Centralizes repository-level paths avoiding fragmented or relative parents[...] lookups.
"""
from pathlib import Path

# Repository root (c:\repos\python\assault)
REPO_ROOT = Path(__file__).resolve().parents[1]

# Centralized root assets directory
ASSETS_DIR = REPO_ROOT / "assets"

# Structured subdirectories
CATALOGS_DIR = ASSETS_DIR / "catalogs"
RULES_TABLES_DIR = ASSETS_DIR / "rules_tables"
SCENARIOS_DIR = ASSETS_DIR / "scenarios"
ART_DIR = ASSETS_DIR / "art"

# Canonical Catalog Files
UNIT_CATALOG_PATH = CATALOGS_DIR / "unit_catalog.json"
MAP_PIECE_CATALOG_PATH = CATALOGS_DIR / "map_piece_catalog.json"
FORMATION_CATALOG_PATH = CATALOGS_DIR / "formation_catalog.json"

# Canonical Rules Tables
DICE_FACE_TABLE_PATH = RULES_TABLES_DIR / "combat" / "dice_face_table.v1.json"
CRITICAL_TABLE_PATH = RULES_TABLES_DIR / "combat" / "critical_table.v1.json"
FORTIFICATION_MODIFIERS_PATH = RULES_TABLES_DIR / "fortification" / "fortification_modifiers.v1.json"
TERRAIN_MODIFIERS_PATH = RULES_TABLES_DIR / "terrain" / "terrain_modifiers.v1.json"
RULES_TABLES_MANIFEST_PATH = RULES_TABLES_DIR / "manifest" / "rules_tables_manifest.v1.json"
