"""
tools/unit_editor_server.py

Standalone Web GUI / REST Server for the Assault Unit and Formation Catalog Editor.
Workflow:
1. Loads canonical assets/catalogs/unit_catalog.json, unit_art_inventory.json,
   unit_staging_proposals.json, and formation_catalog.json.
2. Supports staging proposed unit definitions and combined arms tactical formations.
3. Serves an interactive Web UI with card/counter previews, visual editing of stats,
   attacks & range bands matrix, trait chip selector, and full Formation OOB mapping.
4. Auto-saves approved units and formations directly to their canonical JSON catalogs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from assault_backend.services.scenario_editor_service import (
    scenario_editor_service,
    load_unit_catalog_dict,
    load_map_piece_catalog_dict,
    VALID_FORTIFICATIONS,
    VALID_EXPERIENCES,
    VALID_SIDES,
)
from assault_backend.services.map_piece_editor_service import (
    map_piece_editor_service,
    VALID_TERRAINS,
    VALID_EDGE_FEATURES,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_catalog.json"
INVENTORY_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_art_inventory.json"
STAGING_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_staging_proposals.json"
FORMATIONS_PATH = REPO_ROOT / "assets" / "catalogs" / "formation_catalog.json"
FORMATION_INVENTORY_PATH = REPO_ROOT / "assets" / "catalogs" / "formation_art_inventory.json"

STANDARD_TRAITS = [
    "ANTI_TANK",
    "ASSAULT",
    "BACK_BLAST",
    "BANGALORE_TORPEDO",
    "CAMOUFLAGED",
    "CONCEALED",
    "EXPLOSIVE_CHARGE",
    "FAST_DISEMBARK",
    "FLAMETHROWER",
    "FRAGILE_UNIT",
    "HEAVY_WEIGHT",
    "HIDDEN",
    "IMMOBILE",
    "INDIRECT_FIRE",
    "LIMITED_PIVOT",
    "LOW_SILHOUETTE",
    "MINE_DETECTION",
    "NO_LINE_OF_SIGHT",
    "PARATROOPS",
    "PIVOT",
    "RAPID_FIRE",
    "REAR_ECHELON",
    "RECON_PATROL",
    "RIFLE_GRENADES",
    "SCOUT",
    "SET_UP_TIME",
    "SLOW_UNIT",
    "SMOKE",
    "SMOKE_GRENADES",
    "SNIPER",
    "TALL_SILHOUETTE",
    "TANK_BUSTERS",
    "TOUGH",
]


def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return {"_comment": "Core unit definitions", "units": {}}
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(data: dict) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_inventory() -> dict:
    if not INVENTORY_PATH.exists():
        return {"units": []}
    with open(INVENTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_staging() -> dict:
    if not STAGING_PATH.exists():
        return {}
    with open(STAGING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_staging(data: dict) -> None:
    STAGING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STAGING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_formations() -> dict:
    if not FORMATIONS_PATH.exists():
        return {}
    with open(FORMATIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_formations(data: dict) -> None:
    FORMATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FORMATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_formation_inventory() -> dict:
    if not FORMATION_INVENTORY_PATH.exists():
        return {"cards": []}
    with open(FORMATION_INVENTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_formation_inventory(data: dict) -> None:
    FORMATION_INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FORMATION_INVENTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Assault - Tactical Unit & Formation Catalog Editor | Assault - Tactical Scenario Editor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    :root {
      --bg: #0b1120;
      --card-bg: #1e293b;
      --card-border: #334155;
      --card-border-light: #475569;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #0ea5e9;
      --accent-hover: #38bdf8;
      --green: #10b981;
      --green-hover: #34d399;
      --yellow: #f59e0b;
      --red: #ef4444;
      --blue: #3b82f6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 1.2rem; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--card-border); }
    h1 { font-size: 1.4rem; color: #fff; display: flex; align-items: center; gap: 0.5rem; }
    
    .nav-tabs { display: flex; gap: 0.6rem; align-items: center; }
    .btn-nav { padding: 0.5rem 1rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; border: 1px solid var(--card-border); background: #131d31; color: var(--text-muted); cursor: pointer; transition: all 0.15s; }
    .btn-nav:hover { color: #fff; border-color: var(--accent); }
    .btn-nav.active { background: #0284c7; color: #fff; border-color: #38bdf8; box-shadow: 0 0 10px rgba(14, 165, 233, 0.4); }

    .badge { padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .badge-published { background: #065f46; color: #6ee7b7; border: 1px solid #10b981; }
    .badge-staged { background: #854d0e; color: #fde047; border: 1px solid #f59e0b; }
    .badge-pending { background: #374151; color: #d1d5db; border: 1px solid #6b7280; }
    .btn-palette { padding: 0.25rem 0.55rem; font-size: 0.72rem; font-weight: 700; border-radius: 4px; border: 1px solid var(--card-border); color: #fff; cursor: pointer; transition: all 0.15s; }
    .btn-palette:hover { filter: brightness(1.2); border-color: #38bdf8; }
    .btn-palette.active { outline: 2px solid #38bdf8; box-shadow: 0 0 8px rgba(56, 189, 248, 0.6); }
    
    .layout { display: grid; grid-template-columns: 360px 1fr; gap: 1.5rem; }
    .sidebar { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; max-height: calc(100vh - 120px); overflow-y: auto; }
    .search-box { width: 100%; padding: 0.6rem; border-radius: 6px; border: 1px solid var(--card-border); background: #0f172a; color: #fff; margin-bottom: 0.8rem; }
    .unit-list { list-style: none; display: flex; flex-direction: column; gap: 0.4rem; }
    .unit-item { padding: 0.6rem 0.8rem; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: #131d31; border: 1px solid transparent; transition: all 0.15s; }
    .unit-item:hover { border-color: var(--accent); background: #1e293b; }
    .unit-item.active { border-color: var(--accent); background: #0369a1; }
    .unit-item .name { font-weight: 600; font-size: 0.88rem; }
    .unit-item .meta { font-size: 0.72rem; color: var(--text-muted); }

    .status-filters, .faction-filters { display: flex; gap: 0.35rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
    .filter-btn { flex: 1; padding: 0.35rem 0.5rem; font-size: 0.72rem; font-weight: 700; border-radius: 6px; border: 1px solid var(--card-border); background: #131d31; color: var(--text-muted); cursor: pointer; text-align: center; transition: all 0.15s; white-space: nowrap; }
    .filter-btn:hover { color: #fff; border-color: var(--accent); }
    .filter-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .filter-btn.filter-published.active { background: #065f46; color: #6ee7b7; border-color: #10b981; }
    .filter-btn.filter-staged.active { background: #854d0e; color: #fde047; border-color: #f59e0b; }
    .filter-btn.filter-pending.active { background: #374151; color: #d1d5db; border-color: #9ca3af; }
    .filter-btn.filter-faction.active { background: #3b82f6; color: #fff; border-color: #60a5fa; }

    .main-editor { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 1.2rem; height: calc(100vh - 120px); overflow: hidden; display: flex; flex-direction: column; }
    .editor-top { display: grid; grid-template-columns: 340px 1fr; gap: 1.2rem; height: 100%; overflow: hidden; }
    .preview-box { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; text-align: center; height: 100%; overflow-y: auto; display: flex; flex-direction: column; justify-content: flex-start; }
    .card-tabs { display: flex; gap: 0.3rem; }
    .btn-card-tab { padding: 0.25rem 0.6rem; font-size: 0.72rem; font-weight: 700; border-radius: 4px; border: 1px solid var(--card-border); background: #1e293b; color: var(--text-muted); cursor: pointer; }
    .btn-card-tab:hover { color: #fff; border-color: var(--accent); }
    .btn-card-tab.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .preview-box img.card-img { max-width: 100%; max-height: 480px; object-fit: contain; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
    .counter-row { display: flex; justify-content: center; gap: 1rem; margin-top: 1rem; }
    .counter-row img { width: 85px; height: 85px; border-radius: 6px; border: 1px solid var(--card-border); }

    .form-scroll-container { height: 100%; overflow: hidden; display: flex; flex-direction: column; }
    #editor-form { height: 100%; display: flex; flex-direction: column; overflow: hidden; }

    .editor-top-section { flex-shrink: 0; max-height: 42%; overflow-y: auto; padding-right: 0.5rem; margin-bottom: 0.6rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.4rem; }
    .editor-bottom-split { flex: 1; min-height: 0; display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 1rem; overflow: hidden; }

    .split-col-attacks { height: 100%; overflow-y: auto; padding-right: 0.4rem; display: flex; flex-direction: column; }
    .split-col-tactical { height: 100%; overflow-y: auto; padding-right: 0.4rem; display: flex; flex-direction: column; gap: 0.8rem; }

    .fields-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.5rem; margin-bottom: 0.5rem; }
    .field-group { display: flex; flex-direction: column; gap: 0.2rem; }
    .field-group label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
    .field-group input, .field-group select { padding: 0.35rem 0.5rem; border-radius: 6px; border: 1px solid var(--card-border); background: #0f172a; color: #fff; font-size: 0.82rem; }

    .defense-section, .traits-section { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; }
    .attack-section { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem; height: 100%; display: flex; flex-direction: column; overflow: hidden; }
    .section-title { font-size: 0.88rem; font-weight: 700; color: var(--accent); margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; }

    /* Trait Chips */
    .traits-container { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.8rem; }
    .trait-chip { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.65rem; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; border: 1px solid var(--card-border-light); background: #1e293b; color: #94a3b8; transition: all 0.15s; user-select: none; }
    .trait-chip:hover { border-color: var(--accent-hover); color: #fff; }
    .trait-chip.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .add-trait-bar { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.5rem; }
    .add-trait-bar input { flex: 1; padding: 0.45rem 0.6rem; border-radius: 6px; border: 1px solid var(--card-border); background: #131d31; color: #fff; font-size: 0.82rem; }
    .add-trait-bar button { padding: 0.45rem 0.9rem; font-size: 0.82rem; background: #0284c7; color: #fff; border-radius: 6px; }

    /* Attacks and Bands */
    .attack-mode-card { background: #131d31; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.8rem; margin-bottom: 0.8rem; }
    .attack-mode-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
    .attack-mode-title { font-size: 0.85rem; font-weight: 700; color: #e2e8f0; display: flex; align-items: center; gap: 0.4rem; }
    .bands-table { width: 100%; border-collapse: collapse; margin-top: 0.4rem; font-size: 0.82rem; }
    .bands-table th { text-align: left; padding: 0.4rem 0.6rem; background: #0b1120; color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; border-bottom: 1px solid var(--card-border); }
    .bands-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid #1e293b; vertical-align: middle; }
    .bands-table tr:hover td { background: #1a2438; }

    /* Dice Badges */
    .dice-badge-container { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
    .die-badge { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 4px; font-size: 0.7rem; font-weight: 800; color: #fff; cursor: pointer; user-select: none; box-shadow: 0 1px 3px rgba(0,0,0,0.4); }
    .die-badge:hover { opacity: 0.8; transform: scale(1.05); }
    .die-RED { background: #dc2626; border: 1px solid #f87171; }
    .die-YELLOW { background: #d97706; border: 1px solid #fbbf24; color: #000; }
    .die-GREEN { background: #16a34a; border: 1px solid #4ade80; }
    .die-BLUE { background: #2563eb; border: 1px solid #60a5fa; }
    .die-empty { font-size: 0.75rem; color: #64748b; font-style: italic; }

    .die-picker { display: inline-flex; gap: 0.2rem; align-items: center; background: #0b1120; padding: 0.2rem 0.4rem; border-radius: 6px; border: 1px solid var(--card-border); margin-right: 0.5rem; flex-shrink: 0; }
    .btn-add-die { width: 18px; height: 18px; border-radius: 3px; font-size: 0.65rem; font-weight: 900; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; border: none; }

    .btn-small { padding: 0.25rem 0.5rem; font-size: 0.75rem; border-radius: 4px; cursor: pointer; border: none; font-weight: 600; }
    .btn-del-band { background: #7f1d1d; color: #fca5a5; }
    .btn-del-band:hover { background: #991b1b; }
    .btn-add-band { background: #1e3a5f; color: #38bdf8; border: 1px dashed #0284c7; width: 100%; text-align: center; padding: 0.4rem; margin-top: 0.4rem; border-radius: 6px; cursor: pointer; font-size: 0.78rem; font-weight: 600; }
    .btn-add-band:hover { background: #0369a1; color: #fff; }

    .actions-bar { display: flex; justify-content: flex-end; gap: 0.8rem; margin-top: 1rem; padding-top: 0.8rem; border-top: 1px solid var(--card-border); }
    button { padding: 0.6rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }
    .btn-save-draft { background: var(--yellow); color: #000; }
    .btn-save-draft:hover { background: #fbbf24; }
    .btn-approve { background: var(--green); color: #fff; }
    .btn-approve:hover { background: var(--green-hover); }
    .btn-danger { background: #991b1b; color: #fee2e2; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-secondary { background: #334155; color: #e2e8f0; }
    .btn-secondary:hover { background: #475569; }

    .json-preview { width: 100%; height: 110px; font-family: monospace; font-size: 0.78rem; background: #0b1120; color: #38bdf8; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.5rem; resize: vertical; margin-top: 0.5rem; }
    .notification { position: fixed; bottom: 20px; right: 20px; padding: 1rem 1.5rem; border-radius: 6px; background: #10b981; color: #fff; font-weight: 600; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.4); z-index: 1000; }

    /* Formation Editor Specific Styles */
    .formation-card { background: #131d31; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem; margin-bottom: 0.8rem; }
    .formation-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
    .slot-section { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem; margin-bottom: 0.8rem; }
    .slot-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
    .slot-title { font-size: 0.85rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 0.4rem; }
    .unit-slot-item { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0.6rem; background: #1e293b; border: 1px solid var(--card-border); border-radius: 6px; margin-bottom: 0.4rem; }
    .unit-slot-info { display: flex; align-items: center; gap: 0.6rem; font-size: 0.82rem; }
    .qty-controls { display: inline-flex; align-items: center; gap: 0.3rem; margin-right: 0.6rem; }
    .btn-qty { width: 22px; height: 22px; border-radius: 4px; background: #0f172a; color: #fff; border: 1px solid var(--card-border); font-size: 0.75rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; justify-content: center; }
    .btn-qty:hover { border-color: var(--accent); color: var(--accent); }
    .qty-display { font-weight: 700; min-width: 18px; text-align: center; font-size: 0.82rem; color: #fde047; }
    .add-to-slot-bar { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    .add-to-slot-bar select { flex: 1; padding: 0.4rem 0.6rem; border-radius: 6px; border: 1px solid var(--card-border); background: #131d31; color: #fff; font-size: 0.82rem; }
    .add-to-slot-bar button { padding: 0.4rem 0.8rem; font-size: 0.82rem; background: #0284c7; color: #fff; border-radius: 6px; }
    .roster-summary-card { background: #0b1120; border: 1px solid #1e3a5f; border-radius: 8px; padding: 0.8rem; margin-top: 0.8rem; }
    .stat-chip { display: inline-flex; align-items: center; gap: 0.3rem; background: #1e293b; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; color: #e2e8f0; border: 1px solid var(--card-border); }
    .btn-cross-nav { padding: 0.35rem 0.65rem; border-radius: 6px; font-weight: 600; font-size: 0.78rem; text-decoration: none; border: 1px solid var(--card-border); background: #131d31; color: var(--text-muted); transition: all 0.15s; display: inline-flex; align-items: center; gap: 0.35rem; }
    .btn-cross-nav:hover { color: #fff; border-color: var(--accent); background: #1e293b; }
  </style>
</head>
<body>
  <header>
    <h1>🎖️ Assault - Tactical Unit & Formation Catalog Editor</h1>
    <nav class="nav-tabs">
      <button type="button" id="tab-nav-units" class="btn-nav active" onclick="switchView('units')">🎖️ Unit Catalog & Staging</button>
      <button type="button" id="tab-nav-formations" class="btn-nav" onclick="switchView('formations')">🛡️ Formation Catalog (OOB)</button>
      <button type="button" id="tab-nav-scenarios" class="btn-nav" onclick="switchView('scenarios')">🗺️ Scenario Editor (Drafts & Publish)</button>
      <button type="button" id="tab-nav-pieces" class="btn-nav" onclick="switchView('pieces')">🧩 Map Piece Editor (Drafts & Publish)</button>
    </nav>
    <div id="unit-header-badges" style="display: flex; gap: 0.8rem; align-items: center;">
      <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="loadData(0)" title="Reload catalog data">🔄 Reload</button>
      <span id="catalog-count" class="badge badge-published" style="cursor: pointer;" onclick="setStatusFilter('published')">0 Published</span>
      <span id="staging-count" class="badge badge-staged" style="cursor: pointer;" onclick="setStatusFilter('staged')">0 Staged</span>
    </div>
    <div id="formation-header-badges" style="display: none; gap: 0.8rem; align-items: center;">
      <span id="formation-total-badge" class="badge badge-published">12 Formations</span>
    </div>
    <div id="scenario-header-badges" style="display: none; gap: 0.8rem; align-items: center;">
      <span id="scenario-pub-badge" class="badge badge-published">0 Published</span>
      <span id="scenario-draft-badge" class="badge badge-staged">0 Drafts</span>
      <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; background: #0284c7; color: #fff;" onclick="openNewScenarioModal()">➕ New Draft</button>
      <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; background: #059669; color: #fff;" onclick="publishCurrentScenario()">🚀 Publish to Engine</button>
    </div>
    <div id="piece-header-badges" style="display: none; gap: 0.8rem; align-items: center;">
      <span id="piece-pub-badge" class="badge badge-published">0 Published</span>
      <span id="piece-draft-badge" class="badge badge-staged">0 Drafts</span>
      <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; background: #0284c7; color: #fff;" onclick="openNewPieceModal()">➕ New Piece Draft</button>
      <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem; background: #059669; color: #fff;" onclick="publishCurrentPiece()">🚀 Publish Piece</button>
    </div>
    <div style="display: flex; gap: 0.5rem; align-items: center; margin-left: auto;">
      <a href="http://127.0.0.1:8778/docs/" target="_blank" class="btn-cross-nav" style="border-color: #38bdf8; color: #38bdf8;" title="Assault Canonical Documentation Hub">📚 Docs Hub</a>
      <a href="http://127.0.0.1:8778" target="_blank" class="btn-cross-nav" style="border-color: #a855f7; color: #c084fc;" title="MLOps Dashboard & Match Replay Viewer (Port 8778)">📊 MLOps Viewer (8778)</a>
      <a href="http://127.0.0.1:8001/docs" target="_blank" class="btn-cross-nav" style="border-color: #f59e0b; color: #fde047;" title="FastAPI Interactive Swagger Docs (Port 8001)">⚡ Swagger API (8001)</a>
    </div>
  </header>

  <!-- VIEW 1: UNIT CATALOG & STAGING -->
  <div id="view-units" class="layout">
    <div class="sidebar">
      <input type="text" id="search" class="search-box" placeholder="Search units (e.g. Airborne, Rifles, Mortar)..." oninput="filterUnits()" />
      <div class="status-filters">
        <button type="button" id="filter-all" class="filter-btn active" onclick="setStatusFilter('all')">All (<span id="count-all">0</span>)</button>
        <button type="button" id="filter-published" class="filter-btn filter-published" onclick="setStatusFilter('published')">🟢 Published (<span id="count-pub">0</span>)</button>
        <button type="button" id="filter-staged" class="filter-btn filter-staged" onclick="setStatusFilter('staged')">🟡 Staged (<span id="count-stg">0</span>)</button>
        <button type="button" id="filter-pending" class="filter-btn filter-pending" onclick="setStatusFilter('pending')">⚪ Pending (<span id="count-pen">0</span>)</button>
      </div>
            <div class="faction-filters">
        <button type="button" id="filter-faction-all" class="filter-btn filter-faction active" onclick="setFactionFilter('all')">All</button>
        <button type="button" id="filter-faction-GE" class="filter-btn filter-faction" onclick="setFactionFilter('GE')">🇩🇪 GE (<span id="count-fac-GE">0</span>)</button>
        <button type="button" id="filter-faction-US" class="filter-btn filter-faction" onclick="setFactionFilter('US')">🇺🇸 US (<span id="count-fac-US">0</span>)</button>
        <button type="button" id="filter-faction-UK" class="filter-btn filter-faction" onclick="setFactionFilter('UK')">🇬🇧 UK (<span id="count-fac-UK">0</span>)</button>
        <button type="button" id="filter-faction-IT" class="filter-btn filter-faction" onclick="setFactionFilter('IT')">🇮🇹 IT (<span id="count-fac-IT">0</span>)</button>
      </div>
      <div class="category-filters" style="display: flex; gap: 0.25rem; margin-bottom: 0.6rem; flex-wrap: wrap;">
        <button type="button" id="filter-category-all" class="filter-btn filter-category active" onclick="setCategoryFilter('all')">All</button>
        <button type="button" id="filter-category-INFANTRY" class="filter-btn filter-category" onclick="setCategoryFilter('INFANTRY')">🪖 Inf (<span id="count-cat-INFANTRY">0</span>)</button>
        <button type="button" id="filter-category-GUN_ARTILLERY" class="filter-btn filter-category" onclick="setCategoryFilter('GUN_ARTILLERY')">🎯 Art (<span id="count-cat-GUN_ARTILLERY">0</span>)</button>
        <button type="button" id="filter-category-VEHICLE" class="filter-btn filter-category" onclick="setCategoryFilter('VEHICLE')">🛡️ Veh (<span id="count-cat-VEHICLE">0</span>)</button>
        <button type="button" id="filter-category-TRANSPORT" class="filter-btn filter-category" onclick="setCategoryFilter('TRANSPORT')">🚚 Trp (<span id="count-cat-TRANSPORT">0</span>)</button>
      </div>
      <div style="margin-bottom: 0.8rem;">
        <select id="filter-trait-select" class="search-box" style="margin-bottom: 0; padding: 0.45rem; font-size: 0.8rem;" onchange="setTraitFilter(this.value)">
          <option value="all">⚡ Filter by Keyword / Trait (All)</option>
        </select>
      </div>
      <ul id="unit-list" class="unit-list"></ul>
    </div>

    <div class="main-editor">
      <div id="no-selection" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        Select a unit from the left panel to inspect tactical card, edit stats, saving shields, attacks, keywords, or publish.
      </div>

      <div id="editor-form" style="display: none; height: 100%;">
        <div class="editor-top">
          <div class="preview-box">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <h3 style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">Tactical Card</h3>
              <div class="card-tabs">
                <button type="button" id="tab-card-front" class="btn-card-tab active" onclick="switchCardSide('front')">Front (A)</button>
                <button type="button" id="tab-card-back" class="btn-card-tab" onclick="switchCardSide('back')">Back (B)</button>
              </div>
            </div>
            <div style="position: relative;">
              <img id="card-front-img" class="card-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="Card Front" />
              <img id="card-back-img" class="card-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="Card Back" style="display: none;" />
            </div>
            <div class="counter-row">
              <div>
                <img id="counter-front-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="Counter Front" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Counter A</div>
              </div>
              <div>
                <img id="counter-back-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="Counter Back" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Counter B</div>
              </div>
            </div>
          </div>

          <div class="form-scroll-container">
            <div class="editor-top-section">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
                <h2 id="unit-title" style="font-size: 1.15rem; color: #fff;">-</h2>
                <span id="status-badge" class="badge">-</span>
              </div>

              <div class="fields-grid">
                <div class="field-group">
                  <label>Canonical ID</label>
                  <input type="text" id="field-id" />
                </div>
                <div class="field-group">
                  <label>Faction / Nation</label>
                  <select id="field-side">
                    <option value="GE">GE (Germany)</option>
                    <option value="IT">IT (Italy)</option>
                    <option value="UK">UK (United Kingdom)</option>
                    <option value="US">US (United States)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Category</label>
                  <select id="field-category">
                    <option value="INFANTRY">INFANTRY</option>
                    <option value="GUN_ARTILLERY">GUN_ARTILLERY</option>
                    <option value="VEHICLE">VEHICLE</option>
                    <option value="TRANSPORT">TRANSPORT</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Doctrinal Subtype</label>
                  <input type="text" id="field-subtype" placeholder="e.g. STANDARD_INFANTRY..." />
                </div>
                <div class="field-group">
                  <label>Classification</label>
                  <input type="text" id="field-classification" placeholder="e.g. SPECIALIZED_INFANTRY..." />
                </div>
                <div class="field-group">
                  <label>Card ID (Page/Code)</label>
                  <input type="text" id="field-card-id" placeholder="e.g. S43, Pr43..." />
                </div>
                <div class="field-group">
                  <label>Point Cost</label>
                  <input type="number" id="field-cost" min="1" max="50" />
                </div>
                <div class="field-group">
                  <label>Movement (AP)</label>
                  <input type="number" id="field-movement" min="0" max="10" />
                </div>
                <div class="field-group">
                  <label>Max Strength (HP)</label>
                  <input type="number" id="field-max-strength" min="1" max="10" />
                </div>
              </div>

              <!-- Base Defense Shields -->
              <div class="defense-section">
                <div class="section-title">
                  <span>Base Defense Shields (Saving Dice by Arc)</span>
                  <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">Click die to remove or use picker to add</span>
                </div>
                <div id="defense-arcs-container" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.8rem;"></div>
              </div>

              <!-- Tactical Traits & Keywords -->
              <div class="traits-section">
                <div class="section-title">
                  <span>Tactical Keywords & Traits</span>
                  <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">Click chip to toggle or create custom</span>
                </div>
                <div id="traits-chips-container" class="traits-container"></div>
                <div class="add-trait-bar">
                  <input type="text" id="new-trait-input" placeholder="New keyword (e.g. BANGALORE_TORPEDO, MINE_DETECTION...)" onkeydown="if(event.key==='Enter') addNewTrait()" />
                  <button type="button" onclick="addNewTrait()">➕ Add Keyword</button>
                </div>
              </div>
            </div>

            <div class="editor-bottom-split">
              <!-- Left Column: Direct and Indirect Fire -->
              <div class="split-col-attacks">
                <div class="attack-section" style="height: 100%; display: flex; flex-direction: column; overflow: hidden; margin-bottom: 0;">
                  <div class="section-title" style="flex-shrink: 0; margin-bottom: 0.5rem;">
                    <span>Attack Fire Matrix (Direct & Indirect)</span>
                    <div style="display: flex; gap: 0.5rem;">
                      <button type="button" class="btn-small" style="background: #0284c7; color: #fff;" onclick="addAttackMode('DIRECT_FIRE')">+ Direct Fire</button>
                      <button type="button" class="btn-small" style="background: #7c3aed; color: #fff;" onclick="addAttackMode('INDIRECT_FIRE')">+ Indirect Fire</button>
                    </div>
                  </div>
                  <div id="attack-modes-container" style="flex: 1; min-height: 0; overflow-y: auto; padding-right: 0.3rem;"></div>
                </div>
              </div>

              <!-- Right Column: Smoke, Raw JSON, Actions -->
              <div class="split-col-tactical">
                <div id="smoke-action-container"></div>

                <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem;">
                  <details>
                    <summary style="font-size: 0.75rem; color: var(--accent); cursor: pointer; font-weight: 600;">🔍 View / Edit Raw Attack JSON</summary>
                    <textarea id="field-attack-json" class="json-preview" oninput="onJsonInput()"></textarea>
                  </details>
                </div>

                <div class="actions-bar" style="margin-top: auto; display: flex; gap: 0.6rem;">
                  <button class="btn-save-draft" style="flex: 1;" onclick="saveDraft()">💾 Save Staged Draft</button>
                  <button class="btn-approve" style="flex: 1;" onclick="approveAndPublish()">🚀 Approve & Publish</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- VIEW 2: FORMATION CATALOG & OOB MAPPING -->
  <div id="view-formations" class="layout" style="display: none;">
    <div class="sidebar">
      <input type="text" id="search-formations" class="search-box" placeholder="Search formations (e.g. Rifle, Ranger, Pionier)..." oninput="filterFormations()" />
      <div class="status-filters">
        <button type="button" id="filter-form-status-all" class="filter-btn active" onclick="setFormationStatusFilter('all')">All (<span id="count-form-status-all">0</span>)</button>
        <button type="button" id="filter-form-status-mapped" class="filter-btn filter-published" onclick="setFormationStatusFilter('mapped')">🟢 Mapped (<span id="count-form-status-mapped">0</span>)</button>
        <button type="button" id="filter-form-status-pending" class="filter-btn filter-pending" onclick="setFormationStatusFilter('pending')">⚪ Pending (<span id="count-form-status-pending">0</span>)</button>
      </div>
      <div class="faction-filters">
        <button type="button" id="filter-form-all" class="filter-btn filter-faction active" onclick="setFormationFactionFilter('all')">All</button>
        <button type="button" id="filter-form-GE" class="filter-btn filter-faction" onclick="setFormationFactionFilter('GE')">🇩🇪 GE (<span id="count-form-GE">0</span>)</button>
        <button type="button" id="filter-form-US" class="filter-btn filter-faction" onclick="setFormationFactionFilter('US')">🇺🇸 US (<span id="count-form-US">0</span>)</button>
        <button type="button" id="filter-form-UK" class="filter-btn filter-faction" onclick="setFormationFactionFilter('UK')">🇬🇧 UK (<span id="count-form-UK">0</span>)</button>
        <button type="button" id="filter-form-IT" class="filter-btn filter-faction" onclick="setFormationFactionFilter('IT')">🇮🇹 IT (<span id="count-form-IT">0</span>)</button>
      </div>
      <button type="button" style="width: 100%; margin-bottom: 0.8rem; background: #0284c7; color: #fff; padding: 0.5rem; border-radius: 6px; font-weight: 700;" onclick="createNewFormation()">
        ➕ New Custom Formation
      </button>
      <ul id="formation-list" class="unit-list"></ul>
    </div>

    <div class="main-editor">
      <div id="no-formation-selection" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        Select a formation from the left panel or click "+ New Custom Formation" to map combined arms units, command ratings, and slots.
      </div>

      <div id="formation-editor-form" style="display: none; height: 100%;">
        <div class="editor-top">
          <!-- Left Column: Formation Card Preview -->
          <div class="preview-box">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <h3 style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">Formation Card Art</h3>
              <span id="formation-art-badge" class="badge badge-published" style="font-size: 0.65rem;">Art Available</span>
            </div>
            <div style="position: relative; flex: 1; display: flex; align-items: center; justify-content: center; min-height: 380px;">
              <img id="formation-card-img" class="card-img" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E" alt="Formation Card Art" style="max-height: 480px;" />
            </div>
            <div style="margin-top: 0.8rem; text-align: left;">
              <label style="font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Select / Reassign Card Art</label>
              <select id="formation-card-art-select" class="search-box" style="margin-top: 0.3rem; margin-bottom: 0; padding: 0.4rem; font-size: 0.78rem;" onchange="onFormationCardArtSelect(this.value)">
              </select>
            </div>
          </div>

          <!-- Right Column: Form Scroll Container & Slots -->
          <div class="form-scroll-container">
            <!-- Header & Identity fields -->
            <div class="editor-top-section" style="max-height: 40%;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
                <div>
                  <h2 id="formation-title" style="font-size: 1.15rem; color: #fff;">-</h2>
                  <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;" id="formation-subtitle">-</div>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
                  <span id="formation-side-badge" class="badge badge-published">US</span>
                  <span id="formation-cp-badge" class="stat-chip" style="color: #38bdf8;">2 CP</span>
                  <span id="formation-exp-badge" class="stat-chip" style="color: #4ade80;">HARDENED (x5)</span>
                  <span id="formation-units-count-badge" class="stat-chip">0 Units</span>
                  <span id="formation-cost-badge" class="stat-chip" style="color: #fde047;">0 pts</span>
                </div>
              </div>

              <div class="fields-grid" style="margin-bottom: 0.5rem; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));">
                <div class="field-group">
                  <label>Canonical Formation ID</label>
                  <input type="text" id="form-field-id" placeholder="e.g. US_RANGER_ASSAULT_COMPANY" />
                </div>
                <div class="field-group">
                  <label>Formation Display Name</label>
                  <input type="text" id="form-field-name" placeholder="e.g. US Ranger Assault Company" />
                </div>
                <div class="field-group">
                  <label>Nation / Faction</label>
                  <select id="form-field-side" onchange="onFormationSideChange(this.value)">
                    <option value="US">US (United States)</option>
                    <option value="GE">GE (Germany)</option>
                    <option value="UK">UK (United Kingdom)</option>
                    <option value="IT">IT (Italy)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Command Points (CP)</label>
                  <select id="form-field-cp" onchange="syncFormationRosterSummary()">
                    <option value="1">1 CP (1 Chevron v)</option>
                    <option value="2" selected>2 CP (2 Chevrons vv)</option>
                    <option value="3">3 CP (3 Chevrons vvv)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Experience Level</label>
                  <select id="form-field-exp-level" onchange="syncFormationRosterSummary()">
                    <option value="REGULAR">Regular (No Marker)</option>
                    <option value="RECRUIT">Recruit (🔵 Blue / Malus)</option>
                    <option value="HARDENED" selected>Hardened (🟢 Green / +1 Def)</option>
                    <option value="VETERAN">Veteran (🟠 Orange / +1 Atk)</option>
                    <option value="ELITE">Elite (🔴 Red / No Supp)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Exp. Units (xN)</label>
                  <input type="number" id="form-field-exp-count" min="0" max="20" value="5" onchange="syncFormationRosterSummary()" />
                </div>
                <div class="field-group">
                  <label>Command Rating (CR)</label>
                  <input type="number" id="form-field-cr" min="1" max="12" value="8" onchange="syncFormationRosterSummary()" />
                </div>
              </div>

              <div class="field-group" style="margin-bottom: 0.5rem;">
                <label>Tactical Doctrinal Role & Mission Description</label>
                <input type="text" id="form-field-desc" placeholder="e.g. Specialized breach detachment tasked with urban chokepoints and VP penetration." />
              </div>
            </div>

            <!-- Slots & Actions Bottom Section -->
            <div style="flex: 1; min-height: 0; overflow-y: auto; padding-right: 0.4rem; display: flex; flex-direction: column;">
              <!-- 3 Categorical Slots -->
              <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.6rem; margin-bottom: 0.6rem;">
                <!-- Slot 1: Line Units -->
                <div class="slot-section">
                  <div class="slot-header">
                    <span class="slot-title">🎖️ Line Units</span>
                    <span id="slot-count-line" style="font-size: 0.72rem; color: var(--text-muted);">0</span>
                  </div>
                  <div id="slot-units-line" style="min-height: 60px; max-height: 180px; overflow-y: auto;"></div>
                  <div class="add-to-slot-bar">
                    <select id="select-add-line"></select>
                    <button type="button" onclick="addUnitToSlot('line_units')">+</button>
                  </div>
                </div>

                <!-- Slot 2: Heavy Weapons -->
                <div class="slot-section">
                  <div class="slot-header">
                    <span class="slot-title">💣 Heavy Weapons</span>
                    <span id="slot-count-heavy" style="font-size: 0.72rem; color: var(--text-muted);">0</span>
                  </div>
                  <div id="slot-units-heavy" style="min-height: 60px; max-height: 180px; overflow-y: auto;"></div>
                  <div class="add-to-slot-bar">
                    <select id="select-add-heavy"></select>
                    <button type="button" onclick="addUnitToSlot('heavy_weapons')">+</button>
                  </div>
                </div>

                <!-- Slot 3: Specialists -->
                <div class="slot-section">
                  <div class="slot-header">
                    <span class="slot-title">⚡ Specialists</span>
                    <span id="slot-count-special" style="font-size: 0.72rem; color: var(--text-muted);">0</span>
                  </div>
                  <div id="slot-units-special" style="min-height: 60px; max-height: 180px; overflow-y: auto;"></div>
                  <div class="add-to-slot-bar">
                    <select id="select-add-special"></select>
                    <button type="button" onclick="addUnitToSlot('specialists')">+</button>
                  </div>
                </div>
              </div>

              <!-- Live Roster & Order of Battle Summary -->
              <div class="roster-summary-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                  <span style="font-size: 0.82rem; font-weight: 700; color: #38bdf8;">📋 Combined Arms Order of Battle Summary</span>
                  <div style="display: flex; gap: 0.4rem;">
                    <span id="summary-line-badge" class="stat-chip">Line: 0</span>
                    <span id="summary-heavy-badge" class="stat-chip">Heavy: 0</span>
                    <span id="summary-special-badge" class="stat-chip">Special: 0</span>
                    <span id="summary-total-cost" class="stat-chip" style="color: #fde047; font-weight: 700;">Total Cost: 0 pts</span>
                  </div>
                </div>
                <div id="summary-flat-units" style="font-family: monospace; font-size: 0.72rem; color: #94a3b8; word-break: break-all;">
                  units: []
                </div>
              </div>

              <!-- Raw JSON Inspector -->
              <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem; margin-top: 0.6rem;">
                <details>
                  <summary style="font-size: 0.75rem; color: var(--accent); cursor: pointer; font-weight: 600;">🔍 View / Edit Raw Formation JSON</summary>
                  <textarea id="formation-json-raw" class="json-preview" oninput="onFormationJsonInput()"></textarea>
                </details>
              </div>

              <!-- Action Buttons -->
              <div class="actions-bar" style="margin-top: auto; padding-top: 0.6rem;">
                <button type="button" class="btn-danger" onclick="deleteCurrentFormation()">🗑️ Delete Formation</button>
                <button type="button" class="btn-secondary" onclick="cloneCurrentFormation()">📋 Duplicate</button>
                <button type="button" class="btn-approve" onclick="saveCurrentFormation()">💾 Save Formation</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- VIEW 3: SCENARIO EDITOR -->
  <div id="view-scenarios" style="display: none;">
    <div class="layout">
      <!-- Sidebar -->
      <div class="sidebar">
        <input type="text" id="scenario-search" class="search-box" placeholder="Search scenarios (e.g. Mettete, Battaglia)..." oninput="filterScenarios()" />
        
        <div class="status-filters">
          <button type="button" id="scenario-filter-all" class="filter-btn active" onclick="setScenarioFilter('all')">All (<span id="count-scenarios-all">0</span>)</button>
          <button type="button" id="scenario-filter-drafts" class="filter-btn filter-staged" onclick="setScenarioFilter('drafts')">⚡ Drafts (<span id="count-scenarios-drafts">0</span>)</button>
          <button type="button" id="scenario-filter-published" class="filter-btn filter-published" onclick="setScenarioFilter('published')">✓ Published (<span id="count-scenarios-published">0</span>)</button>
        </div>

        <button type="button" class="btn-nav" style="width: 100%; margin-bottom: 0.8rem; background: #0284c7; color: #fff; padding: 0.5rem;" onclick="openNewScenarioModal()">➕ Create New Draft Scenario</button>

        <ul id="scenario-list" class="unit-list">
          <li style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">Loading scenarios...</li>
        </ul>
      </div>

      <!-- Main Scenario Editor Area -->
      <div class="main-editor">
        <div id="no-scenario-selection" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">
          <div style="font-size: 3rem; margin-bottom: 1rem;">🗺️</div>
          <h2>Select a scenario to view or edit</h2>
          <p style="margin-top: 0.5rem; font-size: 0.9rem;">Choose from published scenarios or drafts, or create a new draft.</p>
        </div>

        <div id="scenario-editor-form" style="display: none; height: 100%; flex-direction: column; overflow: hidden;">
          <!-- Scenario Sub-Tabs -->
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.5rem;">
            <div style="display: flex; gap: 0.5rem;">
              <button type="button" id="scen-subtab-map" class="btn-card-tab active" onclick="switchScenarioSubTab('map')">🗺️ Map & Canvas</button>
              <button type="button" id="scen-subtab-units" class="btn-card-tab" onclick="switchScenarioSubTab('units')">⚔️ Order of Battle (Units)</button>
              <button type="button" id="scen-subtab-forts" class="btn-card-tab" onclick="switchScenarioSubTab('forts')">🛡️ Fortifications & VPs</button>
              <button type="button" id="scen-subtab-rules" class="btn-card-tab" onclick="switchScenarioSubTab('rules')">⚙️ Rules & Morale</button>
              <button type="button" id="scen-subtab-json" class="btn-card-tab" onclick="switchScenarioSubTab('json')">📄 Raw JSON & Live Validation</button>
            </div>
            <div style="display: flex; gap: 0.6rem; align-items: center;">
              <button type="button" class="btn-card-tab" onclick="autoFitScenarioCamera()" title="Auto Fit & Center Board">🎯 Fit View</button>
              <button type="button" class="btn-card-tab" onclick="zoomScenarioCanvas(1.15)">➕ Zoom In</button>
              <button type="button" class="btn-card-tab" onclick="zoomScenarioCanvas(0.85)">➖ Zoom Out</button>
              <span id="scenario-status-pill" class="badge badge-published">PUBLISHED</span>
            </div>
          </div>

          <!-- Sub-Tab 1: Canvas & Map View -->
          <div id="scen-panel-map" class="scenario-panel" style="display: flex; flex-direction: column; flex: 1; overflow: hidden; gap: 0.8rem;">
            <div style="position: relative; flex: 1; min-height: 380px; background: #080d1a; border: 1px solid var(--card-border); border-radius: 8px; overflow: hidden;">
              <canvas id="hexCanvas" width="900" height="420" style="width: 100%; height: 100%; display: block; cursor: grab;"></canvas>
              <div id="canvas-info-overlay" style="position: absolute; bottom: 8px; left: 8px; background: rgba(15, 23, 42, 0.85); padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; color: #94a3b8; border: 1px solid #334155;">
                Hover over a hex to view details (Col, Row & Terrain)
              </div>
            </div>

            <!-- Map Pieces Section -->
            <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.6rem 0.8rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <span style="font-size: 0.82rem; font-weight: 700; color: #e2e8f0;">Map Pieces Layout</span>
                <button type="button" class="btn-nav" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;" onclick="addMapPieceToScenario()">➕ Add Map Piece</button>
              </div>
              <div id="scenario-map-pieces-list" style="display: flex; gap: 0.6rem; flex-wrap: wrap;"></div>
            </div>
          </div>

          <!-- Sub-Tab 2: Units / OOB -->
          <div id="scen-panel-units" class="scenario-panel" style="display: none; flex-direction: column; flex: 1; overflow-y: auto; gap: 0.8rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <h3 style="font-size: 0.95rem; color: #e2e8f0;">Scenario Units (Order of Battle)</h3>
              <button type="button" class="btn-approve" style="padding: 0.3rem 0.8rem; font-size: 0.78rem;" onclick="openAddUnitModal()">➕ Deploy Unit</button>
            </div>
            <table class="table-dark" style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
              <thead>
                <tr style="background: #0f172a; text-align: left; border-bottom: 1px solid var(--card-border);">
                  <th style="padding: 0.5rem;">Unit ID</th>
                  <th style="padding: 0.5rem;">Side</th>
                  <th style="padding: 0.5rem;">Hex (Q, R)</th>
                  <th style="padding: 0.5rem;">Facing</th>
                  <th style="padding: 0.5rem;">Experience</th>
                  <th style="padding: 0.5rem;">Turn</th>
                  <th style="padding: 0.5rem;">Actions</th>
                </tr>
              </thead>
              <tbody id="scenario-units-tbody"></tbody>
            </table>
          </div>

          <!-- Sub-Tab 3: Fortifications & VPs -->
          <div id="scen-panel-forts" class="scenario-panel" style="display: none; flex-direction: column; flex: 1; overflow-y: auto; gap: 1rem;">
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <h3 style="font-size: 0.92rem; color: #e2e8f0;">Fortifications</h3>
                <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="addFortificationRow()">➕ Add Fortification</button>
              </div>
              <table class="table-dark" style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
                <thead>
                  <tr style="background: #0f172a; text-align: left; border-bottom: 1px solid var(--card-border);">
                    <th style="padding: 0.4rem;">Hex (Q, R)</th>
                    <th style="padding: 0.4rem;">Type</th>
                    <th style="padding: 0.4rem;">Action</th>
                  </tr>
                </thead>
                <tbody id="scenario-forts-tbody"></tbody>
              </table>
            </div>

            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <h3 style="font-size: 0.92rem; color: #e2e8f0;">Victory Points (VPs)</h3>
                <button type="button" class="btn-nav" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="addVpRow()">➕ Add VP</button>
              </div>
              <table class="table-dark" style="width: 100%; border-collapse: collapse; font-size: 0.82rem;">
                <thead>
                  <tr style="background: #0f172a; text-align: left; border-bottom: 1px solid var(--card-border);">
                    <th style="padding: 0.4rem;">Hex (Q, R)</th>
                    <th style="padding: 0.4rem;">Value</th>
                    <th style="padding: 0.4rem;">Action</th>
                  </tr>
                </thead>
                <tbody id="scenario-vps-tbody"></tbody>
              </table>
            </div>
          </div>

          <!-- Sub-Tab 4: Rules & Morale -->
          <div id="scen-panel-rules" class="scenario-panel" style="display: none; flex-direction: column; flex: 1; overflow-y: auto; gap: 0.8rem;">
            <div class="form-grid" style="grid-template-columns: 1fr 1fr; gap: 1rem;">
              <div class="form-group">
                <label>Scenario Name</label>
                <input type="text" id="scen-field-name" class="form-control" oninput="syncScenarioDataFromInputs()" />
              </div>
              <div class="form-group">
                <label>Max Turns (Duration)</label>
                <input type="number" id="scen-field-max-turns" class="form-control" min="1" max="50" oninput="syncScenarioDataFromInputs()" />
              </div>
              <div class="form-group">
                <label>Attacker Morale Threshold</label>
                <input type="number" id="scen-field-atk-morale" class="form-control" min="1" max="100" oninput="syncScenarioDataFromInputs()" />
              </div>
              <div class="form-group">
                <label>Defender Morale Threshold</label>
                <input type="number" id="scen-field-def-morale" class="form-control" min="1" max="100" oninput="syncScenarioDataFromInputs()" />
              </div>
            </div>
            <div class="form-group">
              <label>Description & Mission Briefing</label>
              <textarea id="scen-field-desc" class="form-control" rows="4" oninput="syncScenarioDataFromInputs()"></textarea>
            </div>
          </div>

          <!-- Sub-Tab 5: Raw JSON & Live Validation -->
          <div id="scen-panel-json" class="scenario-panel" style="display: none; flex-direction: column; flex: 1; overflow: hidden; gap: 0.5rem;">
            <div id="scen-validation-box" style="padding: 0.4rem 0.8rem; border-radius: 4px; font-size: 0.8rem; background: #064e3b; color: #6ee7b7; border: 1px solid #10b981;">
              ✓ Schema Validated
            </div>
            <textarea id="scenario-json-raw" style="flex: 1; width: 100%; background: #0b1120; color: #38bdf8; font-family: monospace; font-size: 0.82rem; padding: 0.8rem; border: 1px solid var(--card-border); border-radius: 6px; resize: none;" oninput="onScenarioJsonInput()"></textarea>
          </div>

          <!-- Bottom Action Buttons -->
          <div class="actions-bar" style="margin-top: 0.8rem; padding-top: 0.6rem; border-top: 1px solid var(--card-border); display: flex; justify-content: flex-end; gap: 0.6rem;">
            <button type="button" class="btn-danger" id="btn-delete-scenario" onclick="deleteCurrentScenario()">🗑️ Delete Draft</button>
            <button type="button" class="btn-secondary" onclick="cloneCurrentScenario()">📋 Duplicate as Draft</button>
            <button type="button" class="btn-approve" onclick="saveCurrentScenarioDraft()">💾 Save Draft</button>
            <button type="button" class="btn-nav" style="background: #059669; color: #fff;" onclick="publishCurrentScenario()">🚀 Publish to Engine</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- VIEW 4: MAP PIECE EDITOR -->
  <div id="view-pieces" style="display: none;">
    <div class="layout">
      <!-- Sidebar -->
      <div class="sidebar">
        <input type="text" id="piece-search" class="search-box" placeholder="Search map pieces (e.g. S2, S3)..." oninput="filterPieces()" />
        
        <div class="status-filters">
          <button type="button" id="piece-filter-all" class="filter-btn active" onclick="setPieceFilter('all')">All (<span id="count-pieces-all">0</span>)</button>
          <button type="button" id="piece-filter-drafts" class="filter-btn filter-staged" onclick="setPieceFilter('drafts')">⚡ Drafts (<span id="count-pieces-drafts">0</span>)</button>
          <button type="button" id="piece-filter-published" class="filter-btn filter-published" onclick="setPieceFilter('published')">✓ Published (<span id="count-pieces-published">0</span>)</button>
        </div>

        <button type="button" class="btn-nav" style="width: 100%; margin-bottom: 0.8rem; background: #0284c7; color: #fff; padding: 0.5rem;" onclick="openNewPieceModal()">➕ Create New Map Piece Draft</button>

        <ul id="piece-list" class="unit-list">
          <li style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">Loading map pieces...</li>
        </ul>
      </div>

      <!-- Main Map Piece Editor Area -->
      <div class="main-editor">
        <div id="no-piece-selection" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted);">
          <div style="font-size: 3rem; margin-bottom: 1rem;">🧩</div>
          <h2>Select a map piece to view or edit</h2>
          <p style="margin-top: 0.5rem; font-size: 0.9rem;">Choose from standard pieces (S2, S3, S4) or custom drafts, or create a new section.</p>
        </div>

        <div id="piece-editor-form" style="display: none; height: 100%; flex-direction: column; overflow: hidden;">
          <!-- Top Tool Palette & Controls -->
          <div style="display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 0.8rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.6rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; gap: 0.6rem; align-items: center;">
                <span id="piece-id-title" style="font-size: 1.1rem; font-weight: 700; color: #38bdf8;">S2</span>
                <span id="piece-shape-pill" class="badge badge-pending">9x8</span>
                <span id="piece-status-pill" class="badge badge-published">PUBLISHED</span>
              </div>
              <div style="display: flex; gap: 0.5rem; align-items: center;">
                <button type="button" class="btn-card-tab" onclick="autoFitPieceCamera()">🎯 Fit Piece</button>
                <button type="button" class="btn-card-tab" onclick="zoomPieceCanvas(1.15)">➕ Zoom In</button>
                <button type="button" class="btn-card-tab" onclick="zoomPieceCanvas(0.85)">➖ Zoom Out</button>
              </div>
            </div>

            <!-- Terrain Painting Palette -->
            <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; background: #0f172a; padding: 0.4rem 0.6rem; border-radius: 6px; border: 1px solid var(--card-border);">
              <span style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; margin-right: 0.4rem;">🖌️ Terrain:</span>
              <button type="button" class="btn-palette active" style="background:#334155;" onclick="selectPieceTerrain('clear', this)">Clear</button>
              <button type="button" class="btn-palette" style="background:#1d4ed8;" onclick="selectPieceTerrain('water', this)">Water</button>
              <button type="button" class="btn-palette" style="background:#15803d;" onclick="selectPieceTerrain('light_forest', this)">Lt Forest</button>
              <button type="button" class="btn-palette" style="background:#14532d;" onclick="selectPieceTerrain('heavy_forest', this)">Hvy Forest</button>
              <button type="button" class="btn-palette" style="background:#4d7c0f;" onclick="selectPieceTerrain('olive_vine_grove', this)">Olive</button>
              <button type="button" class="btn-palette" style="background:#a16207;" onclick="selectPieceTerrain('brush', this)">Brush</button>
              <button type="button" class="btn-palette" style="background:#64748b;" onclick="selectPieceTerrain('rocky', this)">Rocky</button>
              <button type="button" class="btn-palette" style="background:#b45309;" onclick="selectPieceTerrain('building_single', this)">Bldg</button>
              <button type="button" class="btn-palette" style="background:#78350f;" onclick="selectPieceTerrain('building_multi', this)">Bldg+</button>
              <button type="button" class="btn-palette" style="background:#ca8a04;" onclick="selectPieceTerrain('hill', this)">Hill</button>
              <button type="button" class="btn-palette" style="background:#44403c;" onclick="selectPieceTerrain('ruins', this)">Ruins</button>

              <span style="font-size: 0.75rem; font-weight: 700; color: #94a3b8; margin-left: 0.8rem; margin-right: 0.4rem;">🧱 Edge:</span>
              <button type="button" id="btn-tool-wall" class="btn-palette" style="background:#475569;" onclick="togglePieceWallTool(this)">Wall Mode</button>
            </div>
          </div>

          <!-- Piece Canvas Area -->
          <div style="position: relative; flex: 1; min-height: 340px; background: #080d1a; border: 1px solid var(--card-border); border-radius: 8px; overflow: hidden;">
            <canvas id="pieceCanvas" width="900" height="380" style="width: 100%; height: 100%; display: block; cursor: crosshair;"></canvas>
            <div id="piece-canvas-overlay" style="position: absolute; bottom: 8px; left: 8px; background: rgba(15, 23, 42, 0.85); padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; color: #94a3b8; border: 1px solid #334155;">
              Click / Drag on hexes to paint terrain. Click on borders to toggle walls.
            </div>
          </div>

          <!-- Bottom Tabs for Piece Details -->
          <div style="display: flex; gap: 0.5rem; margin-top: 0.6rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.4rem;">
            <button type="button" id="piece-subtab-hexes" class="btn-card-tab active" onclick="switchPieceSubTab('hexes')">📋 Sparse Hexes (<span id="piece-hexes-count">0</span>)</button>
            <button type="button" id="piece-subtab-edges" class="btn-card-tab" onclick="switchPieceSubTab('edges')">🧱 Edge Features (<span id="piece-edges-count">0</span>)</button>
            <button type="button" id="piece-subtab-json" class="btn-card-tab" onclick="switchPieceSubTab('json')">📄 Raw JSON</button>
          </div>

          <!-- Piece Panels -->
          <div id="piece-panel-hexes" style="display: flex; flex-direction: column; max-height: 140px; overflow-y: auto; margin-top: 0.4rem;">
            <table class="table-dark" style="width: 100%; border-collapse: collapse; font-size: 0.78rem;">
              <thead>
                <tr style="background: #0f172a; text-align: left;">
                  <th style="padding: 0.3rem;">Hex (Q, R)</th>
                  <th style="padding: 0.3rem;">Terrain</th>
                  <th style="padding: 0.3rem;">Actions</th>
                </tr>
              </thead>
              <tbody id="piece-hexes-tbody"></tbody>
            </table>
          </div>

          <div id="piece-panel-edges" style="display: none; flex-direction: column; max-height: 140px; overflow-y: auto; margin-top: 0.4rem;">
            <table class="table-dark" style="width: 100%; border-collapse: collapse; font-size: 0.78rem;">
              <thead>
                <tr style="background: #0f172a; text-align: left;">
                  <th style="padding: 0.3rem;">From (Q, R)</th>
                  <th style="padding: 0.3rem;">To (Q, R)</th>
                  <th style="padding: 0.3rem;">Feature</th>
                  <th style="padding: 0.3rem;">Action</th>
                </tr>
              </thead>
              <tbody id="piece-edges-tbody"></tbody>
            </table>
          </div>

          <div id="piece-panel-json" style="display: none; flex-direction: column; max-height: 140px; overflow: hidden; margin-top: 0.4rem;">
            <textarea id="piece-json-raw" style="width: 100%; height: 130px; background: #0b1120; color: #38bdf8; font-family: monospace; font-size: 0.78rem; padding: 0.5rem; border: 1px solid var(--card-border); border-radius: 4px; resize: none;" oninput="onPieceJsonInput()"></textarea>
          </div>

          <!-- Bottom Action Buttons -->
          <div class="actions-bar" style="margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--card-border); display: flex; justify-content: flex-end; gap: 0.6rem;">
            <button type="button" class="btn-danger" id="btn-delete-piece" onclick="deleteCurrentPiece()">🗑️ Delete Draft</button>
            <button type="button" class="btn-secondary" onclick="cloneCurrentPiece()">📋 Duplicate as Draft</button>
            <button type="button" class="btn-approve" onclick="saveCurrentPieceDraft()">💾 Save Draft</button>
            <button type="button" class="btn-nav" style="background: #059669; color: #fff;" onclick="publishCurrentPiece()">🚀 Publish to Catalog</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- MODAL: NEW SCENARIO -->
  <div id="modal-new-scenario" class="modal-backdrop" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center;">
    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; width: 440px; padding: 1.2rem;">
      <h3 style="margin-bottom: 0.8rem; color: #fff;">Create New Draft Scenario</h3>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Scenario ID (filename slug)</label>
        <input type="text" id="new-scen-id" class="form-control" placeholder="e.g. gela_beachhead_1" />
      </div>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Scenario Name</label>
        <input type="text" id="new-scen-name" class="form-control" placeholder="e.g. Gela Beachhead Attack" />
      </div>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Clone from Existing Template (Optional)</label>
        <select id="new-scen-template" class="form-control">
          <option value="">-- Blank Scenario --</option>
        </select>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1rem;">
        <button type="button" class="btn-secondary" onclick="closeNewScenarioModal()">Cancel</button>
        <button type="button" class="btn-approve" onclick="submitCreateScenario()">Create Draft</button>
      </div>
    </div>
  </div>

  <!-- MODAL: NEW MAP PIECE -->
  <div id="modal-new-piece" class="modal-backdrop" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center;">
    <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; width: 440px; padding: 1.2rem;">
      <h3 style="margin-bottom: 0.8rem; color: #fff;">Create New Map Piece Draft</h3>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Piece ID (e.g. S5, RIDGE_1)</label>
        <input type="text" id="new-piece-id" class="form-control" placeholder="e.g. S5" />
      </div>
      <div class="form-grid" style="grid-template-columns: 1fr 1fr; gap: 0.6rem; margin-bottom: 0.8rem;">
        <div class="form-group">
          <label>Width (Cols Q)</label>
          <input type="number" id="new-piece-w" class="form-control" value="9" min="1" max="50" />
        </div>
        <div class="form-group">
          <label>Height (Rows R)</label>
          <input type="number" id="new-piece-h" class="form-control" value="8" min="1" max="50" />
        </div>
      </div>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Description</label>
        <input type="text" id="new-piece-desc" class="form-control" placeholder="e.g. Coastal ridge section 9x8" />
      </div>
      <div class="form-group" style="margin-bottom: 0.8rem;">
        <label>Clone from Existing Template (Optional)</label>
        <select id="new-piece-template" class="form-control">
          <option value="">-- Blank Piece (Clear Terrain) --</option>
        </select>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 1rem;">
        <button type="button" class="btn-secondary" onclick="closeNewPieceModal()">Cancel</button>
        <button type="button" class="btn-approve" onclick="submitCreatePiece()">Create Piece Draft</button>
      </div>
    </div>
  </div>

  <div id="notif" class="notification">Action completed successfully.</div>

  <script>
    // State management
    let inventory = [];
    let catalog = {};
    let staging = {};
    let currentUnit = null;

    let availableTraits = [];
    let activeTraits = new Set();
    let defenseData = {};
    let attackData = {};

        let currentStatusFilter = 'all';
    let currentFactionFilter = 'all';
    let currentCategoryFilter = 'all';
    let currentTraitFilter = 'all';

    function setCategoryFilter(category) {
      currentCategoryFilter = category;
      ['all', 'INFANTRY', 'GUN_ARTILLERY', 'VEHICLE', 'TRANSPORT'].forEach(c => {
        const btn = document.getElementById('filter-category-' + c);
        if (btn) {
          if (c === category) btn.classList.add('active');
          else btn.classList.remove('active');
        }
      });
      renderSidebar();
    }

    // Formation State
    let formations = {};
    let formationInventory = [];
    let currentFormationId = null;
    let currentFormationData = null;
    let formationFactionFilter = 'all';
    let formationStatusFilter = 'all';

        function getUnitStatus(u) {
      if (!u) return 'pending';
      const id = u.id;
      const catKey = u.catalog_key;
      if (catalog[id] || (catKey && catalog[catKey])) {
        return 'published';
      }
      if (staging[id] || (catKey && staging[catKey])) {
        return 'staged';
      }
      return 'pending';
    }

    let isLoadingData = false;
    async function loadData(retryCount = 0) {
      if (isLoadingData && retryCount === 0) return;
      isLoadingData = true;
      try {
        const res = await fetch('/api/units/state', { cache: 'no-store' });
        if (!res.ok) {
          throw new Error('HTTP ' + res.status + ' ' + res.statusText);
        }
        const data = await res.json();
        inventory = data.inventory || [];
        catalog = (data.catalog && data.catalog.units) ? data.catalog.units : {};
        staging = data.staging || {};
        availableTraits = data.traits || [];
        
                const pubCount = inventory.filter(u => getUnitStatus(u) === 'published').length;
        const stgCount = inventory.filter(u => getUnitStatus(u) === 'staged').length;
        const penCount = inventory.filter(u => getUnitStatus(u) === 'pending').length;
        const totalCount = inventory.length;

        const elCat = document.getElementById('catalog-count');
        if (elCat) elCat.innerText = pubCount + ' Published';
        const elStg = document.getElementById('staging-count');
        if (elStg) elStg.innerText = stgCount + ' Staged';

        const elAll = document.getElementById('count-all');
        if (elAll) elAll.innerText = totalCount;
        const elPub = document.getElementById('count-pub');
        if (elPub) elPub.innerText = pubCount;
        const elStgCount = document.getElementById('count-stg');
        if (elStgCount) elStgCount.innerText = stgCount;
        const elPen = document.getElementById('count-pen');
        if (elPen) elPen.innerText = penCount;

                const factions = ['GE', 'US', 'UK', 'IT'];
        factions.forEach(f => {
          const el = document.getElementById('count-fac-' + f);
          if (el) el.innerText = inventory.filter(u => u.faction === f).length;
        });

        const categories = ['INFANTRY', 'GUN_ARTILLERY', 'VEHICLE', 'TRANSPORT'];
        categories.forEach(c => {
          const el = document.getElementById('count-cat-' + c);
          if (el) el.innerText = inventory.filter(u => u.category === c).length;
        });

        const traitSelect = document.getElementById('filter-trait-select');
        if (traitSelect) {
          const savedVal = currentTraitFilter;
          traitSelect.innerHTML = '<option value="all">⚡ Filter by Keyword / Trait (All)</option>';
          availableTraits.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t;
            opt.innerText = t;
            traitSelect.appendChild(opt);
          });
          traitSelect.value = savedVal;
        }

        renderSidebar();
        await loadFormationsData();
        isLoadingData = false;
      } catch (err) {
        isLoadingData = false;
        console.error('Failed to load unit catalog data:', err);
        if (retryCount < 6) {
          console.log(`Retrying unit catalog load in 1s (attempt ${retryCount + 1}/6)...`);
          setTimeout(() => loadData(retryCount + 1), 1000);
        } else {
          const list = document.getElementById('unit-list');
          if (list) {
            list.innerHTML = `
              <li style="padding: 1.2rem; text-align: center; color: #f87171; background: #2a1215; border-radius: 6px; border: 1px solid #7f1d1d;">
                <div style="font-weight: 700; margin-bottom: 0.4rem;">⚠️ Connection Error</div>
                <div style="font-size: 0.78rem; margin-bottom: 0.8rem; color: #fca5a5;">Could not reach backend on port 8780.</div>
                <button type="button" class="btn-nav" style="background: #0284c7; color: #fff;" onclick="loadData(0)">🔄 Retry</button>
              </li>
            `;
          }
        }
      }
    }

    // --- NAVIGATION VIEW SWITCHER ---
    // Terrain color definitions according to canonical assault wargame rules
    const TERRAIN_COLORS = {
      clear: "#334155",
      water: "#1d4ed8",
      light_forest: "#15803d",
      heavy_forest: "#14532d",
      olive_vine_grove: "#4d7c0f",
      brush: "#a16207",
      rocky: "#64748b",
      building_single: "#b45309",
      building_multi: "#78350f",
      hill: "#ca8a04",
      ruins: "#44403c"
    };

    const TERRAIN_SHORTS = {
      clear: "C",
      water: "W",
      light_forest: "LF",
      heavy_forest: "HF",
      olive_vine_grove: "OG",
      brush: "BR",
      rocky: "R",
      building_single: "B",
      building_multi: "B+",
      hill: "H",
      ruins: "RN"
    };

    function switchView(viewName) {
      currentView = viewName;
      const tabUnits = document.getElementById('tab-nav-units');
      const tabFormations = document.getElementById('tab-nav-formations');
      const tabScenarios = document.getElementById('tab-nav-scenarios');
      const tabPieces = document.getElementById('tab-nav-pieces');

      const viewUnits = document.getElementById('view-units');
      const viewFormations = document.getElementById('view-formations');
      const viewScenarios = document.getElementById('view-scenarios');
      const viewPieces = document.getElementById('view-pieces');

      const unitBadges = document.getElementById('unit-header-badges');
      const formationBadges = document.getElementById('formation-header-badges');
      const scenarioBadges = document.getElementById('scenario-header-badges');
      const pieceBadges = document.getElementById('piece-header-badges');

      [tabUnits, tabFormations, tabScenarios, tabPieces].forEach(t => t.classList.remove('active'));
      [viewUnits, viewFormations, viewScenarios, viewPieces].forEach(v => v.style.display = 'none');
      [unitBadges, formationBadges, scenarioBadges, pieceBadges].forEach(b => b.style.display = 'none');

      if (viewName === 'units') {
        tabUnits.classList.add('active');
        viewUnits.style.display = 'grid';
        unitBadges.style.display = 'flex';
      } else if (viewName === 'formations') {
        tabFormations.classList.add('active');
        viewFormations.style.display = 'grid';
        formationBadges.style.display = 'flex';
        renderFormationSidebar();
      } else if (viewName === 'scenarios') {
        tabScenarios.classList.add('active');
        viewScenarios.style.display = 'block';
        scenarioBadges.style.display = 'flex';
        loadScenariosData();
      } else if (viewName === 'pieces') {
        tabPieces.classList.add('active');
        viewPieces.style.display = 'block';
        pieceBadges.style.display = 'flex';
        loadMapPiecesData();
      }
    }

    // --- UNIT CATALOG VIEW FUNCTIONS ---
    function setStatusFilter(status) {
      currentStatusFilter = status;
      ['all', 'published', 'staged', 'pending'].forEach(s => {
        const btn = document.getElementById('filter-' + s);
        if (btn) {
          if (s === status) btn.classList.add('active');
          else btn.classList.remove('active');
        }
      });
      renderSidebar();
    }

    function setFactionFilter(faction) {
      currentFactionFilter = faction;
      ['all', 'GE', 'US', 'UK', 'IT'].forEach(f => {
        const btn = document.getElementById('filter-faction-' + f);
        if (btn) {
          if (f === faction) btn.classList.add('active');
          else btn.classList.remove('active');
        }
      });
      renderSidebar();
    }

    function setTraitFilter(trait) {
      currentTraitFilter = trait;
      renderSidebar();
    }

    function renderSidebar() {
      const q = (document.getElementById('search').value || '').toLowerCase();
      const list = document.getElementById('unit-list');
      list.innerHTML = '';

      inventory.forEach(u => {
        const id = u.id;
        const name = u.name;
        if (q && !id.toLowerCase().includes(q) && !name.toLowerCase().includes(q) && !u.faction.toLowerCase().includes(q) && !(u.category && u.category.toLowerCase().includes(q))) {
          return;
        }

        if (currentFactionFilter !== 'all' && u.faction !== currentFactionFilter) {
          return;
        }

        if (currentCategoryFilter !== 'all' && u.category !== currentCategoryFilter) {
          return;
        }

        const status = getUnitStatus(u);
        if (currentStatusFilter !== 'all' && currentStatusFilter !== status) {
          return;
        }

        const catKey = u.catalog_key;
        const sourceData = catalog[id] || (catKey && catalog[catKey]) || staging[id] || (catKey && staging[catKey]) || {};
        const unitTraits = sourceData.traits || [];

        if (currentTraitFilter !== 'all' && !unitTraits.includes(currentTraitFilter)) {
          return;
        }

        let badgeClass = 'badge-pending';
        let badgeText = 'Pending';
        if (status === 'published') {
          badgeClass = 'badge-published';
          badgeText = 'Published';
        } else if (status === 'staged') {
          badgeClass = 'badge-staged';
          badgeText = 'Staged';
        }

        const li = document.createElement('li');
        li.className = 'unit-item' + (currentUnit && currentUnit.id === id ? ' active' : '');
        li.onclick = () => selectUnit(u);
        li.innerHTML = `
          <div>
            <div class="name">${name}</div>
            <div class="meta">${u.faction} • ${u.category}</div>
          </div>
          <span class="badge ${badgeClass}">${badgeText}</span>
        `;
        list.appendChild(li);
      });
    }

    function filterUnits() {
      renderSidebar();
    }

    function switchCardSide(side) {
      const frontImg = document.getElementById('card-front-img');
      const backImg = document.getElementById('card-back-img');
      const tabFront = document.getElementById('tab-card-front');
      const tabBack = document.getElementById('tab-card-back');

      if (side === 'front') {
        frontImg.style.display = 'block';
        backImg.style.display = 'none';
        tabFront.classList.add('active');
        tabBack.classList.remove('active');
      } else {
        frontImg.style.display = 'none';
        backImg.style.display = 'block';
        tabFront.classList.remove('active');
        tabBack.classList.add('active');
      }
    }

    function selectUnit(u) {
      currentUnit = u;
      renderSidebar();

      document.getElementById('no-selection').style.display = 'none';
      document.getElementById('editor-form').style.display = 'block';

      document.getElementById('card-front-img').src = '/' + u.card_front;
      document.getElementById('card-back-img').src = '/' + (u.card_back || u.card_front);
      switchCardSide('front');

      document.getElementById('counter-front-img').src = '/' + u.counter_front;
      document.getElementById('counter-back-img').src = '/' + (u.counter_back || u.counter_front);

      document.getElementById('unit-title').innerText = u.name + ' (' + u.id + ')';

      const status = getUnitStatus(u);
      const badge = document.getElementById('status-badge');
      if (status === 'published') {
        badge.className = 'badge badge-published';
        badge.innerText = '🟢 Published in Catalog';
      } else if (status === 'staged') {
        badge.className = 'badge badge-staged';
        badge.innerText = '🟡 Staged Proposal';
      } else {
        badge.className = 'badge badge-pending';
        badge.innerText = '⚪ Pending Values';
      }

      const catKey = u.catalog_key;
      const source = catalog[u.id] || (catKey && catalog[catKey]) || staging[u.id] || (catKey && staging[catKey]) || {};

      document.getElementById('field-id').value = u.id;
      document.getElementById('field-side').value = source.side || u.faction;
      document.getElementById('field-category').value = source.category || u.category;
      document.getElementById('field-subtype').value = source.subtype || 'STANDARD_INFANTRY';
      document.getElementById('field-classification').value = source.classification || 'STANDARD_INFANTRY';
      document.getElementById('field-card-id').value = source.card_id || 'S43';
      document.getElementById('field-cost').value = source.cost || 6;
      document.getElementById('field-movement').value = source.movement !== undefined ? source.movement : 2;
      document.getElementById('field-max-strength').value = source.max_strength || 4;

      const baseDef = source.base_defense || { FRONT: ["YELLOW"], FLANK_LEFT: ["YELLOW"], FLANK_RIGHT: ["YELLOW"], REAR: ["YELLOW"] };
      defenseData = {
        FRONT: Array.isArray(baseDef.FRONT) ? [...baseDef.FRONT] : ["YELLOW"],
        FLANK_LEFT: Array.isArray(baseDef.FLANK_LEFT) ? [...baseDef.FLANK_LEFT] : ["YELLOW"],
        FLANK_RIGHT: Array.isArray(baseDef.FLANK_RIGHT) ? [...baseDef.FLANK_RIGHT] : ["YELLOW"],
        REAR: Array.isArray(baseDef.REAR) ? [...baseDef.REAR] : ["YELLOW"]
      };
      renderDefenseArcs();

      const pseudoTraits = new Set([
        "ATTACK_DIE_REROLL",
        "REMOVE_WEAKEST_TERRAIN_DEFENSE",
        "REMOVE_STRONGEST_TERRAIN_DEFENSE",
        "IGNORE_WEAK_TERRAIN_DEFENSE",
        "IGNORE_FIRST_CC_DAMAGE"
      ]);
      const cleanTraits = (source.traits || []).filter(t => !pseudoTraits.has(t));
      activeTraits = new Set(cleanTraits);
      cleanTraits.forEach(t => {
        if (!availableTraits.includes(t)) availableTraits.push(t);
      });
      availableTraits = availableTraits.filter(t => !pseudoTraits.has(t));
      availableTraits.sort();
      renderTraitsChips();

      attackData = JSON.parse(JSON.stringify(source.attack || {
        DIRECT_FIRE: {
          VEHICLE: { "0-10": { dice: [] } },
          INFANTRY: { "0": { dice: ["RED", "RED"] }, "1-3": { dice: ["RED", "YELLOW"] } }
        }
      }));

      if (attackData.SMOKE) {
        let dice = attackData.SMOKE.dice || [];
        if (attackData.SMOKE.SMOKE_TARGET) {
          for (const [rKey, rVal] of Object.entries(attackData.SMOKE.SMOKE_TARGET)) {
            dice = (rVal && rVal.dice) ? rVal.dice : [];
          }
        }
        const maxAdj = attackData.SMOKE.max_adjacent_hexes !== undefined ? attackData.SMOKE.max_adjacent_hexes : 2;
        attackData.SMOKE = {
          target_hex: true,
          max_adjacent_hexes: maxAdj,
          dice: dice
        };
      }

      if (attackData.INDIRECT_FIRE) {
        const ind = attackData.INDIRECT_FIRE;
        let defLoss = ind.defense_loss;
        let rerollVal = ind.reroll;
        if (ind.INFANTRY || ind.VEHICLE || ind.ALL) {
          attackData.INDIRECT_FIRE = JSON.parse(JSON.stringify(ind.INFANTRY || ind.VEHICLE || ind.ALL || {}));
        }
        if (!attackData.INDIRECT_FIRE.defense_loss) {
          attackData.INDIRECT_FIRE.defense_loss = defLoss || "NONE";
        }
        if (attackData.INDIRECT_FIRE.reroll === undefined) {
          attackData.INDIRECT_FIRE.reroll = rerollVal !== undefined ? Boolean(rerollVal) : false;
        }
      }
      syncAttackToUI();
    }

    // --- DEFENSE ARCS ---
    const ARC_LABELS = {
      FRONT: "FRONT",
      FLANK_LEFT: "FLANK LEFT",
      FLANK_RIGHT: "FLANK RIGHT",
      REAR: "REAR"
    };

    function renderDefenseArcs() {
      const container = document.getElementById('defense-arcs-container');
      if (!container) return;
      container.innerHTML = '';

      Object.entries(defenseData).forEach(([arc, dice]) => {
        const card = document.createElement('div');
        card.style.background = '#131d31';
        card.style.border = '1px solid var(--card-border)';
        card.style.borderRadius = '6px';
        card.style.padding = '0.6rem';

        let diceBadges = '';
        if (!dice || dice.length === 0) {
          diceBadges = '<span class="die-empty" style="font-size: 0.72rem;">No dice (0)</span>';
        } else {
          diceBadges = dice.map((d, idx) => `
            <span class="die-badge die-${d}" title="Remove ${d} die" onclick="removeDefenseDie('${arc}', ${idx})">${d[0]}</span>
          `).join('');
        }

        card.innerHTML = `
          <div style="font-size: 0.75rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.4rem; display: flex; justify-content: space-between; align-items: center;">
            <span>${ARC_LABELS[arc] || arc}</span>
            <span style="font-size: 0.65rem; color: var(--text-muted);">${dice ? dice.length : 0} die(s)</span>
          </div>
          <div style="display: flex; gap: 0.2rem; align-items: center; background: #0b1120; padding: 0.2rem 0.35rem; border-radius: 4px; border: 1px solid var(--card-border); margin-bottom: 0.4rem;">
            <span style="font-size: 0.65rem; color: var(--text-muted); margin-right: 2px;">+</span>
            <button type="button" class="btn-add-die die-RED" title="Add Red die" onclick="addDefenseDie('${arc}', 'RED')">R</button>
            <button type="button" class="btn-add-die die-YELLOW" title="Add Yellow die" onclick="addDefenseDie('${arc}', 'YELLOW')">Y</button>
            <button type="button" class="btn-add-die die-GREEN" title="Add Green die" onclick="addDefenseDie('${arc}', 'GREEN')">G</button>
            <button type="button" class="btn-add-die die-BLUE" title="Add Blue die" onclick="addDefenseDie('${arc}', 'BLUE')">B</button>
          </div>
          <div class="dice-badge-container" style="min-height: 26px;">
            ${diceBadges}
          </div>
        `;
        container.appendChild(card);
      });
    }

    function addDefenseDie(arc, color) {
      if (!defenseData[arc]) defenseData[arc] = [];
      defenseData[arc].push(color);
      renderDefenseArcs();
    }

    function removeDefenseDie(arc, index) {
      if (defenseData[arc]) {
        defenseData[arc].splice(index, 1);
        renderDefenseArcs();
      }
    }

    // --- TRAITS CHIPS ---
    
    const TRAIT_DESCRIPTIONS = {
      "ANTI_TANK": "[Tables] Heavy anti-tank weaponry (massive penetration dice vs vehicles).",
      "ASSAULT": "[Engine] Assault specialist at range 0 and close-quarters combat.",
      "BANGALORE_TORPEDO": "[Demolition] Linear explosive charge to breach adjacent barbed wire and minefields.",
      "CAMOUFLAGED": "[Implemented] Passive tactical camouflage in vegetation and cover.",
      "CONCEALED": "[Implemented] Passive stealth and concealment in hindered terrain.",
      "EXPLOSIVE_CHARGE": "[Implemented] Demolition action (Rule 12.5) against buildings, bunkers, and minefields.",
      "FAST_DISEMBARK": "[Roadmap L3] Quick disembark from halftracks consuming only 1 MP.",
      "FRAGILE_UNIT": "[Attributes] Reduced crew (2 HP) vulnerable to rapid attrition and morale tests.",
      "HEAVY_WEIGHT": "[Movement] This unit must be transported to move up or down an elevation level (hills/crests).",
      "HIDDEN": "[Implemented] Immune to automatic spotting until firing or fast moving.",
      "INDIRECT_FIRE": "[Implemented] High-angle parabolic fire without requiring direct line of sight.",
      "LOW_SILHOUETTE": "[Implemented] When defending, applies -1 modifier to attacker's spotting rolls (§10.5, §12.3, §12.4).",
      "MINE_DETECTION": "[Implemented] +2 bonus on D6 rolls for detecting and probing minefields.",
      "NO_LINE_OF_SIGHT": "[Implemented] Automatically prioritizes indirect fire against covered targets.",
      "PARATROOPS": "[Scenario] Airborne elite troops with high cohesion and TOUGH trait.",
      "PIVOT": "[Implemented] 360-degree free turret/mount rotation without MP penalty.",
      "RAPID_FIRE": "[Implemented] Re-rolls 1 unfavorable attack die in ranged or close combat.",
      "RECON_PATROL": "[Doctrine] Vanguard shock patrol and exploration in fog of war.",
      "RIFLE_GRENADES": "[Tables] Rifle grenade launcher attacks at range 1-3 with curved fire.",
      "SCOUT": "[Implemented] +1 bonus on mine detection rolls and RECON doctrine role.",
      "SLOW_UNIT": "[Implemented] Heavy weapon crew unable to perform fast or move-fire actions.",
      "SMOKE": "[Implemented] Deploys ballistic smoke screens that block LOS and provide cover.",
      "SMOKE_GRENADES": "[Implemented] Short-range tactical smoke grenades for infantry.",
      "SNIPER": "[Implemented] Removes defender's strongest terrain defense die against infantry.",
      "TANK_BUSTERS": "[Assault] Close-quarters tank hunter assault with magnetic charges and Molotovs.",
      "TOUGH": "[Implemented] Ignores 1 point of damage in the first round of close combat.",
      "BACK_BLAST": "[Artillery] Firing while marked reduces one Yellow defense die to Green.",
      "FLAMETHROWER": "[Special Weapon] Attacks ignore strongest defense die and inflict automatic suppression.",
      "IMMOBILE": "[Heavy Artillery] Fixed gun mount with 0 autonomous MP; requires transport towing.",
      "LIMITED_PIVOT": "[Arc of Fire] 240-degree firing arc limited to flanks and rear; frontal arc blocked.",
      "REAR_ECHELON": "[Support / Service] Isolated rear troops take automatic damage/suppression when attacked without adjacent allies.",
      "SET_UP_TIME": "[Emplacement] Prolonged deployment time; prohibits MoveThenFire and FireThenMove actions.",
      "TALL_SILHOUETTE": "[Spotting / Defense] High profile unit granting +1 modifier to attacker spotting rolls.",
    };

    function renderTraitsChips() {
      const container = document.getElementById('traits-chips-container');
      if (!container) return;
      container.innerHTML = '';

      availableTraits.forEach(trait => {
        const isActive = activeTraits.has(trait);
        const chip = document.createElement('div');
        chip.className = 'trait-chip' + (isActive ? ' active' : '');
        chip.title = (TRAIT_DESCRIPTIONS[trait] || trait) + ' (Click to toggle)';
        chip.setAttribute('data-desc', TRAIT_DESCRIPTIONS[trait] || '');
        chip.onclick = () => toggleTrait(trait);

        chip.innerHTML = `
          <span>${isActive ? '✓' : '○'}</span>
          <span>${trait}</span>
        `;
        container.appendChild(chip);
      });
    }

    function toggleTrait(trait) {
      if (activeTraits.has(trait)) {
        activeTraits.delete(trait);
      } else {
        activeTraits.add(trait);
      }
      renderTraitsChips();
    }

    function addNewTrait() {
      const input = document.getElementById('new-trait-input');
      const val = (input.value || '').trim().toUpperCase().replace(/\\s+/g, '_');
      if (!val) return;
      if (!availableTraits.includes(val)) {
        availableTraits.push(val);
        availableTraits.sort();
      }
      activeTraits.add(val);
      input.value = '';
      renderTraitsChips();
    }

    // --- ATTACK MATRIX & SMOKE ---
    function syncAttackToUI() {
      renderAttackModesUI();
      renderSmokeUI();
      document.getElementById('field-attack-json').value = JSON.stringify(attackData, null, 2);
    }

    function renderAttackModesUI() {
      const container = document.getElementById('attack-modes-container');
      if (!container) return;
      container.innerHTML = '';

      Object.entries(attackData).forEach(([modeName, modeObj]) => {
        if (modeName === 'SMOKE') return;

        const card = document.createElement('div');
        card.className = 'attack-mode-card';

        const isIndirect = modeName === 'INDIRECT_FIRE';

        let innerContent = '';
        if (isIndirect) {
          innerContent = renderIndirectModeContent(modeObj);
        } else {
          innerContent = renderDirectModeContent(modeName, modeObj);
        }

        card.innerHTML = `
          <div class="attack-mode-header">
            <span class="attack-mode-title">
              <span>${isIndirect ? '☄️' : '🎯'}</span>
              <span>${modeName}</span>
            </span>
            <button type="button" class="btn-small btn-del-band" onclick="removeAttackMode('${modeName}')">Remove Mode</button>
          </div>
          ${innerContent}
        `;
        container.appendChild(card);
      });
    }

    function renderDirectModeContent(modeName, modeObj) {
      let targetsHtml = '';
      const categories = ['VEHICLE', 'INFANTRY'];

      categories.forEach(targetType => {
        const rangesObj = modeObj[targetType] || null;
        if (!rangesObj) {
          targetsHtml += `
            <div style="margin-top: 0.6rem; padding: 0.4rem; background: #0b1120; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Target: ${targetType} (Disabled)</span>
              <button type="button" class="btn-small" style="background: #0284c7; color: #fff;" onclick="addTargetCategory('${modeName}', '${targetType}')">+ Enable Target</button>
            </div>
          `;
          return;
        }

        let rowsHtml = '';
        Object.entries(rangesObj).forEach(([rangeBand, bandData]) => {
          const dice = bandData.dice || [];
          let diceBadges = '';
          if (dice.length === 0) {
            diceBadges = '<span class="die-empty">None</span>';
          } else {
            diceBadges = dice.map((d, idx) => `
              <span class="die-badge die-${d}" title="Remove ${d}" onclick="removeDie('${modeName}', '${targetType}', '${rangeBand}', ${idx})">${d[0]}</span>
            `).join('');
          }

          rowsHtml += `
            <tr>
              <td style="width: 25%;">
                <input type="text" value="${rangeBand}" style="width: 100%; padding: 0.2rem 0.4rem; border-radius: 4px; border: 1px solid var(--card-border); background: #0b1120; color: #fff; font-size: 0.78rem;" onchange="renameRangeBand('${modeName}', '${targetType}', '${rangeBand}', this.value)" />
              </td>
              <td>
                <div class="dice-badge-container">
                  <div class="die-picker">
                    <button type="button" class="btn-add-die die-RED" title="Add Red die" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'RED')">R</button>
                    <button type="button" class="btn-add-die die-YELLOW" title="Add Yellow die" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'YELLOW')">Y</button>
                    <button type="button" class="btn-add-die die-GREEN" title="Add Green die" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'GREEN')">G</button>
                    <button type="button" class="btn-add-die die-BLUE" title="Add Blue die" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'BLUE')">B</button>
                  </div>
                  <div class="dice-badges-list" style="display: inline-flex; gap: 0.25rem; flex-wrap: wrap; align-items: center;">
                    ${diceBadges}
                  </div>
                </div>
              </td>
              <td style="width: 30px; text-align: right;">
                <button type="button" class="btn-small btn-del-band" onclick="removeRangeBand('${modeName}', '${targetType}', '${rangeBand}')">✕</button>
              </td>
            </tr>
          `;
        });

        targetsHtml += `
          <div style="margin-top: 0.6rem; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.5rem; background: #0f172a;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-size: 0.78rem; font-weight: 700; color: #e2e8f0;">Target: ${targetType}</span>
              <button type="button" class="btn-small btn-del-band" onclick="removeTargetCategory('${modeName}', '${targetType}')">Remove</button>
            </div>
            <table class="bands-table">
              <thead><tr><th>Range Band</th><th>Attack Dice</th><th></th></tr></thead>
              <tbody>${rowsHtml}</tbody>
            </table>
            <button type="button" class="btn-add-band" onclick="addNewRangeBand('${modeName}', '${targetType}')">+ Add Range Band</button>
          </div>
        `;
      });

      return targetsHtml;
    }

    function renderIndirectModeContent(modeObj) {
      let rowsHtml = '';
      const specialKeys = new Set(['defense_loss', 'reroll']);

      Object.entries(modeObj).forEach(([rangeBand, bandData]) => {
        if (specialKeys.has(rangeBand)) return;
        const dice = (bandData && bandData.dice) ? bandData.dice : [];
        let diceBadges = '';
        if (dice.length === 0) {
          diceBadges = '<span class="die-empty">None</span>';
        } else {
          diceBadges = dice.map((d, idx) => `
            <span class="die-badge die-${d}" title="Remove ${d}" onclick="removeIndirectDie('${rangeBand}', ${idx})">${d[0]}</span>
          `).join('');
        }

        rowsHtml += `
          <tr>
            <td style="width: 25%;">
              <input type="text" value="${rangeBand}" style="width: 100%; padding: 0.2rem 0.4rem; border-radius: 4px; border: 1px solid var(--card-border); background: #0b1120; color: #fff; font-size: 0.78rem;" onchange="renameIndirectRangeBand('${rangeBand}', this.value)" />
            </td>
            <td>
              <div class="dice-badge-container">
                <div class="die-picker">
                  <button type="button" class="btn-add-die die-RED" title="Add Red die" onclick="addIndirectDie('${rangeBand}', 'RED')">R</button>
                  <button type="button" class="btn-add-die die-YELLOW" title="Add Yellow die" onclick="addIndirectDie('${rangeBand}', 'YELLOW')">Y</button>
                  <button type="button" class="btn-add-die die-GREEN" title="Add Green die" onclick="addIndirectDie('${rangeBand}', 'GREEN')">G</button>
                  <button type="button" class="btn-add-die die-BLUE" title="Add Blue die" onclick="addIndirectDie('${rangeBand}', 'BLUE')">B</button>
                </div>
                <div class="dice-badges-list" style="display: inline-flex; gap: 0.25rem; flex-wrap: wrap; align-items: center;">
                  ${diceBadges}
                </div>
              </div>
            </td>
            <td style="width: 30px; text-align: right;">
              <button type="button" class="btn-small btn-del-band" onclick="removeIndirectRangeBand('${rangeBand}')">✕</button>
            </td>
          </tr>
        `;
      });

      const defLoss = modeObj.defense_loss || 'NONE';
      const reroll = Boolean(modeObj.reroll);

      return `
        <div style="margin-top: 0.4rem; padding: 0.5rem; background: #0f172a; border-radius: 6px; border: 1px solid var(--card-border);">
          <div style="display: flex; gap: 1rem; align-items: center; margin-bottom: 0.6rem;">
            <div class="field-group" style="flex: 1;">
              <label style="font-size: 0.68rem;">Defense Loss</label>
              <select style="padding: 0.25rem 0.4rem; font-size: 0.78rem;" onchange="updateIndirectDefenseLoss(this.value)">
                <option value="NONE" ${defLoss === 'NONE' ? 'selected' : ''}>NONE</option>
                <option value="WEAKEST" ${defLoss === 'WEAKEST' ? 'selected' : ''}>WEAKEST (Remove Weakest Shield)</option>
                <option value="STRONGEST" ${defLoss === 'STRONGEST' ? 'selected' : ''}>STRONGEST (Remove Strongest Shield)</option>
              </select>
            </div>
            <div style="display: flex; align-items: center; gap: 0.4rem; margin-top: 1rem;">
              <input type="checkbox" id="chk-indirect-reroll" ${reroll ? 'checked' : ''} onchange="updateIndirectReroll(this.checked)" />
              <label for="chk-indirect-reroll" style="font-size: 0.75rem; color: #e2e8f0; cursor: pointer;">Reroll Attack Dice</label>
            </div>
          </div>
          <table class="bands-table">
            <thead><tr><th>Range Band</th><th>Indirect Dice</th><th></th></tr></thead>
            <tbody>${rowsHtml}</tbody>
          </table>
          <button type="button" class="btn-add-band" onclick="addNewIndirectRangeBand()">+ Add Range Band</button>
        </div>
      `;
    }

    function renderSmokeUI() {
      const container = document.getElementById('smoke-action-container');
      if (!container) return;

      const smoke = attackData.SMOKE || null;
      if (!smoke) {
        container.innerHTML = `
          <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">Tactical Smoke Curtain (Disabled)</span>
            <button type="button" class="btn-small" style="background: #0284c7; color: #fff;" onclick="enableSmokeAction()">+ Enable Smoke</button>
          </div>
        `;
        return;
      }

      const dice = smoke.dice || [];
      let diceBadges = '';
      if (dice.length === 0) {
        diceBadges = '<span class="die-empty">None</span>';
      } else {
        diceBadges = dice.map((d, idx) => `
          <span class="die-badge die-${d}" title="Remove ${d}" onclick="removeSmokeDie(${idx})">${d[0]}</span>
        `).join('');
      }

      container.innerHTML = `
        <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <span style="font-size: 0.85rem; font-weight: 700; color: #94a3b8; display: flex; align-items: center; gap: 0.4rem;">
              <span>💨</span>
              <span>Tactical Smoke Curtain (Rule 7.2)</span>
            </span>
            <button type="button" class="btn-small btn-del-band" onclick="removeSmokeAction()">Remove</button>
          </div>
          <div style="display: flex; gap: 0.8rem; align-items: center; margin-bottom: 0.5rem;">
            <div class="field-group" style="flex: 1;">
              <label style="font-size: 0.68rem;">Max Adjacent Hexes</label>
              <input type="number" min="0" max="6" value="${smoke.max_adjacent_hexes !== undefined ? smoke.max_adjacent_hexes : 2}" style="padding: 0.25rem 0.4rem; font-size: 0.78rem;" onchange="updateSmokeAdjacent(this.value)" />
            </div>
            <div style="flex: 1;">
              <label style="font-size: 0.68rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Presets</label>
              <div style="display: flex; gap: 0.3rem; margin-top: 0.2rem;">
                <button type="button" class="btn-small" style="background: #1e293b; color: #38bdf8;" onclick="applySmokePreset('ENGINEER')">Engineer (2G, 2B)</button>
                <button type="button" class="btn-small" style="background: #1e293b; color: #38bdf8;" onclick="applySmokePreset('MORTAR')">Mortar (1Y, 1G)</button>
              </div>
            </div>
          </div>
          <div>
            <label style="font-size: 0.68rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Smoke Generation Dice</label>
            <div class="dice-badge-container" style="margin-top: 0.3rem;">
              <div class="die-picker">
                <button type="button" class="btn-add-die die-RED" title="Add Red die" onclick="addSmokeDie('RED')">R</button>
                <button type="button" class="btn-add-die die-YELLOW" title="Add Yellow die" onclick="addSmokeDie('YELLOW')">Y</button>
                <button type="button" class="btn-add-die die-GREEN" title="Add Green die" onclick="addSmokeDie('GREEN')">G</button>
                <button type="button" class="btn-add-die die-BLUE" title="Add Blue die" onclick="addSmokeDie('BLUE')">B</button>
              </div>
              <div class="dice-badges-list" style="display: inline-flex; gap: 0.25rem; flex-wrap: wrap; align-items: center;">
                ${diceBadges}
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function enableSmokeAction() {
      attackData.SMOKE = {
        target_hex: true,
        max_adjacent_hexes: 2,
        dice: ["GREEN", "GREEN", "BLUE", "BLUE"]
      };
      activeTraits.add("SMOKE");
      renderTraitsChips();
      syncAttackToUI();
    }

    function removeSmokeAction() {
      delete attackData.SMOKE;
      syncAttackToUI();
    }

    function updateSmokeAdjacent(val) {
      if (attackData.SMOKE) {
        attackData.SMOKE.max_adjacent_hexes = parseInt(val, 10) || 0;
        syncAttackToUI();
      }
    }

    function addSmokeDie(color) {
      if (attackData.SMOKE) {
        if (!attackData.SMOKE.dice) attackData.SMOKE.dice = [];
        attackData.SMOKE.dice.push(color);
        syncAttackToUI();
      }
    }

    function removeSmokeDie(index) {
      if (attackData.SMOKE && attackData.SMOKE.dice) {
        attackData.SMOKE.dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function applySmokePreset(presetKey) {
      if (!attackData.SMOKE) enableSmokeAction();
      if (presetKey === 'ENGINEER') {
        attackData.SMOKE.dice = ["GREEN", "GREEN", "BLUE", "BLUE"];
        attackData.SMOKE.max_adjacent_hexes = 2;
      } else if (presetKey === 'MORTAR') {
        attackData.SMOKE.dice = ["YELLOW", "GREEN"];
        attackData.SMOKE.max_adjacent_hexes = 1;
      }
      syncAttackToUI();
    }

    function addAttackMode(modeName) {
      if (!attackData[modeName]) {
        if (modeName === 'DIRECT_FIRE') {
          attackData.DIRECT_FIRE = {
            INFANTRY: { "0": { dice: ["RED", "RED"] }, "1-3": { dice: ["RED", "YELLOW"] } },
            VEHICLE: { "0-10": { dice: [] } }
          };
        } else if (modeName === 'INDIRECT_FIRE') {
          attackData.INDIRECT_FIRE = {
            "2-6": { dice: ["YELLOW", "YELLOW"] },
            defense_loss: "NONE",
            reroll: false
          };
        }
        syncAttackToUI();
      }
    }

    function removeAttackMode(modeName) {
      delete attackData[modeName];
      syncAttackToUI();
    }

    function addNewIndirectRangeBand() {
      if (attackData.INDIRECT_FIRE) {
        const bandKey = prompt("Enter Range Band (e.g. 2-8, 3-12):", "2-8");
        if (bandKey && !attackData.INDIRECT_FIRE[bandKey]) {
          attackData.INDIRECT_FIRE[bandKey] = { dice: ["YELLOW"] };
          syncAttackToUI();
        }
      }
    }

    function renameIndirectRangeBand(oldBand, newBand) {
      if (attackData.INDIRECT_FIRE && oldBand !== newBand && newBand.trim()) {
        const saved = attackData.INDIRECT_FIRE[oldBand];
        delete attackData.INDIRECT_FIRE[oldBand];
        attackData.INDIRECT_FIRE[newBand.trim()] = saved;
        syncAttackToUI();
      }
    }

    function removeIndirectRangeBand(bandName) {
      if (attackData.INDIRECT_FIRE) {
        delete attackData.INDIRECT_FIRE[bandName];
        syncAttackToUI();
      }
    }

    function addIndirectDie(rangeBand, dieColor) {
      if (attackData.INDIRECT_FIRE && attackData.INDIRECT_FIRE[rangeBand]) {
        if (!attackData.INDIRECT_FIRE[rangeBand].dice) attackData.INDIRECT_FIRE[rangeBand].dice = [];
        attackData.INDIRECT_FIRE[rangeBand].dice.push(dieColor);
        syncAttackToUI();
      }
    }

    function removeIndirectDie(rangeBand, index) {
      if (attackData.INDIRECT_FIRE && attackData.INDIRECT_FIRE[rangeBand] && attackData.INDIRECT_FIRE[rangeBand].dice) {
        attackData.INDIRECT_FIRE[rangeBand].dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function updateIndirectDefenseLoss(val) {
      if (attackData.INDIRECT_FIRE) {
        attackData.INDIRECT_FIRE.defense_loss = val;
        syncAttackToUI();
      }
    }

    function updateIndirectReroll(checked) {
      if (attackData.INDIRECT_FIRE) {
        attackData.INDIRECT_FIRE.reroll = checked;
        syncAttackToUI();
      }
    }

    function addTargetCategory(modeName, targetType) {
      if (attackData[modeName]) {
        if (!attackData[modeName][targetType]) {
          attackData[modeName][targetType] = {
            "0": { dice: ["RED"] }
          };
          syncAttackToUI();
        }
      }
    }

    function removeTargetCategory(modeName, targetType) {
      if (attackData[modeName] && attackData[modeName][targetType]) {
        delete attackData[modeName][targetType];
        syncAttackToUI();
      }
    }

    function addNewRangeBand(modeName, targetType) {
      if (attackData[modeName] && attackData[modeName][targetType]) {
        const bandKey = prompt("Enter Range Band (e.g. 0, 1-3, 4-6):", "1-3");
        if (bandKey && !attackData[modeName][targetType][bandKey]) {
          attackData[modeName][targetType][bandKey] = { dice: ["RED"] };
          syncAttackToUI();
        }
      }
    }

    function renameRangeBand(modeName, targetType, oldBand, newBand) {
      if (attackData[modeName] && attackData[modeName][targetType] && oldBand !== newBand && newBand.trim()) {
        const saved = attackData[modeName][targetType][oldBand];
        delete attackData[modeName][targetType][oldBand];
        attackData[modeName][targetType][newBand.trim()] = saved;
        syncAttackToUI();
      }
    }

    function removeRangeBand(modeName, targetType, bandName) {
      if (attackData[modeName] && attackData[modeName][targetType]) {
        delete attackData[modeName][targetType][bandName];
        syncAttackToUI();
      }
    }

    function addDie(modeName, targetType, rangeBand, dieColor) {
      if (attackData[modeName] && attackData[modeName][targetType] && attackData[modeName][targetType][rangeBand]) {
        if (!attackData[modeName][targetType][rangeBand].dice) attackData[modeName][targetType][rangeBand].dice = [];
        attackData[modeName][targetType][rangeBand].dice.push(dieColor);
        syncAttackToUI();
      }
    }

    function removeDie(modeName, targetType, rangeBand, index) {
      if (attackData[modeName] && attackData[modeName][targetType] && attackData[modeName][targetType][rangeBand]) {
        attackData[modeName][targetType][rangeBand].dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function onJsonInput() {
      try {
        const parsed = JSON.parse(document.getElementById('field-attack-json').value);
        attackData = parsed;
        renderAttackModesUI();
        renderSmokeUI();
      } catch (e) {}
    }

    function gatherFormData() {
      return {
        side: document.getElementById('field-side').value,
        category: document.getElementById('field-category').value,
        subtype: document.getElementById('field-subtype').value,
        classification: document.getElementById('field-classification').value,
        card_id: document.getElementById('field-card-id').value,
        cost: parseInt(document.getElementById('field-cost').value, 10),
        movement: parseInt(document.getElementById('field-movement').value, 10),
        max_strength: parseInt(document.getElementById('field-max-strength').value, 10),
        base_defense: {
          FRONT: defenseData.FRONT || ["YELLOW"],
          FLANK_LEFT: defenseData.FLANK_LEFT || ["YELLOW"],
          FLANK_RIGHT: defenseData.FLANK_RIGHT || ["YELLOW"],
          REAR: defenseData.REAR || ["YELLOW"]
        },
        traits: Array.from(activeTraits),
        attack: attackData
      };
    }

    async function saveDraft() {
      if (!currentUnit) return;
      const unitId = document.getElementById('field-id').value;
      const data = gatherFormData();

      const res = await fetch('/api/units/stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: unitId, data: data })
      });
      if (res.ok) {
        showNotif('Draft successfully saved to staging.');
        await loadData();
      }
    }

    async function approveAndPublish() {
      if (!currentUnit) return;
      const unitId = document.getElementById('field-id').value;
      const data = gatherFormData();

      const res = await fetch('/api/units/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: unitId, data: data })
      });
      if (res.ok) {
        showNotif('Unit approved and published to canonical catalog.');
        await loadData();
      }
    }

    // --- FORMATIONS VIEW FUNCTIONS ---
    async function loadFormationsData() {
      try {
        const res = await fetch('/api/formations');
        const data = await res.json();
        formations = data.formations || {};
        formationInventory = data.inventory || [];
        populateFormationCardArtDropdown();
        renderFormationSidebar();
        document.getElementById('formation-total-badge').innerText = Object.keys(formations).length + ' Formations (' + formationInventory.length + ' Cards)';
      } catch (e) {
        console.error("Failed to load formations", e);
      }
    }

    function setFormationStatusFilter(status) {
      formationStatusFilter = status;
      ['all', 'mapped', 'pending'].forEach(s => {
        const btn = document.getElementById('filter-form-status-' + s);
        if (btn) {
          if (s === status) btn.classList.add('active');
          else btn.classList.remove('active');
        }
      });
      renderFormationSidebar();
    }

    function setFormationFactionFilter(faction) {
      formationFactionFilter = faction;
      ['all', 'GE', 'US', 'UK', 'IT'].forEach(f => {
        const btn = document.getElementById('filter-form-' + f);
        if (btn) {
          if (f === faction) btn.classList.add('active');
          else btn.classList.remove('active');
        }
      });
      renderFormationSidebar();
    }

    function filterFormations() {
      renderFormationSidebar();
    }

    function populateFormationCardArtDropdown() {
      const select = document.getElementById('formation-card-art-select');
      if (!select) return;
      select.innerHTML = '<option value="">(None / Custom Formation)</option>';
      formationInventory.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.card_image;
        opt.innerText = `${c.faction}: ${c.title}`;
        select.appendChild(opt);
      });
    }

    function onFormationCardArtSelect(imgVal) {
      if (!currentFormationData) return;
      currentFormationData.card_image = imgVal;
      const imgEl = document.getElementById('formation-card-img');
      if (imgVal) {
        imgEl.src = '/' + imgVal;
        imgEl.style.display = 'block';
      } else {
        imgEl.src = '';
        imgEl.style.display = 'none';
      }
      syncFormationRosterSummary();
    }

    function renderFormationSidebar() {
      const q = (document.getElementById('search-formations').value || '').toLowerCase();
      const list = document.getElementById('formation-list');
      if (!list) return;
      list.innerHTML = '';

      // Count stats
      let totalAll = 0, totalMapped = 0, totalPending = 0;
      const fCounts = { GE: 0, US: 0, UK: 0, IT: 0 };

      // Build unified list of entries (Catalog Formations + Unmapped Cards)
      const mappedKeys = new Set(Object.keys(formations));
      const unifiedList = [];

      // 1. Mapped formations
      Object.entries(formations).forEach(([fid, fdef]) => {
        const side = (fdef.side || 'US').toUpperCase();
        totalAll++;
        totalMapped++;
        if (fCounts[side] !== undefined) fCounts[side]++;

        unifiedList.push({
          type: 'mapped',
          id: fid,
          name: fdef.name || fid.replace(/_/g, ' '),
          side: side,
          command_rating: fdef.command_rating || 8,
          command_points: fdef.command_points || 2,
          experience_level: fdef.experience_level || "REGULAR",
          experience_units_count: fdef.experience_units_count || 0,
          units: fdef.units || [],
          card_image: fdef.card_image || '',
          data: fdef
        });
      });

      // 2. Unmapped Inventory Cards
      formationInventory.forEach(card => {
        // Skip if already in mappedKeys
        if (mappedKeys.has(card.id) || (card.catalog_key && mappedKeys.has(card.catalog_key))) {
          return;
        }
        totalAll++;
        totalPending++;
        const side = (card.faction || 'US').toUpperCase();
        if (fCounts[side] !== undefined) fCounts[side]++;

        unifiedList.push({
          type: 'pending',
          id: card.id,
          name: card.title,
          side: side,
          command_rating: 8,
          units: [],
          card_image: card.card_image,
          data: null
        });
      });

      // Update counters in UI
      const cntAll = document.getElementById('count-form-status-all');
      if (cntAll) cntAll.innerText = totalAll;
      const cntMap = document.getElementById('count-form-status-mapped');
      if (cntMap) cntMap.innerText = totalMapped;
      const cntPen = document.getElementById('count-form-status-pending');
      if (cntPen) cntPen.innerText = totalPending;

      ['GE', 'US', 'UK', 'IT'].forEach(f => {
        const el = document.getElementById('count-form-' + f);
        if (el) el.innerText = fCounts[f];
      });

      // Filter and render
      unifiedList.forEach(item => {
        const fid = item.id;
        const name = item.name;
        const side = item.side;

        if (q && !fid.toLowerCase().includes(q) && !name.toLowerCase().includes(q) && !side.toLowerCase().includes(q)) {
          return;
        }

        if (formationFactionFilter !== 'all' && side !== formationFactionFilter) {
          return;
        }

        if (formationStatusFilter === 'mapped' && item.type !== 'mapped') return;
        if (formationStatusFilter === 'pending' && item.type !== 'pending') return;

        let totalCost = 0;
        item.units.forEach(uid => {
          const u = catalog[uid] || staging[uid];
          if (u && u.cost) totalCost += u.cost;
        });

        const isCurrent = currentFormationId === fid;
        const li = document.createElement('li');
        li.className = 'unit-item' + (isCurrent ? ' active' : '');
        li.onclick = () => selectFormationItem(item);

        let badgeHtml = '';
        let metaHtml = '';
        if (item.type === 'mapped') {
          badgeHtml = `<span class="badge badge-published">${side} • MAPPED</span>`;
          metaHtml = `${side} • ${item.units.length} Units • ${item.command_points || 2} CP • ${item.experience_level || "REG"} (x${item.experience_units_count || 0}) • <span style="color: #fde047;">${totalCost} pts</span>`;
        } else {
          badgeHtml = `<span class="badge badge-pending">${side} • CARD</span>`;
          metaHtml = `${side} • Unmapped Card • Ready to configure OOB`;
        }

        li.innerHTML = `
          <div>
            <div class="name">${name}</div>
            <div class="meta">${metaHtml}</div>
          </div>
          ${badgeHtml}
        `;
        list.appendChild(li);
      });
    }

    function selectFormationItem(item) {
      if (item.type === 'mapped') {
        selectFormation(item.id);
      } else {
        // Pending card: initialize draft formation
        currentFormationId = item.id;
        currentFormationData = {
          name: item.name,
          side: item.side,
          command_rating: 8,
          command_points: 2,
          experience_level: "REGULAR",
          experience_units_count: 0,
          line_units: [],
          heavy_weapons: [],
          specialists: [],
          units: [],
          card_image: item.card_image,
          description: `Tactical formation card scanned from Assault wargame catalog: ${item.name}.`
        };

        renderFormationSidebar();

        document.getElementById('no-formation-selection').style.display = 'none';
        document.getElementById('formation-editor-form').style.display = 'flex';

        document.getElementById('formation-title').innerText = item.name;
        document.getElementById('formation-subtitle').innerText = item.id + ' (Pending Initial OOB Mapping)';
        document.getElementById('formation-side-badge').innerText = item.side;

        document.getElementById('form-field-id').value = item.id;
        document.getElementById('form-field-name').value = item.name;
        document.getElementById('form-field-side').value = item.side;
        document.getElementById('form-field-cr').value = 8;
        document.getElementById('form-field-cp').value = 2;
        document.getElementById('form-field-exp-level').value = "REGULAR";
        document.getElementById('form-field-exp-count').value = 0;
        document.getElementById('form-field-desc').value = currentFormationData.description;

        const imgEl = document.getElementById('formation-card-img');
        if (item.card_image) {
          imgEl.src = '/' + item.card_image;
          imgEl.style.display = 'block';
        } else {
          imgEl.src = '';
          imgEl.style.display = 'none';
        }

        const selArt = document.getElementById('formation-card-art-select');
        if (selArt) selArt.value = item.card_image || '';

        populateUnitSelectDropdowns(item.side);
        renderFormationSlots();
        syncFormationRosterSummary();
      }
    }

    function selectFormation(fid) {
      currentFormationId = fid;
      const fdef = formations[fid];
      if (!fdef) return;
      currentFormationData = JSON.parse(JSON.stringify(fdef));

      // Ensure lists exist
      if (!currentFormationData.line_units) currentFormationData.line_units = [];
      if (!currentFormationData.heavy_weapons) currentFormationData.heavy_weapons = [];
      if (!currentFormationData.specialists) currentFormationData.specialists = [];
      if (!currentFormationData.units) {
        currentFormationData.units = [
          ...currentFormationData.line_units,
          ...currentFormationData.heavy_weapons,
          ...currentFormationData.specialists
        ];
      }

      renderFormationSidebar();

      document.getElementById('no-formation-selection').style.display = 'none';
      document.getElementById('formation-editor-form').style.display = 'flex';

      document.getElementById('formation-title').innerText = currentFormationData.name || fid;
      document.getElementById('formation-subtitle').innerText = fid;
      document.getElementById('formation-side-badge').innerText = (currentFormationData.side || 'US').toUpperCase();

      document.getElementById('form-field-id').value = fid;
      document.getElementById('form-field-name').value = currentFormationData.name || '';
      document.getElementById('form-field-side').value = (currentFormationData.side || 'US').toUpperCase();
      document.getElementById('form-field-cr').value = currentFormationData.command_rating || 8;
      document.getElementById('form-field-cp').value = currentFormationData.command_points || 2;
      document.getElementById('form-field-exp-level').value = (currentFormationData.experience_level || "REGULAR").toUpperCase();
      document.getElementById('form-field-exp-count').value = currentFormationData.experience_units_count !== undefined ? currentFormationData.experience_units_count : 0;
      document.getElementById('form-field-desc').value = currentFormationData.description || '';

      const cardImg = currentFormationData.card_image || '';
      const imgEl = document.getElementById('formation-card-img');
      if (cardImg) {
        imgEl.src = '/' + cardImg;
        imgEl.style.display = 'block';
      } else {
        imgEl.src = '';
        imgEl.style.display = 'none';
      }

      const selArt = document.getElementById('formation-card-art-select');
      if (selArt) selArt.value = cardImg;

      populateUnitSelectDropdowns((currentFormationData.side || 'US').toUpperCase());
      renderFormationSlots();
      syncFormationRosterSummary();
    }

    function createNewFormation() {
      const fid = prompt("Enter new Canonical Formation ID (e.g. US_ARMORED_ASSAULT_TEAM):", "US_NEW_FORMATION");
      if (!fid || !fid.trim()) return;
      const cleanId = fid.trim().toUpperCase().replace(/\\s+/g, '_');

      formations[cleanId] = {
        name: cleanId.replace(/_/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase()),
        side: "US",
        command_rating: 8,
        line_units: ["US_RIFLES_43", "US_RIFLES_43", "US_RIFLES_43"],
        heavy_weapons: ["US_BAZOOKA_TEAM"],
        specialists: [],
        units: ["US_RIFLES_43", "US_RIFLES_43", "US_RIFLES_43", "US_BAZOOKA_TEAM"],
        description: "New tactical combined arms formation."
      };

      selectFormation(cleanId);
      renderFormationSidebar();
    }

    function onFormationSideChange(side) {
      if (currentFormationData) {
        currentFormationData.side = side;
        document.getElementById('formation-side-badge').innerText = side;
        populateUnitSelectDropdowns(side);
        syncFormationRosterSummary();
      }
    }

    function populateUnitSelectDropdowns(side) {
      const slots = ['line', 'heavy', 'special'];
      const unitOptions = Object.keys(catalog).sort();

      slots.forEach(slotKey => {
        const select = document.getElementById('select-add-' + slotKey);
        if (!select) return;
        select.innerHTML = '';

        // Prioritize matching faction, then others
        const factionUnits = unitOptions.filter(uid => {
          const u = catalog[uid];
          return (u && u.side === side) || uid.startsWith(side + '_');
        });
        const otherUnits = unitOptions.filter(uid => !factionUnits.includes(uid));

        const optGroup1 = document.createElement('optgroup');
        optGroup1.label = `${side} Available Units`;
        factionUnits.forEach(uid => {
          const u = catalog[uid];
          const cost = u ? u.cost : 6;
          const opt = document.createElement('option');
          opt.value = uid;
          opt.innerText = `${uid} (${cost} pts)`;
          optGroup1.appendChild(opt);
        });
        select.appendChild(optGroup1);

        if (otherUnits.length > 0) {
          const optGroup2 = document.createElement('optgroup');
          optGroup2.label = `Allied & Other Units`;
          otherUnits.forEach(uid => {
            const u = catalog[uid];
            const cost = u ? u.cost : 6;
            const opt = document.createElement('option');
            opt.value = uid;
            opt.innerText = `${uid} (${cost} pts)`;
            optGroup2.appendChild(opt);
          });
          select.appendChild(optGroup2);
        }
      });
    }

    function renderFormationSlots() {
      if (!currentFormationData) return;

      const mapping = [
        { key: 'line_units', containerId: 'slot-units-line', countId: 'slot-count-line' },
        { key: 'heavy_weapons', containerId: 'slot-units-heavy', countId: 'slot-count-heavy' },
        { key: 'specialists', containerId: 'slot-units-special', countId: 'slot-count-special' }
      ];

      mapping.forEach(m => {
        const container = document.getElementById(m.containerId);
        const countBadge = document.getElementById(m.countId);
        if (!container) return;
        container.innerHTML = '';

        const unitsList = currentFormationData[m.key] || [];
        countBadge.innerText = unitsList.length + ' unit(s)';

        // Group units by frequency
        const counts = {};
        unitsList.forEach(uid => { counts[uid] = (counts[uid] || 0) + 1; });

        Object.entries(counts).forEach(([uid, qty]) => {
          const u = catalog[uid] || staging[uid] || {};
          const cost = (u.cost || 6) * qty;

          const item = document.createElement('div');
          item.className = 'unit-slot-item';
          item.innerHTML = `
            <div class="unit-slot-info">
              <span style="font-weight: 700; color: #fff;">${uid}</span>
              <span class="stat-chip">${u.category || 'INFANTRY'}</span>
              <span class="stat-chip" style="color: #fde047;">${cost} pts</span>
            </div>
            <div style="display: flex; align-items: center;">
              <div class="qty-controls">
                <button type="button" class="btn-qty" onclick="modifySlotUnitQty('${m.key}', '${uid}', -1)">-</button>
                <span class="qty-display">${qty}</span>
                <button type="button" class="btn-qty" onclick="modifySlotUnitQty('${m.key}', '${uid}', 1)">+</button>
              </div>
              <button type="button" class="btn-small btn-del-band" title="Remove all ${uid}" onclick="removeSlotUnitAll('${m.key}', '${uid}')">✕</button>
            </div>
          `;
          container.appendChild(item);
        });
      });
    }

    function addUnitToSlot(slotKey) {
      if (!currentFormationData) return;
      let selectId = 'select-add-line';
      if (slotKey === 'heavy_weapons') selectId = 'select-add-heavy';
      if (slotKey === 'specialists') selectId = 'select-add-special';

      const select = document.getElementById(selectId);
      if (!select || !select.value) return;
      const unitId = select.value;

      if (!currentFormationData[slotKey]) currentFormationData[slotKey] = [];
      currentFormationData[slotKey].push(unitId);

      renderFormationSlots();
      syncFormationRosterSummary();
    }

    function modifySlotUnitQty(slotKey, unitId, delta) {
      if (!currentFormationData || !currentFormationData[slotKey]) return;
      const list = currentFormationData[slotKey];
      if (delta > 0) {
        list.push(unitId);
      } else if (delta < 0) {
        const idx = list.indexOf(unitId);
        if (idx !== -1) list.splice(idx, 1);
      }
      renderFormationSlots();
      syncFormationRosterSummary();
    }

    function removeSlotUnitAll(slotKey, unitId) {
      if (!currentFormationData || !currentFormationData[slotKey]) return;
      currentFormationData[slotKey] = currentFormationData[slotKey].filter(u => u !== unitId);
      renderFormationSlots();
      syncFormationRosterSummary();
    }

    function syncFormationRosterSummary() {
      if (!currentFormationData) return;

      const lines = currentFormationData.line_units || [];
      const heavies = currentFormationData.heavy_weapons || [];
      const specs = currentFormationData.specialists || [];
      const allUnits = [...lines, ...heavies, ...specs];
      currentFormationData.units = allUnits;

      let totalCost = 0;
      allUnits.forEach(uid => {
        const u = catalog[uid] || staging[uid];
        if (u && u.cost) totalCost += u.cost;
        else totalCost += 6;
      });

      document.getElementById('formation-units-count-badge').innerText = allUnits.length + ' Units';
      document.getElementById('formation-cost-badge').innerText = totalCost + ' pts';
      document.getElementById('summary-line-badge').innerText = 'Line: ' + lines.length;
      document.getElementById('summary-heavy-badge').innerText = 'Heavy: ' + heavies.length;
      document.getElementById('summary-special-badge').innerText = 'Special: ' + specs.length;
      document.getElementById('summary-total-cost').innerText = 'Total Cost: ' + totalCost + ' pts';

      document.getElementById('summary-flat-units').innerText = 'units: [' + allUnits.map(u => `"${u}"`).join(', ') + ']';

      // Update current formation payload
      currentFormationData.name = document.getElementById('form-field-name').value;
      currentFormationData.side = document.getElementById('form-field-side').value;
      currentFormationData.command_rating = parseInt(document.getElementById('form-field-cr').value, 10) || 8;
      currentFormationData.command_points = parseInt(document.getElementById('form-field-cp').value, 10) || 2;
      currentFormationData.experience_level = document.getElementById('form-field-exp-level').value || "REGULAR";
      currentFormationData.experience_units_count = parseInt(document.getElementById('form-field-exp-count').value, 10) || 0;
      currentFormationData.description = document.getElementById('form-field-desc').value;

      // Update CP & Experience badges
      const cpBadge = document.getElementById('formation-cp-badge');
      if (cpBadge) cpBadge.innerText = (currentFormationData.command_points || 2) + ' CP';
      const expBadge = document.getElementById('formation-exp-badge');
      if (expBadge) {
        const expLvl = (currentFormationData.experience_level || 'REGULAR').toUpperCase();
        const expCnt = currentFormationData.experience_units_count || 0;
        expBadge.innerText = `${expLvl} (x${expCnt})`;
        const expColors = { RECRUIT: '#38bdf8', REGULAR: '#94a3b8', HARDENED: '#4ade80', VETERAN: '#fb923c', ELITE: '#f87171' };
        expBadge.style.color = expColors[expLvl] || '#94a3b8';
      }

      document.getElementById('formation-json-raw').value = JSON.stringify(currentFormationData, null, 2);
    }

    function onFormationJsonInput() {
      try {
        const parsed = JSON.parse(document.getElementById('formation-json-raw').value);
        currentFormationData = parsed;
        renderFormationSlots();
        syncFormationRosterSummary();
      } catch (e) {}
    }

    async function saveCurrentFormation() {
      if (!currentFormationData) return;
      const targetId = document.getElementById('form-field-id').value.trim();
      if (!targetId) {
        alert("Please enter a valid Formation ID.");
        return;
      }

      syncFormationRosterSummary();

      const payload = {
        id: targetId,
        data: currentFormationData
      };

      const res = await fetch('/api/formations/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        showNotif('Formation successfully saved to catalog.');
        currentFormationId = targetId;
        await loadFormationsData();
        selectFormation(targetId);
      } else {
        alert("Failed to save formation.");
      }
    }

    async function deleteCurrentFormation() {
      if (!currentFormationId) return;
      if (!confirm(`Are you sure you want to delete formation '${currentFormationId}'?`)) return;

      const res = await fetch('/api/formations/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentFormationId })
      });

      if (res.ok) {
        showNotif('Formation deleted.');
        currentFormationId = null;
        currentFormationData = null;
        document.getElementById('no-formation-selection').style.display = 'block';
        document.getElementById('formation-editor-form').style.display = 'none';
        await loadFormationsData();
      }
    }

    function cloneCurrentFormation() {
      if (!currentFormationId || !currentFormationData) return;
      const newId = currentFormationId + '_COPY';
      formations[newId] = JSON.parse(JSON.stringify(currentFormationData));
      formations[newId].name = (currentFormationData.name || currentFormationId) + ' (Copy)';
      selectFormation(newId);
      renderFormationSidebar();
    }

    function showNotif(msg) {
      const el = document.getElementById('notif');
      el.innerText = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 3000);
    }

    // ==========================================
    // SCENARIO & MAP PIECE FRONTEND BUNDLE
    // ==========================================

    let scenarios = [];
    let currentScenarioId = null;
    let currentScenarioData = null;
    let scenarioFilter = 'all';

    let mapPieces = [];
    let currentPieceId = null;
    let currentPieceData = null;
    let pieceFilter = 'all';

    let catalogsCache = {
      units: [],
      map_pieces: [],
      fortifications: [],
      experiences: [],
      sides: []
    };

    let mapPieceDefinitions = {}; // piece_id -> raw piece object

    // Canvas Transform State for Scenarios
    let canvasZoom = 24;
    let canvasOffsetX = 60;
    let canvasOffsetY = 50;
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let hoveredHex = null;

    // Canvas Transform State for Map Pieces
    let pieceCanvasZoom = 26;
    let pieceOffsetX = 60;
    let pieceOffsetY = 50;
    let isPiecePanning = false;
    let piecePanStartX = 0;
    let piecePanStartY = 0;
    let isPaintingPiece = false;
    let pieceActiveTerrain = 'clear';
    let pieceWallToolActive = false;
    let hoveredPieceHex = null;

    // --- Math & Hex Helpers (Pointy-topped Odd-R Staggered) ---
    function hexToPixel(q, r, zoom, offX, offY) {
      const hexWidth = zoom * Math.sqrt(3);
      const hexHeight = zoom * 1.5;
      const x = hexWidth * (q + 0.5 * (r % 2)) + offX;
      const y = hexHeight * r + offY;
      return { x, y };
    }

    function pixelToHex(px, py, zoom, offX, offY) {
      const hexWidth = zoom * Math.sqrt(3);
      const hexHeight = zoom * 1.5;
      const relY = py - offY;
      const r = Math.round(relY / hexHeight);
      const relX = (px - offX) - hexWidth * 0.5 * (Math.abs(r) % 2);
      const q = Math.round(relX / hexWidth);
      return { q, r };
    }

    function drawPointyHex(ctx, cx, cy, size, fillColor, strokeColor, lineWidth = 1) {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 6) + (i * Math.PI / 3);
        const hx = cx + size * Math.cos(angle);
        const hy = cy + size * Math.sin(angle);
        if (i === 0) ctx.moveTo(hx, hy);
        else ctx.lineTo(hx, hy);
      }
      ctx.closePath();
      if (fillColor) {
        ctx.fillStyle = fillColor;
        ctx.fill();
      }
      if (strokeColor) {
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = lineWidth;
        ctx.stroke();
      }
    }

    // --- Load Global Catalogs ---
    async function loadGlobalCatalogs() {
      try {
        const res = await fetch('/api/catalogs');
        const data = await res.json();
        if (data.ok) {
          catalogsCache = data;
          populateScenarioCatalogs();
        }
      } catch (e) {
        console.error('Failed to load catalogs', e);
      }
    }

    // --- SCENARIO EDITOR LOGIC ---
    async function loadScenariosData() {
      await loadGlobalCatalogs();
      await loadAllMapPieceDefinitions();
      try {
        const res = await fetch('/api/scenarios');
        const data = await res.json();
        if (data.ok) {
          scenarios = data.scenarios;
          updateScenarioHeaderBadges();
          renderScenarioSidebar();
          if (currentScenarioId) {
            selectScenario(currentScenarioId);
          } else if (scenarios.length > 0) {
            selectScenario(scenarios[0].id);
          }
        }
      } catch (e) {
        console.error('Failed to load scenarios', e);
      }
    }

    async function loadAllMapPieceDefinitions() {
      try {
        const res = await fetch('/api/map_pieces');
        const data = await res.json();
        if (data.ok) {
          for (const p of data.pieces) {
            try {
              const pres = await fetch('/api/map_pieces/' + p.id);
              const pdata = await pres.json();
              if (pdata.ok) {
                mapPieceDefinitions[p.id] = pdata.piece;
              }
            } catch (err) {}
          }
        }
      } catch (e) {
        console.error('Failed to load piece definitions', e);
      }
    }

    function updateScenarioHeaderBadges() {
      const pubCount = scenarios.filter(s => !s.is_draft).length;
      const draftCount = scenarios.filter(s => s.is_draft).length;
      document.getElementById('scenario-pub-badge').innerText = pubCount + ' Published';
      document.getElementById('scenario-draft-badge').innerText = draftCount + ' Drafts';
      document.getElementById('count-scenarios-all').innerText = scenarios.length;
      document.getElementById('count-scenarios-drafts').innerText = draftCount;
      document.getElementById('count-scenarios-published').innerText = pubCount;
    }

    function setScenarioFilter(filt) {
      scenarioFilter = filt;
      ['all', 'drafts', 'published'].forEach(f => {
        const btn = document.getElementById('scenario-filter-' + f);
        if (btn) btn.classList.toggle('active', f === filt);
      });
      renderScenarioSidebar();
    }

    function filterScenarios() {
      renderScenarioSidebar();
    }

    function renderScenarioSidebar() {
      const query = (document.getElementById('scenario-search')?.value || '').toLowerCase().trim();
      const listEl = document.getElementById('scenario-list');
      listEl.innerHTML = '';

      const filtered = scenarios.filter(s => {
        if (scenarioFilter === 'drafts' && !s.is_draft) return false;
        if (scenarioFilter === 'published' && s.is_draft) return false;
        if (query && !s.id.toLowerCase().includes(query) && !s.name.toLowerCase().includes(query)) return false;
        return true;
      });

      if (filtered.length === 0) {
        listEl.innerHTML = '<li style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">No scenarios match filter</li>';
        return;
      }

      filtered.forEach(s => {
        const li = document.createElement('li');
        li.className = 'unit-item' + (s.id === currentScenarioId ? ' active' : '');
        li.onclick = () => selectScenario(s.id);

        const badgeClass = s.is_draft ? 'badge-staged' : 'badge-published';
        const badgeText = s.is_draft ? 'DRAFT' : 'PUBLISHED';

        li.innerHTML = `
          <div>
            <div class="name">${escapeHtml(s.name || s.id)}</div>
            <div class="meta">${s.id} &bull; ${s.max_turns} turns &bull; ${s.unit_count} units &bull; ${s.vp_count} VPs</div>
          </div>
          <span class="badge ${badgeClass}">${badgeText}</span>
        `;
        listEl.appendChild(li);
      });
    }

    async function selectScenario(scenId) {
      currentScenarioId = scenId;
      renderScenarioSidebar();

      try {
        const res = await fetch('/api/scenarios/' + scenId);
        const data = await res.json();
        if (data.ok) {
          currentScenarioData = data.scenario;
          displayScenarioForm();
          autoFitScenarioCamera();
          drawScenarioCanvas();
        }
      } catch (e) {
        console.error('Failed to load scenario details', e);
      }
    }

    function displayScenarioForm() {
      document.getElementById('no-scenario-selection').style.display = 'none';
      const form = document.getElementById('scenario-editor-form');
      form.style.display = 'flex';

      const s = currentScenarioData;
      const isDraft = !!s.is_draft;

      // Status pill & Delete button
      const pill = document.getElementById('scenario-status-pill');
      pill.innerText = isDraft ? 'DRAFT' : 'PUBLISHED';
      pill.className = 'badge ' + (isDraft ? 'badge-staged' : 'badge-published');

      document.getElementById('btn-delete-scenario').style.display = isDraft ? 'inline-block' : 'none';

      // Rules tab fields
      document.getElementById('scen-field-name').value = s.name || s.id || '';
      document.getElementById('scen-field-max-turns').value = s.max_turns || 8;
      document.getElementById('scen-field-atk-morale').value = s.rules?.attacker_morale_threshold || 10;
      document.getElementById('scen-field-def-morale').value = s.rules?.defender_morale_threshold || 10;
      document.getElementById('scen-field-desc').value = s.description || '';

      // JSON Raw
      document.getElementById('scenario-json-raw').value = JSON.stringify(s, null, 2);

      renderScenarioMapPieces();
      renderScenarioUnitsTable();
      renderScenarioFortsTable();
      renderScenarioVpsTable();
    }

    function switchScenarioSubTab(tabName) {
      ['map', 'units', 'forts', 'rules', 'json'].forEach(t => {
        document.getElementById('scen-subtab-' + t).classList.toggle('active', t === tabName);
        document.getElementById('scen-panel-' + t).style.display = (t === tabName ? 'flex' : 'none');
      });
      if (tabName === 'map') {
        setTimeout(() => { drawScenarioCanvas(); }, 50);
      }
    }

    function getScenarioMapPieces() {
      if (!currentScenarioData) return [];
      return currentScenarioData.map?.pieces || currentScenarioData.map_pieces || [];
    }

    function getScenarioUnits() {
      if (!currentScenarioData) return [];
      return currentScenarioData.units || [];
    }

    function getUnitCoords(u) {
      if (Array.isArray(u.position) && u.position.length >= 2) {
        return { q: u.position[0], r: u.position[1] };
      }
      return { q: u.q !== undefined ? u.q : 0, r: u.r !== undefined ? u.r : 0 };
    }

    function getScenarioFortifications() {
      if (!currentScenarioData) return [];
      return currentScenarioData.map?.fortifications || currentScenarioData.fortifications || [];
    }

    function getScenarioVps() {
      if (!currentScenarioData) return [];
      return currentScenarioData.vp?.hexes || currentScenarioData.victory_points || [];
    }

    function autoFitScenarioCamera() {
      if (!currentScenarioData) return;
      const canvas = document.getElementById('hexCanvas');
      if (!canvas) return;

      const [w, h] = currentScenarioData.shape || [9, 8];
      const availW = canvas.width - 60;
      const availH = canvas.height - 60;

      const approxHexW = availW / (w + 0.5);
      const approxHexH = availH / (h * 1.5 + 0.5);
      const sizeFromW = approxHexW / Math.sqrt(3);
      const sizeFromH = approxHexH;

      canvasZoom = Math.max(10, Math.min(36, Math.floor(Math.min(sizeFromW, sizeFromH))));
      canvasOffsetX = Math.max(20, Math.floor((canvas.width - (w + 0.5) * canvasZoom * Math.sqrt(3)) / 2));
      canvasOffsetY = Math.max(20, Math.floor((canvas.height - h * canvasZoom * 1.5) / 2));
      drawScenarioCanvas();
    }

    function zoomScenarioCanvas(factor) {
      canvasZoom = Math.max(10, Math.min(60, Math.round(canvasZoom * factor)));
      drawScenarioCanvas();
    }

    function buildScenarioTerrainAndElevationMap() {
      const terrainMap = {};
      const elevationMap = {};
      const wallsList = [];

      if (!currentScenarioData) return { terrainMap, elevationMap, wallsList };

      const pieces = getScenarioMapPieces();
      for (const pEntry of pieces) {
        const pid = pEntry.id || pEntry.piece_id;
        const origin = pEntry.origin || [0, 0];
        const pDef = mapPieceDefinitions[pid];
        if (pDef) {
          for (const hx of pDef.hexes || []) {
            const gq = origin[0] + hx.q;
            const gr = origin[1] + hx.r;
            terrainMap[gq + ',' + gr] = hx.terrain || 'clear';
            if (hx.elevation) elevationMap[gq + ',' + gr] = hx.elevation;
          }
          for (const ed of pDef.hex_edges || []) {
            try {
              const [q1, r1] = ed.from.split(',').map(Number);
              const [q2, r2] = ed.to.split(',').map(Number);
              wallsList.push({
                from: `${origin[0] + q1},${origin[1] + r1}`,
                to: `${origin[0] + q2},${origin[1] + r2}`,
                feature: ed.feature || 'wall'
              });
            } catch (e) {}
          }
        }
      }
      return { terrainMap, elevationMap, wallsList };
    }

    function drawScenarioCanvas() {
      const canvas = document.getElementById('hexCanvas');
      if (!canvas || !currentScenarioData) return;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const [cols, rows] = currentScenarioData.shape || [9, 8];
      const { terrainMap, elevationMap, wallsList } = buildScenarioTerrainAndElevationMap();

      // 1. Draw Hex Grid with Real Terrain Colors
      for (let r = 0; r < rows; r++) {
        for (let q = 0; q < cols; q++) {
          const { x, y } = hexToPixel(q, r, canvasZoom, canvasOffsetX, canvasOffsetY);
          const tKey = q + ',' + r;
          const terrain = terrainMap[tKey] || 'clear';
          const elev = elevationMap[tKey] || 0;

          const fillColor = TERRAIN_COLORS[terrain] || '#334155';
          const strokeColor = '#475569';

          drawPointyHex(ctx, x, y, canvasZoom, fillColor, strokeColor, 1);

          // Elevation indicator
          if (elev > 0) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText('+' + elev, x + canvasZoom * 0.7, y - canvasZoom * 0.4);
          }

          // Subtle terrain short code in bottom
          const tShort = TERRAIN_SHORTS[terrain] || '';
          if (tShort && canvasZoom >= 18) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(tShort, x, y + canvasZoom * 0.65);
          }

          // Coordinate label at top
          if (canvasZoom >= 16) {
            ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`${q},${r}`, x, y - canvasZoom * 0.35);
          }
        }
      }

      // 2. Draw Walls / Hex Edges
      for (const w of wallsList) {
        try {
          const [q1, r1] = w.from.split(',').map(Number);
          const [q2, r2] = w.to.split(',').map(Number);
          const p1 = hexToPixel(q1, r1, canvasZoom, canvasOffsetX, canvasOffsetY);
          const p2 = hexToPixel(q2, r2, canvasZoom, canvasOffsetX, canvasOffsetY);

          // Midpoint between hex centers is where edge lies
          const mx = (p1.x + p2.x) / 2;
          const my = (p1.y + p2.y) / 2;
          // Normal perpendicular
          const dx = p2.x - p1.x;
          const dy = p2.y - p1.y;
          const len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len * (canvasZoom * 0.5);
          const ny = dx / len * (canvasZoom * 0.5);

          ctx.beginPath();
          ctx.moveTo(mx - nx, my - ny);
          ctx.lineTo(mx + nx, my + ny);
          ctx.strokeStyle = '#f59e0b'; // Gold wall
          ctx.lineWidth = 3.5;
          ctx.stroke();
        } catch (e) {}
      }

      // 3. Draw Fortifications
      for (const f of getScenarioFortifications()) {
        const { x, y } = hexToPixel(f.q, f.r, canvasZoom, canvasOffsetX, canvasOffsetY);
        ctx.beginPath();
        ctx.arc(x, y + 2, canvasZoom * 0.4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
        ctx.fill();
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(f.type ? f.type.substring(0, 4).toUpperCase() : 'FORT', x, y + 5);
      }

      // 4. Draw Victory Points
      for (const vp of getScenarioVps()) {
        const { x, y } = hexToPixel(vp.q, vp.r, canvasZoom, canvasOffsetX, canvasOffsetY);
        ctx.beginPath();
        ctx.arc(x, y, canvasZoom * 0.35, 0, Math.PI * 2);
        ctx.fillStyle = '#f59e0b';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#000';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('VP' + (vp.value || 1), x, y + 3);
      }

      // 5. Draw Units
      for (const u of getScenarioUnits()) {
        const { q, r } = getUnitCoords(u);
        const { x, y } = hexToPixel(q, r, canvasZoom, canvasOffsetX, canvasOffsetY);
        const isUS = (u.side || '').toUpperCase() === 'US';
        const isIT = (u.side || '').toUpperCase() === 'IT';
        const sideColor = isUS ? '#2563eb' : (isIT ? '#16a34a' : '#475569');

        ctx.beginPath();
        ctx.arc(x, y, canvasZoom * 0.42, 0, Math.PI * 2);
        ctx.fillStyle = sideColor;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        const shortName = (u.unit_id || '').substring(0, 3).toUpperCase();
        ctx.fillText(shortName, x, y + 3);
      }

      // 6. Draw Hover Outline
      if (hoveredHex) {
        const { x, y } = hexToPixel(hoveredHex.q, hoveredHex.r, canvasZoom, canvasOffsetX, canvasOffsetY);
        drawPointyHex(ctx, x, y, canvasZoom, null, '#38bdf8', 2.5);
      }
    }

    // Canvas Mouse Event Handlers
    const scenCanvas = document.getElementById('hexCanvas');
    if (scenCanvas) {
      scenCanvas.addEventListener('mousedown', e => {
        isPanning = true;
        panStartX = e.clientX - canvasOffsetX;
        panStartY = e.clientY - canvasOffsetY;
        scenCanvas.style.cursor = 'grabbing';
      });

      window.addEventListener('mouseup', () => {
        isPanning = false;
        if (scenCanvas) scenCanvas.style.cursor = 'grab';
      });

      scenCanvas.addEventListener('mousemove', e => {
        if (isPanning) {
          canvasOffsetX = e.clientX - panStartX;
          canvasOffsetY = e.clientY - panStartY;
          drawScenarioCanvas();
          return;
        }

        const rect = scenCanvas.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;
        const { q, r } = pixelToHex(px, py, canvasZoom, canvasOffsetX, canvasOffsetY);

        if (!currentScenarioData) return;
        const [w, h] = currentScenarioData.shape || [9, 8];
        if (q >= 0 && q < w && r >= 0 && r < h) {
          hoveredHex = { q, r };
          const { terrainMap, elevationMap } = buildScenarioTerrainAndElevationMap();
          const t = terrainMap[q + ',' + r] || 'clear';
          const el = elevationMap[q + ',' + r] || 0;
          document.getElementById('canvas-info-overlay').innerText = `Hex (${q}, ${r}) | Terrain: ${t} | Elev: +${el}`;
        } else {
          hoveredHex = null;
        }
        drawScenarioCanvas();
      });

      scenCanvas.addEventListener('wheel', e => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        canvasZoom = Math.max(12, Math.min(60, Math.round(canvasZoom * factor)));
        drawScenarioCanvas();
      });
    }

    // --- Scenario Tables Rendering ---
    function renderScenarioMapPieces() {
      const container = document.getElementById('scenario-map-pieces-list');
      container.innerHTML = '';
      getScenarioMapPieces().forEach((mp, idx) => {
        const div = document.createElement('div');
        div.style = 'background: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; font-size: 0.78rem; display: flex; align-items: center; gap: 0.5rem; color: #fff;';
        const pid = mp.id || mp.piece_id;
        const origin = mp.origin || [0, 0];
        div.innerHTML = `
          <span><b>${pid}</b> @ [${origin.join(',')}]</span>
          <button type="button" class="btn-danger" style="padding: 1px 4px; font-size: 0.65rem;" onclick="removeMapPieceFromScenario(${idx})">×</button>
        `;
        container.appendChild(div);
      });
    }

    function renderScenarioUnitsTable() {
      const tbody = document.getElementById('scenario-units-tbody');
      tbody.innerHTML = '';
      getScenarioUnits().forEach((u, idx) => {
        const { q, r } = getUnitCoords(u);
        const tr = document.createElement('tr');
        tr.style = 'border-bottom: 1px solid #334155;';
        tr.innerHTML = `
          <td style="padding: 0.4rem;"><b>${u.unit_id || u.unit_key}</b></td>
          <td style="padding: 0.4rem;"><span class="badge ${u.side === 'US' ? 'badge-published' : 'badge-staged'}">${u.side}</span></td>
          <td style="padding: 0.4rem;">${q}, ${r}</td>
          <td style="padding: 0.4rem;">${u.facing || 0}°</td>
          <td style="padding: 0.4rem;">${u.experience || 'REGULAR'}</td>
          <td style="padding: 0.4rem;">Turn ${u.entry_turn || 1}</td>
          <td style="padding: 0.4rem;">
            <button type="button" class="btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;" onclick="removeScenarioUnit(${idx})">🗑️ Remove</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function renderScenarioFortsTable() {
      const tbody = document.getElementById('scenario-forts-tbody');
      tbody.innerHTML = '';
      getScenarioFortifications().forEach((f, idx) => {
        const tr = document.createElement('tr');
        tr.style = 'border-bottom: 1px solid #334155;';
        tr.innerHTML = `
          <td style="padding: 0.4rem;">${f.q}, ${f.r}</td>
          <td style="padding: 0.4rem;"><span class="badge badge-published">${f.type}</span></td>
          <td style="padding: 0.4rem;">
            <button type="button" class="btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;" onclick="removeFortification(${idx})">🗑️</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function renderScenarioVpsTable() {
      const tbody = document.getElementById('scenario-vps-tbody');
      tbody.innerHTML = '';
      getScenarioVps().forEach((vp, idx) => {
        const tr = document.createElement('tr');
        tr.style = 'border-bottom: 1px solid #334155;';
        tr.innerHTML = `
          <td style="padding: 0.4rem;">${vp.q}, ${vp.r}</td>
          <td style="padding: 0.4rem;"><b>${vp.value || 1} pts</b></td>
          <td style="padding: 0.4rem;">
            <button type="button" class="btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.72rem;" onclick="removeVp(${idx})">🗑️</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function removeScenarioUnit(idx) {
      currentScenarioData.units.splice(idx, 1);
      renderScenarioUnitsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function removeFortification(idx) {
      currentScenarioData.fortifications.splice(idx, 1);
      renderScenarioFortsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function removeVp(idx) {
      currentScenarioData.victory_points.splice(idx, 1);
      renderScenarioVpsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function addFortificationRow() {
      const q = prompt("Enter Fortification Hex Q (column):", "0");
      if (q === null) return;
      const r = prompt("Enter Fortification Hex R (row):", "0");
      if (r === null) return;
      const type = prompt("Enter Fortification Type (bunker, pillbox, trench):", "bunker");
      if (!type) return;

      if (!currentScenarioData.fortifications) currentScenarioData.fortifications = [];
      currentScenarioData.fortifications.push({
        q: parseInt(q, 10) || 0,
        r: parseInt(r, 10) || 0,
        type: type.trim().toLowerCase()
      });
      renderScenarioFortsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function addVpRow() {
      const q = prompt("Enter VP Hex Q (column):", "0");
      if (q === null) return;
      const r = prompt("Enter VP Hex R (row):", "0");
      if (r === null) return;
      const val = prompt("Enter VP Value (points):", "1");
      if (!val) return;

      if (!currentScenarioData.victory_points) currentScenarioData.victory_points = [];
      currentScenarioData.victory_points.push({
        q: parseInt(q, 10) || 0,
        r: parseInt(r, 10) || 0,
        value: parseInt(val, 10) || 1
      });
      renderScenarioVpsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function addMapPieceToScenario() {
      const pid = prompt("Enter Map Piece ID (e.g. S2, S3, S4):", "S2");
      if (!pid) return;
      const oq = prompt("Origin Q (column offset):", "0");
      if (oq === null) return;
      const or_ = prompt("Origin R (row offset):", "0");
      if (or_ === null) return;

      if (!currentScenarioData.map_pieces) currentScenarioData.map_pieces = [];
      currentScenarioData.map_pieces.push({
        piece_id: pid.trim(),
        origin: [parseInt(oq, 10) || 0, parseInt(or_, 10) || 0]
      });
      renderScenarioMapPieces();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function removeMapPieceFromScenario(idx) {
      currentScenarioData.map_pieces.splice(idx, 1);
      renderScenarioMapPieces();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function openAddUnitModal() {
      const uid = prompt("Enter Unit ID (e.g. INF_RIFLE_SQUAD):", "INF_RIFLE_SQUAD");
      if (!uid) return;
      const side = prompt("Enter Side (US / IT / GE):", "US");
      if (!side) return;
      const q = prompt("Enter Hex Q (column):", "0");
      if (q === null) return;
      const r = prompt("Enter Hex R (row):", "0");
      if (r === null) return;

      if (!currentScenarioData.units) currentScenarioData.units = [];
      currentScenarioData.units.push({
        unit_id: uid.trim(),
        side: side.trim().toUpperCase(),
        q: parseInt(q, 10) || 0,
        r: parseInt(r, 10) || 0,
        facing: 0,
        experience: "REGULAR",
        entry_turn: 1
      });
      renderScenarioUnitsTable();
      drawScenarioCanvas();
      syncScenarioJsonFromState();
    }

    function syncScenarioDataFromInputs() {
      if (!currentScenarioData) return;
      currentScenarioData.name = document.getElementById('scen-field-name').value;
      currentScenarioData.max_turns = parseInt(document.getElementById('scen-field-max-turns').value, 10) || 8;
      currentScenarioData.description = document.getElementById('scen-field-desc').value;
      if (!currentScenarioData.rules) currentScenarioData.rules = {};
      currentScenarioData.rules.attacker_morale_threshold = parseInt(document.getElementById('scen-field-atk-morale').value, 10) || 10;
      currentScenarioData.rules.defender_morale_threshold = parseInt(document.getElementById('scen-field-def-morale').value, 10) || 10;
      syncScenarioJsonFromState();
    }

    function syncScenarioJsonFromState() {
      document.getElementById('scenario-json-raw').value = JSON.stringify(currentScenarioData, null, 2);
    }

    function onScenarioJsonInput() {
      try {
        const parsed = JSON.parse(document.getElementById('scenario-json-raw').value);
        currentScenarioData = parsed;
        drawScenarioCanvas();
        renderScenarioUnitsTable();
        renderScenarioFortsTable();
        renderScenarioVpsTable();
        renderScenarioMapPieces();
        document.getElementById('scen-validation-box').innerText = '✓ JSON Syntax Valid';
        document.getElementById('scen-validation-box').style.background = '#064e3b';
        document.getElementById('scen-validation-box').style.color = '#6ee7b7';
      } catch (e) {
        document.getElementById('scen-validation-box').innerText = '⚠ Invalid JSON: ' + e.message;
        document.getElementById('scen-validation-box').style.background = '#7f1d1d';
        document.getElementById('scen-validation-box').style.color = '#fca5a5';
      }
    }

    // Modal Create Scenario
    function openNewScenarioModal() {
      document.getElementById('modal-new-scenario').style.display = 'flex';
      const sel = document.getElementById('new-scen-template');
      sel.innerHTML = '<option value="">-- Blank Scenario --</option>';
      scenarios.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.innerText = `${s.name || s.id} (${s.is_draft ? 'Draft' : 'Published'})`;
        sel.appendChild(opt);
      });
    }

    function closeNewScenarioModal() {
      document.getElementById('modal-new-scenario').style.display = 'none';
    }

    async function submitCreateScenario() {
      const id = document.getElementById('new-scen-id').value.trim();
      const name = document.getElementById('new-scen-name').value.trim() || id;
      const templateId = document.getElementById('new-scen-template').value;

      if (!id) {
        alert("Please enter a Scenario ID.");
        return;
      }

      let payload = {
        id,
        name,
        shape: [9, 8],
        max_turns: 8,
        description: "",
        map_pieces: [{ piece_id: "S2", origin: [0, 0] }],
        units: [],
        fortifications: [],
        victory_points: []
      };

      if (templateId) {
        const tRes = await fetch('/api/scenarios/' + templateId);
        const tData = await tRes.json();
        if (tData.ok) {
          payload = JSON.parse(JSON.stringify(tData.scenario));
          payload.id = id;
          payload.name = name;
        }
      }

      const res = await fetch('/api/scenarios/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.ok) {
        closeNewScenarioModal();
        showNotif("New draft scenario created.");
        currentScenarioId = id;
        await loadScenariosData();
        selectScenario(id);
      } else {
        alert("Error creating scenario: " + (data.error || 'Unknown'));
      }
    }

    async function saveCurrentScenarioDraft() {
      if (!currentScenarioData) return;
      syncScenarioDataFromInputs();

      const res = await fetch('/api/scenarios/draft/' + currentScenarioId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: currentScenarioData })
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("Scenario draft successfully saved.");
        await loadScenariosData();
      } else {
        alert("Failed to save draft.");
      }
    }

    async function deleteCurrentScenario() {
      if (!currentScenarioId || !confirm(`Delete draft scenario '${currentScenarioId}'?`)) return;
      const res = await fetch('/api/scenarios/draft/' + currentScenarioId, { method: 'DELETE' });
      if (res.ok) {
        showNotif("Draft scenario deleted.");
        currentScenarioId = null;
        currentScenarioData = null;
        document.getElementById('no-scenario-selection').style.display = 'flex';
        document.getElementById('scenario-editor-form').style.display = 'none';
        await loadScenariosData();
      }
    }

    async function cloneCurrentScenario() {
      if (!currentScenarioId) return;
      const newId = prompt("Enter cloned Scenario ID:", currentScenarioId + "_draft");
      if (!newId) return;

      const endpoint = currentScenarioData.is_draft ?
        `/api/scenarios/draft/${currentScenarioId}/clone` :
        `/api/scenarios/${currentScenarioId}/clone`;

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_id: newId })
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("Scenario cloned as draft.");
        currentScenarioId = newId;
        await loadScenariosData();
        selectScenario(newId);
      }
    }

    async function publishCurrentScenario() {
      if (!currentScenarioId) return;
      if (!currentScenarioData.is_draft) {
        alert("Scenario is already published.");
        return;
      }
      syncScenarioDataFromInputs();
      await saveCurrentScenarioDraft();

      const res = await fetch(`/api/scenarios/draft/${currentScenarioId}/publish`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showNotif("Scenario successfully published to engine!");
        await loadScenariosData();
        selectScenario(currentScenarioId);
      } else {
        alert("Publish failed: " + (data.error || 'Validation error'));
      }
    }

    function populateScenarioCatalogs() {
      // Available for dropdowns
    }

    // ==========================================
    // MAP PIECE EDITOR LOGIC
    // ==========================================
    async function loadMapPiecesData() {
      try {
        const res = await fetch('/api/map_pieces');
        const data = await res.json();
        if (data.ok) {
          mapPieces = data.pieces;
          updatePieceHeaderBadges();
          renderPieceSidebar();
          if (currentPieceId) {
            selectMapPiece(currentPieceId);
          } else if (mapPieces.length > 0) {
            selectMapPiece(mapPieces[0].id);
          }
        }
      } catch (e) {
        console.error('Failed to load map pieces', e);
      }
    }

    function updatePieceHeaderBadges() {
      const pubCount = mapPieces.filter(p => !p.is_draft).length;
      const draftCount = mapPieces.filter(p => p.is_draft).length;
      document.getElementById('piece-pub-badge').innerText = pubCount + ' Published';
      document.getElementById('piece-draft-badge').innerText = draftCount + ' Drafts';
      document.getElementById('count-pieces-all').innerText = mapPieces.length;
      document.getElementById('count-pieces-drafts').innerText = draftCount;
      document.getElementById('count-pieces-published').innerText = pubCount;
    }

    function setPieceFilter(filt) {
      pieceFilter = filt;
      ['all', 'drafts', 'published'].forEach(f => {
        const btn = document.getElementById('piece-filter-' + f);
        if (btn) btn.classList.toggle('active', f === filt);
      });
      renderPieceSidebar();
    }

    function filterPieces() {
      renderPieceSidebar();
    }

    function renderPieceSidebar() {
      const query = (document.getElementById('piece-search')?.value || '').toLowerCase().trim();
      const listEl = document.getElementById('piece-list');
      listEl.innerHTML = '';

      const filtered = mapPieces.filter(p => {
        if (pieceFilter === 'drafts' && !p.is_draft) return false;
        if (pieceFilter === 'published' && p.is_draft) return false;
        if (query && !p.id.toLowerCase().includes(query) && !p.description.toLowerCase().includes(query)) return false;
        return true;
      });

      if (filtered.length === 0) {
        listEl.innerHTML = '<li style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">No pieces match filter</li>';
        return;
      }

      filtered.forEach(p => {
        const li = document.createElement('li');
        li.className = 'unit-item' + (p.id === currentPieceId ? ' active' : '');
        li.onclick = () => selectMapPiece(p.id);

        const badgeClass = p.is_draft ? 'badge-staged' : 'badge-published';
        const badgeText = p.is_draft ? 'DRAFT' : 'PUBLISHED';

        li.innerHTML = `
          <div>
            <div class="name">Piece <b>${escapeHtml(p.id)}</b></div>
            <div class="meta">${p.shape[0]}x${p.shape[1]} &bull; ${p.hex_count} custom hexes &bull; ${p.edge_count} walls</div>
          </div>
          <span class="badge ${badgeClass}">${badgeText}</span>
        `;
        listEl.appendChild(li);
      });
    }

    async function selectMapPiece(pieceId) {
      currentPieceId = pieceId;
      renderPieceSidebar();

      try {
        const res = await fetch('/api/map_pieces/' + pieceId);
        const data = await res.json();
        if (data.ok) {
          currentPieceData = data.piece;
          displayPieceForm();
          autoFitPieceCamera();
          drawPieceCanvas();
        }
      } catch (e) {
        console.error('Failed to load piece detail', e);
      }
    }

    function displayPieceForm() {
      document.getElementById('no-piece-selection').style.display = 'none';
      const form = document.getElementById('piece-editor-form');
      form.style.display = 'flex';

      const p = currentPieceData;
      const isDraft = !!p.is_draft;

      document.getElementById('piece-id-title').innerText = p.id;
      document.getElementById('piece-shape-pill').innerText = `${p.shape[0]}x${p.shape[1]}`;
      const pill = document.getElementById('piece-status-pill');
      pill.innerText = isDraft ? 'DRAFT' : 'PUBLISHED';
      pill.className = 'badge ' + (isDraft ? 'badge-staged' : 'badge-published');

      document.getElementById('btn-delete-piece').style.display = isDraft ? 'inline-block' : 'none';

      document.getElementById('piece-hexes-count').innerText = (p.hexes || []).length;
      document.getElementById('piece-edges-count').innerText = (p.hex_edges || []).length;
      document.getElementById('piece-json-raw').value = JSON.stringify(p, null, 2);

      renderPieceHexesTable();
      renderPieceEdgesTable();
    }

    function switchPieceSubTab(tabName) {
      ['hexes', 'edges', 'json'].forEach(t => {
        document.getElementById('piece-subtab-' + t).classList.toggle('active', t === tabName);
        document.getElementById('piece-panel-' + t).style.display = (t === tabName ? 'flex' : 'none');
      });
    }

    function selectPieceTerrain(terrain, btnEl) {
      pieceActiveTerrain = terrain;
      pieceWallToolActive = false;
      document.querySelectorAll('.btn-palette').forEach(b => b.classList.remove('active'));
      if (btnEl) btnEl.classList.add('active');
      document.getElementById('piece-canvas-overlay').innerText = `Tool: Paint Terrain [${terrain.toUpperCase()}]. Click or drag over hexes.`;
    }

    function togglePieceWallTool(btnEl) {
      pieceWallToolActive = !pieceWallToolActive;
      document.querySelectorAll('.btn-palette').forEach(b => b.classList.remove('active'));
      if (pieceWallToolActive && btnEl) {
        btnEl.classList.add('active');
        document.getElementById('piece-canvas-overlay').innerText = 'Tool: Wall Edge Mode. Click near borders between two adjacent hexes to toggle walls.';
      } else {
        selectPieceTerrain(pieceActiveTerrain, document.querySelector(`.btn-palette[style*="${TERRAIN_COLORS[pieceActiveTerrain]}"]`));
      }
    }

    function autoFitPieceCamera() {
      if (!currentPieceData) return;
      const canvas = document.getElementById('pieceCanvas');
      if (!canvas) return;

      const [w, h] = currentPieceData.shape || [9, 8];
      const availW = canvas.width - 120;
      const availH = canvas.height - 80;

      const approxHexW = availW / (w + 0.5);
      const approxHexH = availH / (h * 1.5 + 0.5);
      const sizeFromW = approxHexW / Math.sqrt(3);
      const sizeFromH = approxHexH;

      pieceCanvasZoom = Math.max(16, Math.min(42, Math.floor(Math.min(sizeFromW, sizeFromH))));
      pieceOffsetX = Math.floor((canvas.width - (w + 0.5) * pieceCanvasZoom * Math.sqrt(3)) / 2) + 20;
      pieceOffsetY = 35;
      drawPieceCanvas();
    }

    function zoomPieceCanvas(factor) {
      pieceCanvasZoom = Math.max(14, Math.min(65, Math.round(pieceCanvasZoom * factor)));
      drawPieceCanvas();
    }

    function drawPieceCanvas() {
      const canvas = document.getElementById('pieceCanvas');
      if (!canvas || !currentPieceData) return;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const [cols, rows] = currentPieceData.shape || [9, 8];

      // Build sparse lookup
      const terrainLookup = {};
      const elevLookup = {};
      for (const hx of currentPieceData.hexes || []) {
        terrainLookup[hx.q + ',' + hx.r] = hx.terrain || 'clear';
        if (hx.elevation) elevLookup[hx.q + ',' + hx.r] = hx.elevation;
      }

      // 1. Draw Hexes
      for (let r = 0; r < rows; r++) {
        for (let q = 0; q < cols; q++) {
          const { x, y } = hexToPixel(q, r, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
          const t = terrainLookup[q + ',' + r] || 'clear';
          const el = elevLookup[q + ',' + r] || 0;

          const fillColor = TERRAIN_COLORS[t] || '#334155';
          const strokeColor = '#475569';

          drawPointyHex(ctx, x, y, pieceCanvasZoom, fillColor, strokeColor, 1);

          // Elevation
          if (el > 0) {
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText('+' + el, x + pieceCanvasZoom * 0.7, y - pieceCanvasZoom * 0.4);
          }

          // Coordinate label
          if (pieceCanvasZoom >= 16) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.45)';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`${q},${r}`, x, y - pieceCanvasZoom * 0.35);
          }

          // Terrain short badge
          const tShort = TERRAIN_SHORTS[t] || '';
          if (tShort && pieceCanvasZoom >= 18) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
            ctx.font = 'bold 9px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(tShort, x, y + pieceCanvasZoom * 0.4);
          }
        }
      }

      // 2. Draw Hex Edges (Walls)
      for (const ed of currentPieceData.hex_edges || []) {
        try {
          const [q1, r1] = ed.from.split(',').map(Number);
          const [q2, r2] = ed.to.split(',').map(Number);
          const p1 = hexToPixel(q1, r1, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
          const p2 = hexToPixel(q2, r2, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);

          const mx = (p1.x + p2.x) / 2;
          const my = (p1.y + p2.y) / 2;
          const dx = p2.x - p1.x;
          const dy = p2.y - p1.y;
          const len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len * (pieceCanvasZoom * 0.5);
          const ny = dx / len * (pieceCanvasZoom * 0.5);

          ctx.beginPath();
          ctx.moveTo(mx - nx, my - ny);
          ctx.lineTo(mx + nx, my + ny);
          ctx.strokeStyle = '#f59e0b';
          ctx.lineWidth = 4;
          ctx.stroke();
        } catch (e) {}
      }

      // 3. Hover outline
      if (hoveredPieceHex) {
        const { x, y } = hexToPixel(hoveredPieceHex.q, hoveredPieceHex.r, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
        drawPointyHex(ctx, x, y, pieceCanvasZoom, null, '#38bdf8', 2.5);
      }
    }

    // Piece Canvas Mouse Events
    const pieceCanvas = document.getElementById('pieceCanvas');
    if (pieceCanvas) {
      pieceCanvas.addEventListener('mousedown', e => {
        if (e.button === 1 || e.shiftKey) { // Pan with middle click or Shift
          isPiecePanning = true;
          piecePanStartX = e.clientX - pieceOffsetX;
          piecePanStartY = e.clientY - pieceOffsetY;
          pieceCanvas.style.cursor = 'grabbing';
          return;
        }

        // Left click: Paint terrain or toggle wall
        if (e.button === 0) {
          isPaintingPiece = true;
          applyPieceToolAtPoint(e.clientX, e.clientY);
        }
      });

      window.addEventListener('mouseup', () => {
        isPiecePanning = false;
        isPaintingPiece = false;
        if (pieceCanvas) pieceCanvas.style.cursor = 'crosshair';
      });

      pieceCanvas.addEventListener('mousemove', e => {
        if (isPiecePanning) {
          pieceOffsetX = e.clientX - piecePanStartX;
          pieceOffsetY = e.clientY - piecePanStartY;
          drawPieceCanvas();
          return;
        }

        const rect = pieceCanvas.getBoundingClientRect();
        const px = e.clientX - rect.left;
        const py = e.clientY - rect.top;
        const { q, r } = pixelToHex(px, py, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);

        if (!currentPieceData) return;
        const [w, h] = currentPieceData.shape || [9, 8];
        if (q >= 0 && q < w && r >= 0 && r < h) {
          hoveredPieceHex = { q, r };
        } else {
          hoveredPieceHex = null;
        }

        if (isPaintingPiece && !pieceWallToolActive) {
          applyPieceToolAtPoint(e.clientX, e.clientY);
        } else {
          drawPieceCanvas();
        }
      });

      pieceCanvas.addEventListener('wheel', e => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        pieceCanvasZoom = Math.max(14, Math.min(65, Math.round(pieceCanvasZoom * factor)));
        drawPieceCanvas();
      });
    }

    function applyPieceToolAtPoint(clientX, clientY) {
      if (!currentPieceData) return;
      const rect = pieceCanvas.getBoundingClientRect();
      const px = clientX - rect.left;
      const py = clientY - rect.top;
      const { q, r } = pixelToHex(px, py, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
      const [w, h] = currentPieceData.shape || [9, 8];

      if (q < 0 || q >= w || r < 0 || r >= h) return;

      if (pieceWallToolActive) {
        // Toggle wall with adjacent neighbor
        togglePieceWallNear(px, py, q, r);
        return;
      }

      // Paint terrain
      if (!currentPieceData.hexes) currentPieceData.hexes = [];
      const existingIdx = currentPieceData.hexes.findIndex(hx => hx.q === q && hx.r === r);

      if (pieceActiveTerrain === 'clear') {
        if (existingIdx >= 0) {
          currentPieceData.hexes.splice(existingIdx, 1);
        }
      } else {
        if (existingIdx >= 0) {
          currentPieceData.hexes[existingIdx].terrain = pieceActiveTerrain;
        } else {
          currentPieceData.hexes.push({ q, r, terrain: pieceActiveTerrain });
        }
      }

      document.getElementById('piece-hexes-count').innerText = currentPieceData.hexes.length;
      renderPieceHexesTable();
      syncPieceJsonFromState();
      drawPieceCanvas();
    }

    function togglePieceWallNear(px, py, q, r) {
      // Find closest neighbor
      const neighbors = [
        { q: q + 1, r: r },
        { q: q - 1, r: r },
        { q: (r % 2 === 0 ? q : q + 1), r: r - 1 },
        { q: (r % 2 === 0 ? q - 1 : q), r: r - 1 },
        { q: (r % 2 === 0 ? q : q + 1), r: r + 1 },
        { q: (r % 2 === 0 ? q - 1 : q), r: r + 1 }
      ];

      const centerP = hexToPixel(q, r, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
      let closestN = null;
      let minDist = 9999;

      for (const n of neighbors) {
        const [w, h] = currentPieceData.shape;
        if (n.q < 0 || n.q >= w || n.r < 0 || n.r >= h) continue;
        const np = hexToPixel(n.q, n.r, pieceCanvasZoom, pieceOffsetX, pieceOffsetY);
        const edgeMidX = (centerP.x + np.x) / 2;
        const edgeMidY = (centerP.y + np.y) / 2;
        const dist = Math.hypot(px - edgeMidX, py - edgeMidY);
        if (dist < minDist) {
          minDist = dist;
          closestN = n;
        }
      }

      if (closestN && minDist < pieceCanvasZoom * 0.75) {
        const k1 = `${q},${r}`;
        const k2 = `${closestN.q},${closestN.r}`;
        if (!currentPieceData.hex_edges) currentPieceData.hex_edges = [];

        const idx = currentPieceData.hex_edges.findIndex(e =>
          (e.from === k1 && e.to === k2) || (e.from === k2 && e.to === k1)
        );

        if (idx >= 0) {
          currentPieceData.hex_edges.splice(idx, 1);
        } else {
          currentPieceData.hex_edges.push({ from: k1, to: k2, feature: 'wall' });
        }

        document.getElementById('piece-edges-count').innerText = currentPieceData.hex_edges.length;
        renderPieceEdgesTable();
        syncPieceJsonFromState();
        drawPieceCanvas();
      }
    }

    function renderPieceHexesTable() {
      const tbody = document.getElementById('piece-hexes-tbody');
      tbody.innerHTML = '';
      (currentPieceData.hexes || []).forEach((hx, idx) => {
        const tr = document.createElement('tr');
        tr.style = 'border-bottom: 1px solid #334155;';
        tr.innerHTML = `
          <td style="padding: 0.25rem;"><b>${hx.q}, ${hx.r}</b></td>
          <td style="padding: 0.25rem;"><span class="badge badge-published" style="background:${TERRAIN_COLORS[hx.terrain] || '#334155'}; color:#fff;">${hx.terrain}</span></td>
          <td style="padding: 0.25rem;">
            <button type="button" class="btn-danger" style="padding: 0.15rem 0.4rem; font-size: 0.65rem;" onclick="removePieceHex(${idx})">🗑️</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function renderPieceEdgesTable() {
      const tbody = document.getElementById('piece-edges-tbody');
      tbody.innerHTML = '';
      (currentPieceData.hex_edges || []).forEach((ed, idx) => {
        const tr = document.createElement('tr');
        tr.style = 'border-bottom: 1px solid #334155;';
        tr.innerHTML = `
          <td style="padding: 0.25rem;">${ed.from}</td>
          <td style="padding: 0.25rem;">${ed.to}</td>
          <td style="padding: 0.25rem;"><span class="badge badge-staged">${ed.feature}</span></td>
          <td style="padding: 0.25rem;">
            <button type="button" class="btn-danger" style="padding: 0.15rem 0.4rem; font-size: 0.65rem;" onclick="removePieceEdge(${idx})">🗑️</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function removePieceHex(idx) {
      currentPieceData.hexes.splice(idx, 1);
      document.getElementById('piece-hexes-count').innerText = currentPieceData.hexes.length;
      renderPieceHexesTable();
      syncPieceJsonFromState();
      drawPieceCanvas();
    }

    function removePieceEdge(idx) {
      currentPieceData.hex_edges.splice(idx, 1);
      document.getElementById('piece-edges-count').innerText = currentPieceData.hex_edges.length;
      renderPieceEdgesTable();
      syncPieceJsonFromState();
      drawPieceCanvas();
    }

    function syncPieceJsonFromState() {
      document.getElementById('piece-json-raw').value = JSON.stringify(currentPieceData, null, 2);
    }

    function onPieceJsonInput() {
      try {
        const parsed = JSON.parse(document.getElementById('piece-json-raw').value);
        currentPieceData = parsed;
        drawPieceCanvas();
        renderPieceHexesTable();
        renderPieceEdgesTable();
      } catch (e) {}
    }

    // Modal Create Piece
    function openNewPieceModal() {
      document.getElementById('modal-new-piece').style.display = 'flex';
      const sel = document.getElementById('new-piece-template');
      sel.innerHTML = '<option value="">-- Blank Piece (Clear Terrain) --</option>';
      mapPieces.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.innerText = `Piece ${p.id} (${p.shape[0]}x${p.shape[1]}) - ${p.is_draft ? 'Draft' : 'Published'}`;
        sel.appendChild(opt);
      });
    }

    function closeNewPieceModal() {
      document.getElementById('modal-new-piece').style.display = 'none';
    }

    async function submitCreatePiece() {
      const id = document.getElementById('new-piece-id').value.trim();
      const w = parseInt(document.getElementById('new-piece-w').value, 10) || 9;
      const h = parseInt(document.getElementById('new-piece-h').value, 10) || 8;
      const desc = document.getElementById('new-piece-desc').value.trim() || `Map section ${w}x${h}`;
      const templateId = document.getElementById('new-piece-template').value;

      if (!id) {
        alert("Please enter a Map Piece ID.");
        return;
      }

      let payload = {
        id,
        description: desc,
        shape: [w, h],
        hexes: [],
        hex_edges: []
      };

      if (templateId) {
        const tRes = await fetch('/api/map_pieces/' + templateId);
        const tData = await tRes.json();
        if (tData.ok) {
          payload = JSON.parse(JSON.stringify(tData.piece));
          payload.id = id;
          payload.description = desc;
        }
      }

      const res = await fetch('/api/map_pieces/draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.ok) {
        closeNewPieceModal();
        showNotif("Map piece draft created.");
        currentPieceId = id;
        await loadMapPiecesData();
        selectMapPiece(id);
      } else {
        alert("Error creating piece draft: " + (data.error || 'Unknown'));
      }
    }

    async function saveCurrentPieceDraft() {
      if (!currentPieceData) return;
      const res = await fetch('/api/map_pieces/draft/' + currentPieceId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: currentPieceData })
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("Map piece draft saved.");
        await loadMapPiecesData();
      } else {
        alert("Failed to save piece draft.");
      }
    }

    async function deleteCurrentPiece() {
      if (!currentPieceId || !confirm(`Delete draft map piece '${currentPieceId}'?`)) return;
      const res = await fetch('/api/map_pieces/draft/' + currentPieceId, { method: 'DELETE' });
      if (res.ok) {
        showNotif("Draft piece deleted.");
        currentPieceId = null;
        currentPieceData = null;
        document.getElementById('no-piece-selection').style.display = 'flex';
        document.getElementById('piece-editor-form').style.display = 'none';
        await loadMapPiecesData();
      }
    }

    async function cloneCurrentPiece() {
      if (!currentPieceId) return;
      const newId = prompt("Enter cloned Map Piece ID:", currentPieceId + "_draft");
      if (!newId) return;

      const endpoint = currentPieceData.is_draft ?
        `/api/map_pieces/draft/${currentPieceId}/clone` :
        `/api/map_pieces/${currentPieceId}/clone`;

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_id: newId })
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("Map piece cloned as draft.");
        currentPieceId = newId;
        await loadMapPiecesData();
        selectMapPiece(newId);
      }
    }

    async function publishCurrentPiece() {
      if (!currentPieceId) return;
      if (!currentPieceData.is_draft) {
        alert("Map piece is already published.");
        return;
      }
      await saveCurrentPieceDraft();

      const res = await fetch(`/api/map_pieces/draft/${currentPieceId}/publish`, { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showNotif("Map piece published to catalog!");
        await loadMapPiecesData();
        selectMapPiece(currentPieceId);
      } else {
        alert("Publish failed: " + (data.error || 'Validation error'));
      }
    }


    function initApp() {
      loadData(0);
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initApp);
    } else {
      initApp();
    }
  </script>
</body>
</html>
"""


class UnitEditorHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        body = json.loads(raw_body) if raw_body else {}

        if path.startswith("/api/scenarios/draft/"):
            scen_id = path[len("/api/scenarios/draft/"):]
            try:
                res = scenario_editor_service.update_draft(scen_id, body.get("data", body))
                self._send_json(200, {"ok": True, "scenario": res})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/map_pieces/draft/"):
            pid = path[len("/api/map_pieces/draft/"):]
            try:
                res = map_piece_editor_service.update_draft(pid, body.get("data", body))
                self._send_json(200, {"ok": True, "piece": res})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/scenarios/draft/"):
            scen_id = path[len("/api/scenarios/draft/"):]
            ok = scenario_editor_service.delete_draft(scen_id)
            if ok:
                self._send_json(200, {"ok": True, "message": f"Draft scenario {scen_id} deleted"})
            else:
                self._send_json(404, {"ok": False, "detail": f"Draft scenario {scen_id} not found"})
            return

        if path.startswith("/api/map_pieces/draft/"):
            pid = path[len("/api/map_pieces/draft/"):]
            ok = map_piece_editor_service.delete_draft(pid)
            if ok:
                self._send_json(200, {"ok": True, "message": f"Draft map piece {pid} deleted"})
            else:
                self._send_json(404, {"ok": False, "detail": f"Draft map piece {pid} not found"})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if path == "/api/units/state":
            catalog = load_catalog()
            inventory = load_inventory()
            staging = load_staging()

            # Collect all existing traits from catalog + staging + standards
            all_traits = set(STANDARD_TRAITS)
            for u in catalog.get("units", {}).values():
                all_traits.update(u.get("traits", []))
            for u in staging.values():
                all_traits.update(u.get("traits", []))

            payload = {
                "catalog": catalog,
                "inventory": inventory.get("units", []),
                "staging": staging,
                "traits": sorted(list(all_traits)),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/catalogs":
            unit_cat = load_unit_catalog_dict()
            mp_cat = load_map_piece_catalog_dict()
            self._send_json(200, {
                "ok": True,
                "units": sorted(list(unit_cat.keys())),
                "map_pieces": sorted(list(mp_cat.keys())),
                "fortifications": sorted(list(VALID_FORTIFICATIONS)),
                "experiences": sorted(list(VALID_EXPERIENCES)),
                "sides": sorted(list(VALID_SIDES)),
                "terrains": sorted(list(VALID_TERRAINS)),
            })
            return

        if path == "/api/scenarios":
            scenarios = scenario_editor_service.list_scenarios()
            self._send_json(200, {"ok": True, "count": len(scenarios), "scenarios": scenarios})
            return

        if path.startswith("/api/scenarios/"):
            scen_id = path[len("/api/scenarios/"):]
            try:
                scen = scenario_editor_service.get_scenario(scen_id)
                if scen:
                    self._send_json(200, {"ok": True, "scenario": scen})
                else:
                    self._send_json(404, {"ok": False, "detail": f"Scenario {scen_id} not found"})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        if path == "/api/map_pieces":
            pieces = map_piece_editor_service.list_pieces()
            self._send_json(200, {"ok": True, "count": len(pieces), "pieces": pieces})
            return

        if path.startswith("/api/map_pieces/"):
            pid = path[len("/api/map_pieces/"):]
            try:
                p = map_piece_editor_service.get_piece(pid)
                if p:
                    self._send_json(200, {"ok": True, "piece": p})
                else:
                    self._send_json(404, {"ok": False, "detail": f"Map piece {pid} not found"})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        if path == "/api/formations":
            formations_data = load_formations()
            catalog = load_catalog()
            inv_data = load_formation_inventory()
            payload = {
                "formations": formations_data,
                "units": catalog.get("units", {}),
                "inventory": inv_data.get("cards", []),
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        # Serve static assets (images from assets/art/...)
        if path.startswith("/assets/art/"):
            rel_path = path.lstrip("/")
            full_path = (REPO_ROOT / rel_path).resolve()
            if full_path.exists() and full_path.is_file():
                ext = full_path.suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                with open(full_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length).decode("utf-8")
        body = json.loads(raw_body) if raw_body else {}

        # Scenario Editor POST Routes
        if path == "/api/scenarios/draft":
            try:
                data = body.get("data", body)
                scen_id = data.get("id") or body.get("id")
                created = scenario_editor_service.create_draft(scen_id, data)
                self._send_json(200, {"ok": True, "scenario": created})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/draft/") and path.endswith("/clone"):
            source_id = path[len("/api/scenarios/draft/"):-len("/clone")]
            try:
                cloned = scenario_editor_service.clone_scenario(source_id, body.get("new_id"), from_draft=True)
                self._send_json(200, {"ok": True, "scenario": cloned})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/") and path.endswith("/clone"):
            source_id = path[len("/api/scenarios/"):-len("/clone")]
            try:
                cloned = scenario_editor_service.clone_scenario(source_id, body.get("new_id"), from_draft=False)
                self._send_json(200, {"ok": True, "scenario": cloned})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/draft/") and path.endswith("/publish"):
            draft_id = path[len("/api/scenarios/draft/"):-len("/publish")]
            try:
                pub = scenario_editor_service.publish_scenario(draft_id)
                self._send_json(200, {"ok": True, "scenario": pub})
            except Exception as e:
                self._send_json(422, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/") and path.endswith("/unpublish"):
            scen_id = path[len("/api/scenarios/"):-len("/unpublish")]
            try:
                draft = scenario_editor_service.unpublish_scenario(scen_id)
                self._send_json(200, {"ok": True, "scenario": draft})
            except Exception as e:
                self._send_json(404, {"ok": False, "detail": str(e)})
            return

        if path == "/api/scenarios/validate":
            try:
                valid, errors = scenario_editor_service.validate_scenario(body.get("data", body))
                self._send_json(200, {"ok": True, "valid": valid, "errors": errors})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        # Map Piece Editor POST Routes
        if path == "/api/map_pieces/draft":
            try:
                data = body.get("data", body)
                pid = data.get("id") or body.get("id")
                created = map_piece_editor_service.create_draft(pid, data)
                self._send_json(200, {"ok": True, "piece": created})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/map_pieces/draft/") and path.endswith("/clone"):
            source_id = path[len("/api/map_pieces/draft/"):-len("/clone")]
            try:
                cloned = map_piece_editor_service.clone_piece(source_id, body.get("new_id"), from_draft=True)
                self._send_json(200, {"ok": True, "piece": cloned})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/map_pieces/") and path.endswith("/clone"):
            source_id = path[len("/api/map_pieces/"):-len("/clone")]
            try:
                cloned = map_piece_editor_service.clone_piece(source_id, body.get("new_id"), from_draft=False)
                self._send_json(200, {"ok": True, "piece": cloned})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/map_pieces/draft/") and path.endswith("/publish"):
            draft_id = path[len("/api/map_pieces/draft/"):-len("/publish")]
            try:
                pub = map_piece_editor_service.publish_piece(draft_id)
                self._send_json(200, {"ok": True, "piece": pub})
            except Exception as e:
                self._send_json(422, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/map_pieces/") and path.endswith("/unpublish"):
            pid = path[len("/api/map_pieces/"):-len("/unpublish")]
            try:
                draft = map_piece_editor_service.unpublish_piece(pid)
                self._send_json(200, {"ok": True, "piece": draft})
            except Exception as e:
                self._send_json(404, {"ok": False, "detail": str(e)})
            return

        if path == "/api/map_pieces/validate":
            try:
                valid, errors = map_piece_editor_service.validate_piece(body.get("data", body))
                self._send_json(200, {"ok": True, "valid": valid, "errors": errors})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        if path == "/api/units/stage":
            unit_id = body.get("id")
            data = body.get("data")
            if not unit_id or not data:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing id or data"}')
                return

            staging = load_staging()
            staging[unit_id] = data
            save_staging(staging)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        if path == "/api/units/publish":
            unit_id = body.get("id")
            data = body.get("data")
            if not unit_id or not data:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing id or data"}')
                return

            cat = load_catalog()
            cat["units"][unit_id] = data
            save_catalog(cat)

            staging = load_staging()
            if unit_id in staging:
                del staging[unit_id]
                save_staging(staging)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        if path == "/api/formations/save":
            formation_id = body.get("id", "").strip()
            data = body.get("data", {})
            if not formation_id:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing formation id"}')
                return

            line_units = list(data.get("line_units", []))
            heavy_weapons = list(data.get("heavy_weapons", []))
            specialists = list(data.get("specialists", []))
            all_units = list(data.get("units") or (line_units + heavy_weapons + specialists))

            formation_entry = {
                "name": data.get("name", formation_id.replace("_", " ").title()),
                "side": data.get("side", "US").upper(),
                "command_rating": int(data.get("command_rating", 8)),
                "command_points": int(data.get("command_points", 2)),
                "experience_level": str(data.get("experience_level", "REGULAR")).upper(),
                "experience_units_count": int(data.get("experience_units_count", 0)),
                "line_units": line_units,
                "heavy_weapons": heavy_weapons,
                "specialists": specialists,
                "units": all_units,
                "card_image": data.get("card_image", ""),
                "description": data.get("description", ""),
            }

            formations = load_formations()
            formations[formation_id] = formation_entry
            save_formations(formations)

            inv = load_formation_inventory()
            for c in inv.get("cards", []):
                if c.get("id") == formation_id or (formation_entry["card_image"] and c.get("card_image") == formation_entry["card_image"]):
                    c["catalog_key"] = formation_id
            save_formation_inventory(inv)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        if path == "/api/formations/delete":
            formation_id = body.get("id", "").strip()
            formations = load_formations()
            if formation_id in formations:
                del formations[formation_id]
                save_formations(formations)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        self.send_response(404)
        self.end_headers()


def run_server(port: int = 8780):
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("0.0.0.0", port), UnitEditorHandler)
    print(f"[*] Assault Unit & Formation Catalog Editor listening at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    run_server(args.port)
