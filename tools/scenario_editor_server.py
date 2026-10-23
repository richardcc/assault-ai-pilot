"""
tools/scenario_editor_server.py

Standalone Web GUI & REST Server for the Assault Tactical Scenario Editor.
Provides full scenario lifecycle editing:
1. Browse canonical published scenarios and editable draft scenarios.
2. Create new drafts from scratch or clone existing scenarios.
3. Visual and table editing of map pieces, hex coordinates, units, fortifications, VPs, morale tracks, and reinforcements.
4. Interactive HTML5 Hex Canvas for visual map layout and unit positioning.
5. Live schema validation and one-click publishing to assets/scenarios/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from assault_backend.services.scenario_editor_service import (
    scenario_editor_service,
    load_unit_catalog_dict,
    load_map_piece_catalog_dict,
    VALID_FORTIFICATIONS,
    VALID_EXPERIENCES,
    VALID_SIDES,
)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Assault - Tactical Scenario Editor</title>
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
      --side-us: #15803d;
      --side-it: #0284c7;
      --side-ge: #475569;
      --side-uk: #b45309;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 1.2rem; min-height: 100vh; display: flex; flex-direction: column; }
    
    header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 1.2rem; padding-bottom: 1rem; border-bottom: 1px solid var(--card-border);
      flex-wrap: wrap; gap: 1rem;
    }
    h1 { font-size: 1.4rem; color: #fff; display: flex; align-items: center; gap: 0.6rem; }
    .header-actions { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
    
    .btn {
      padding: 0.5rem 1rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem;
      border: 1px solid var(--card-border); background: #1e293b; color: #f8fafc; cursor: pointer;
      display: inline-flex; align-items: center; gap: 0.4rem; transition: all 0.15s ease;
    }
    .btn:hover { border-color: var(--accent); background: #334155; }
    .btn-primary { background: #0284c7; border-color: #38bdf8; }
    .btn-primary:hover { background: #0369a1; }
    .btn-success { background: #059669; border-color: #34d399; }
    .btn-success:hover { background: #047857; }
    .btn-warning { background: #d97706; border-color: #fbbf24; }
    .btn-warning:hover { background: #b45309; }
    .btn-danger { background: #dc2626; border-color: #f87171; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.75rem; }

    .badge {
      padding: 0.2rem 0.55rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 800;
      text-transform: uppercase; letter-spacing: 0.05em; display: inline-flex; align-items: center; gap: 0.3rem;
    }
    .badge-published { background: #064e3b; color: #6ee7b7; border: 1px solid #10b981; }
    .badge-draft { background: #78350f; color: #fde047; border: 1px solid #f59e0b; }
    
    .side-badge { padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 800; font-size: 0.75rem; }
    .side-US { background: #14532d; color: #86efac; border: 1px solid #22c55e; }
    .side-IT { background: #0c4a6e; color: #7dd3fc; border: 1px solid #0ea5e9; }
    .side-GE { background: #334155; color: #cbd5e1; border: 1px solid #94a3b8; }
    .side-UK { background: #713f12; color: #fde047; border: 1px solid #eab308; }

    .layout-container { display: grid; grid-template-columns: 340px 1fr; gap: 1.2rem; flex: 1; }
    
    /* Sidebar */
    .sidebar {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px;
      padding: 1rem; display: flex; flex-direction: column; gap: 0.8rem; max-height: calc(100vh - 120px);
    }
    .filter-pills { display: flex; gap: 0.4rem; }
    .filter-pill {
      flex: 1; text-align: center; padding: 0.35rem 0.5rem; font-size: 0.75rem; font-weight: 700;
      border-radius: 6px; background: #0f172a; border: 1px solid var(--card-border); color: var(--text-muted); cursor: pointer;
    }
    .filter-pill.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .search-input {
      width: 100%; padding: 0.5rem 0.8rem; background: #0f172a; border: 1px solid var(--card-border);
      border-radius: 6px; color: #fff; font-size: 0.85rem;
    }
    .scenario-list { display: flex; flex-direction: column; gap: 0.5rem; overflow-y: auto; flex: 1; }
    .scenario-item {
      padding: 0.75rem; background: #0f172a; border: 1px solid var(--card-border); border-radius: 6px;
      cursor: pointer; transition: all 0.15s; display: flex; flex-direction: column; gap: 0.4rem;
    }
    .scenario-item:hover { border-color: var(--accent); background: #1e293b; }
    .scenario-item.active { border-color: var(--accent); background: #172554; box-shadow: 0 0 10px rgba(14, 165, 233, 0.2); }
    .scenario-item-header { display: flex; justify-content: space-between; align-items: center; }
    .scenario-item-title { font-weight: 700; font-size: 0.9rem; color: #f8fafc; }
    .scenario-item-stats { display: flex; gap: 0.5rem; font-size: 0.75rem; color: var(--text-muted); }

    /* Main Editor Area */
    .editor-main {
      display: flex; flex-direction: column; gap: 1rem; background: var(--card-bg);
      border: 1px solid var(--card-border); border-radius: 8px; padding: 1.2rem;
      max-height: calc(100vh - 120px); overflow-y: auto;
    }
    
    .editor-tabs { display: flex; gap: 0.5rem; border-bottom: 1px solid var(--card-border); padding-bottom: 0.6rem; flex-wrap: wrap; }
    .tab-btn {
      padding: 0.5rem 1rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem;
      border: 1px solid var(--card-border); background: #0f172a; color: var(--text-muted); cursor: pointer;
    }
    .tab-btn:hover { color: #fff; border-color: var(--accent); }
    .tab-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }

    .tab-panel { display: none; flex-direction: column; gap: 1rem; }
    .tab-panel.active { display: flex; }

    /* Forms & Grids */
    .form-grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
    .form-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
    .form-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
    .form-group { display: flex; flex-direction: column; gap: 0.35rem; }
    label { font-size: 0.8rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
    input, select, textarea {
      padding: 0.5rem 0.75rem; background: #0f172a; border: 1px solid var(--card-border);
      border-radius: 6px; color: #fff; font-size: 0.85rem;
    }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent); }
    
    /* Tables */
    .data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .data-table th, .data-table td {
      padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid var(--card-border);
    }
    .data-table th { background: #0f172a; color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
    .data-table tr:hover { background: #26334d; }

    /* Canvas Map Preview */
    .canvas-container {
      position: relative; background: #080d1a; border: 1px solid var(--card-border);
      border-radius: 8px; overflow: hidden; height: 500px; display: flex; justify-content: center; align-items: center;
    }
    #hexCanvas { cursor: crosshair; }
    .canvas-controls {
      position: absolute; top: 10px; right: 10px; display: flex; gap: 0.4rem;
      background: rgba(15, 23, 42, 0.85); padding: 0.4rem; border-radius: 6px; border: 1px solid var(--card-border);
    }
    .hex-tooltip {
      position: absolute; bottom: 10px; left: 10px; background: rgba(15, 23, 42, 0.9);
      border: 1px solid var(--card-border); padding: 0.5rem 0.8rem; border-radius: 6px; font-size: 0.8rem;
    }

    /* Status & Validation Banners */
    .banner { padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.85rem; display: flex; align-items: center; gap: 0.6rem; }
    .banner-success { background: #064e3b; border: 1px solid #10b981; color: #a7f3d0; }
    .banner-error { background: #7f1d1d; border: 1px solid #ef4444; color: #fecaca; }
    .banner-info { background: #0c4a6e; border: 1px solid #0ea5e9; color: #bae6fd; }

    /* Modal */
    .modal-overlay {
      display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
      backdrop-filter: blur(3px); z-index: 100; justify-content: center; align-items: center;
    }
    .modal {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px;
      padding: 1.5rem; width: 500px; max-width: 90vw; display: flex; flex-direction: column; gap: 1rem;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 0.6rem; margin-top: 0.5rem; }
  </style>
</head>
<body>

  <header>
    <h1>
      <span>🗺️</span> Assault - Tactical Scenario Editor
      <span id="activeScenarioBadge" class="badge badge-draft">DRAFT</span>
    </h1>
    <div class="header-actions">
      <button class="btn" onclick="openNewModal()"><span>➕</span> New Draft</button>
      <button class="btn" onclick="cloneCurrentScenario()"><span>📋</span> Clone</button>
      <button class="btn btn-primary" onclick="saveDraft()"><span>💾</span> Save Draft (Ctrl+S)</button>
      <button class="btn btn-warning" onclick="validateCurrent()"><span>✔️</span> Validate</button>
      <button class="btn btn-success" onclick="publishScenario()"><span>🚀</span> Publish to Engine</button>
      <button class="btn btn-danger btn-sm" id="btnDeleteDraft" onclick="deleteDraft()"><span>🗑️</span> Delete Draft</button>
    </div>
  </header>

  <div class="layout-container">
    <!-- Sidebar: Scenarios List -->
    <div class="sidebar">
      <div class="filter-pills">
        <div class="filter-pill active" onclick="setFilter('all')">All</div>
        <div class="filter-pill" onclick="setFilter('draft')">Drafts</div>
        <div class="filter-pill" onclick="setFilter('published')">Published</div>
      </div>
      <input type="text" id="searchScenario" class="search-input" placeholder="Search scenarios..." oninput="renderScenarioList()">
      <div class="scenario-list" id="scenarioListContainer"></div>
    </div>

    <!-- Main Workspace -->
    <div class="editor-main">
      <div id="statusBanner" style="display: none;" class="banner"></div>

      <div class="editor-tabs">
        <button class="tab-btn active" onclick="switchTab('tabMap')">🗺️ Map & Canvas</button>
        <button class="tab-btn" onclick="switchTab('tabUnits')">⚔️ Order of Battle (Units)</button>
        <button class="tab-btn" onclick="switchTab('tabForts')">🛡️ Fortifications & VPs</button>
        <button class="tab-btn" onclick="switchTab('tabRules')">⚙️ Rules & Morale</button>
        <button class="tab-btn" onclick="switchTab('tabJson')">📄 Raw JSON</button>
      </div>

      <!-- Tab 1: Map & Canvas -->
      <div id="tabMap" class="tab-panel active">
        <div class="canvas-container">
          <canvas id="hexCanvas" width="900" height="500"></canvas>
          <div class="canvas-controls">
            <button class="btn btn-sm" onclick="zoomCanvas(1.15)">🔍+</button>
            <button class="btn btn-sm" onclick="zoomCanvas(0.85)">🔍-</button>
            <button class="btn btn-sm" onclick="resetCanvas()">↺ Reset</button>
          </div>
          <div class="hex-tooltip" id="hexTooltip">Hover over a hex to view details</div>
        </div>

        <div>
          <h3 style="font-size: 1rem; margin-bottom: 0.6rem; color: #fff;">Map Pieces Layout</h3>
          <div style="display: flex; gap: 0.6rem; margin-bottom: 0.8rem; align-items: flex-end;">
            <div class="form-group" style="flex: 2;">
              <label>Select Map Piece</label>
              <select id="selectMapPiece"></select>
            </div>
            <div class="form-group" style="flex: 1;">
              <label>Origin Q</label>
              <input type="number" id="pieceOriginQ" value="0">
            </div>
            <div class="form-group" style="flex: 1;">
              <label>Origin R</label>
              <input type="number" id="pieceOriginR" value="0">
            </div>
            <button class="btn btn-primary" onclick="addMapPiece()">Add Piece</button>
          </div>
          <table class="data-table">
            <thead>
              <tr><th>Piece ID</th><th>Origin [Q, R]</th><th>Shape</th><th>Actions</th></tr>
            </thead>
            <tbody id="mapPiecesTableBody"></tbody>
          </table>
        </div>
      </div>

      <!-- Tab 2: Units OOB -->
      <div id="tabUnits" class="tab-panel">
        <div style="background: #0f172a; padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
          <h3 style="font-size: 0.95rem; margin-bottom: 0.8rem; color: #fff;">Deploy New Unit</h3>
          <div class="form-grid-4">
            <div class="form-group">
              <label>Faction / Side</label>
              <select id="newUnitSide" onchange="filterUnitCatalogOptions()">
                <option value="US">US Army (Olive Green)</option>
                <option value="IT">Regio Esercito (Azure)</option>
                <option value="GE">Wehrmacht (Feldgrau)</option>
                <option value="UK">British Army (Khaki)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Unit Catalog Key</label>
              <select id="newUnitKey"></select>
            </div>
            <div class="form-group">
              <label>Unit ID</label>
              <input type="text" id="newUnitId" placeholder="e.g. US_1, IT_2">
            </div>
            <div class="form-group">
              <label>Experience</label>
              <select id="newUnitExp">
                <option value="REGULAR">REGULAR</option>
                <option value="HARDENED">HARDENED</option>
                <option value="VETERAN">VETERAN</option>
                <option value="RECRUIT">RECRUIT</option>
              </select>
            </div>
          </div>
          <div style="display: flex; gap: 0.8rem; margin-top: 0.8rem; align-items: flex-end;">
            <div class="form-group" style="width: 120px;">
              <label>Hex Q</label>
              <input type="number" id="newUnitQ" value="0">
            </div>
            <div class="form-group" style="width: 120px;">
              <label>Hex R</label>
              <input type="number" id="newUnitR" value="0">
            </div>
            <button class="btn btn-success" onclick="addUnit()">Deploy Unit</button>
          </div>
        </div>

        <div>
          <h3 style="font-size: 1rem; margin-bottom: 0.6rem; color: #fff;">Deployed Units Table (<span id="unitCountLabel">0</span>)</h3>
          <table class="data-table">
            <thead>
              <tr><th>Side</th><th>ID</th><th>Unit Key</th><th>Position [Q, R]</th><th>Experience</th><th>Actions</th></tr>
            </thead>
            <tbody id="unitsTableBody"></tbody>
          </table>
        </div>
      </div>

      <!-- Tab 3: Fortifications & VPs -->
      <div id="tabForts" class="tab-panel">
        <div class="form-grid-2">
          <!-- Fortifications -->
          <div style="background: #0f172a; padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
            <h3 style="font-size: 0.95rem; margin-bottom: 0.8rem; color: #fff;">Add Fortification</h3>
            <div class="form-group" style="margin-bottom: 0.6rem;">
              <label>Type</label>
              <select id="fortType"></select>
            </div>
            <div class="form-grid-3" style="margin-bottom: 0.6rem;">
              <div class="form-group">
                <label>Q</label>
                <input type="number" id="fortQ" value="0">
              </div>
              <div class="form-group">
                <label>R</label>
                <input type="number" id="fortR" value="0">
              </div>
              <div class="form-group">
                <label>Orientation</label>
                <input type="number" id="fortOrient" value="4" min="1" max="6">
              </div>
            </div>
            <button class="btn btn-primary" onclick="addFortification()">Place Fortification</button>

            <table class="data-table" style="margin-top: 1rem;">
              <thead>
                <tr><th>Type</th><th>[Q, R]</th><th>Orient</th><th>Actions</th></tr>
              </thead>
              <tbody id="fortsTableBody"></tbody>
            </table>
          </div>

          <!-- Victory Points -->
          <div style="background: #0f172a; padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
            <h3 style="font-size: 0.95rem; margin-bottom: 0.8rem; color: #fff;">Victory Point Hexes</h3>
            <div class="form-group" style="margin-bottom: 0.6rem;">
              <label>Default Value Per Hex</label>
              <input type="number" id="vpValuePerHex" value="2" onchange="updateVpDefault(this.value)">
            </div>
            <div class="form-grid-4" style="margin-bottom: 0.6rem;">
              <div class="form-group">
                <label>Q</label>
                <input type="number" id="newVpQ" value="0">
              </div>
              <div class="form-group">
                <label>R</label>
                <input type="number" id="newVpR" value="0">
              </div>
              <div class="form-group">
                <label>Owner</label>
                <select id="newVpOwner">
                  <option value="IT">IT</option>
                  <option value="US">US</option>
                  <option value="GE">GE</option>
                  <option value="UK">UK</option>
                </select>
              </div>
              <div class="form-group">
                <label>VP Value</label>
                <input type="number" id="newVpValue" value="2">
              </div>
            </div>
            <button class="btn btn-primary" onclick="addVpHex()">Place VP Hex</button>

            <table class="data-table" style="margin-top: 1rem;">
              <thead>
                <tr><th>[Q, R]</th><th>Initial Owner</th><th>Value</th><th>Actions</th></tr>
              </thead>
              <tbody id="vpsTableBody"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 4: Rules & Morale -->
      <div id="tabRules" class="tab-panel">
        <div class="form-grid-3">
          <div class="form-group">
            <label>Scenario ID</label>
            <input type="text" id="metaId" disabled>
          </div>
          <div class="form-group">
            <label>Scenario Title / Name</label>
            <input type="text" id="metaName">
          </div>
          <div class="form-group">
            <label>Max Turns</label>
            <input type="number" id="metaMaxTurns" min="1" max="30" value="8">
          </div>
        </div>

        <div class="form-group">
          <label>Historical Description & Objectives</label>
          <textarea id="metaDescription" rows="3"></textarea>
        </div>

        <div style="background: #0f172a; padding: 1rem; border-radius: 6px; border: 1px solid var(--card-border);">
          <h3 style="font-size: 0.95rem; margin-bottom: 0.8rem; color: #fff;">Morale Track Thresholds</h3>
          <div class="form-grid-2">
            <!-- Side 1 Morale -->
            <div style="border: 1px solid var(--card-border); padding: 0.8rem; border-radius: 6px;">
              <h4 style="font-size: 0.85rem; color: #86efac; margin-bottom: 0.6rem;">Allied Morale (US / UK)</h4>
              <div class="form-grid-4">
                <div class="form-group"><label>Start</label><input type="number" id="morUsStart" value="3"></div>
                <div class="form-group"><label>Retreat</label><input type="number" id="morUsRetreat" value="7"></div>
                <div class="form-group"><label>Rout</label><input type="number" id="morUsRout" value="9"></div>
                <div class="form-group"><label>Surrender</label><input type="number" id="morUsSurrender" value="11"></div>
              </div>
            </div>
            <!-- Side 2 Morale -->
            <div style="border: 1px solid var(--card-border); padding: 0.8rem; border-radius: 6px;">
              <h4 style="font-size: 0.85rem; color: #7dd3fc; margin-bottom: 0.6rem;">Axis Morale (IT / GE)</h4>
              <div class="form-grid-4">
                <div class="form-group"><label>Start</label><input type="number" id="morItStart" value="2"></div>
                <div class="form-group"><label>Retreat</label><input type="number" id="morItRetreat" value="6"></div>
                <div class="form-group"><label>Rout</label><input type="number" id="morItRout" value="7"></div>
                <div class="form-group"><label>Surrender</label><input type="number" id="morItSurrender" value="9"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab 5: Raw JSON -->
      <div id="tabJson" class="tab-panel">
        <div style="display: flex; gap: 0.6rem; justify-content: flex-end;">
          <button class="btn btn-sm" onclick="formatJsonTextarea()">Format JSON</button>
          <button class="btn btn-primary btn-sm" onclick="applyJsonToState()">Apply JSON to Form</button>
        </div>
        <textarea id="rawJsonTextarea" style="height: 480px; font-family: monospace; font-size: 0.85rem;" spellcheck="false"></textarea>
      </div>

    </div>
  </div>

  <!-- Modal: Create New Draft -->
  <div class="modal-overlay" id="newDraftModal">
    <div class="modal">
      <div class="modal-header">
        <h3 style="color: #fff; font-size: 1.1rem;">Create New Scenario Draft</h3>
        <button class="btn btn-sm" onclick="closeNewModal()">✕</button>
      </div>
      <div class="form-group">
        <label>New Scenario ID</label>
        <input type="text" id="modalDraftId" placeholder="e.g. draft_amphibious_assault_01">
      </div>
      <div class="form-group">
        <label>Scenario Name</label>
        <input type="text" id="modalDraftName" placeholder="e.g. Amphibious Assault on Beach Blue">
      </div>
      <div class="form-group">
        <label>Template / Base</label>
        <select id="modalDraftBase">
          <option value="">Empty Standard Template (1 Map Piece, 2 Units)</option>
        </select>
      </div>
      <div class="modal-actions">
        <button class="btn" onclick="closeNewModal()">Cancel</button>
        <button class="btn btn-primary" onclick="submitCreateDraft()">Create Draft</button>
      </div>
    </div>
  </div>

  <script>
    // State
    let activeFilter = 'all';
    let allScenarios = [];
    let currentScenario = null;
    let catalogs = { units: [], map_pieces: [], fortifications: [], experiences: [], sides: [] };

    // Canvas State
    let canvasZoom = 24; // hex radius in pixels
    let canvasOffsetX = 120;
    let canvasOffsetY = 80;
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;

    // Initialization
    window.addEventListener('DOMContentLoaded', async () => {
      await loadCatalogs();
      await fetchScenarios();
      setupCanvasEvents();
      setupKeyboardShortcuts();
    });

    function setupKeyboardShortcuts() {
      window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault();
          saveDraft();
        }
      });
    }

    async function loadCatalogs() {
      try {
        const res = await fetch('/api/catalogs');
        catalogs = await res.json();
        
        // Populate piece dropdown
        const pieceSel = document.getElementById('selectMapPiece');
        pieceSel.innerHTML = catalogs.map_pieces.map(p => `<option value="${p.id}">${p.id} - ${p.name} (${p.shape[0]}x${p.shape[1]})</option>`).join('');

        // Populate fort dropdown
        const fortSel = document.getElementById('fortType');
        fortSel.innerHTML = catalogs.fortifications.map(f => `<option value="${f}">${f.replace('_', ' ').toUpperCase()}</option>`).join('');

        filterUnitCatalogOptions();
      } catch (err) {
        console.error('Failed to load catalogs:', err);
      }
    }

    function filterUnitCatalogOptions() {
      const side = document.getElementById('newUnitSide').value;
      const unitSel = document.getElementById('newUnitKey');
      const filtered = catalogs.units.filter(u => !u.side || u.side === side);
      unitSel.innerHTML = filtered.map(u => `<option value="${u.key}">${u.key} (${u.name}) - ${u.default_role}</option>`).join('');
    }

    async function fetchScenarios() {
      try {
        const res = await fetch('/api/scenarios');
        const data = await res.json();
        allScenarios = data.scenarios || [];
        renderScenarioList();

        // Populate Clone/Base options in modal
        const baseSel = document.getElementById('modalDraftBase');
        baseSel.innerHTML = '<option value="">Empty Standard Template (1 Map Piece, 2 Units)</option>' +
          allScenarios.map(s => `<option value="${s.id}">Clone from: [${s.status.toUpperCase()}] ${s.name} (${s.id})</option>`).join('');

        // Select first if none selected
        if (!currentScenario && allScenarios.length > 0) {
          selectScenario(allScenarios[0].id);
        }
      } catch (err) {
        showBanner('Error loading scenarios: ' + err.message, 'error');
      }
    }

    function setFilter(filter) {
      activeFilter = filter;
      document.querySelectorAll('.filter-pill').forEach(el => {
        el.classList.toggle('active', el.textContent.toLowerCase() === filter);
      });
      renderScenarioList();
    }

    function renderScenarioList() {
      const container = document.getElementById('scenarioListContainer');
      const search = (document.getElementById('searchScenario').value || '').toLowerCase();

      const filtered = allScenarios.filter(s => {
        if (activeFilter === 'draft' && s.status !== 'draft') return false;
        if (activeFilter === 'published' && s.status !== 'published') return false;
        if (search && !s.name.toLowerCase().includes(search) && !s.id.toLowerCase().includes(search)) return false;
        return true;
      });

      container.innerHTML = filtered.map(s => {
        const isActive = currentScenario && currentScenario.id === s.id;
        const badgeCls = s.status === 'published' ? 'badge-published' : 'badge-draft';
        return `
          <div class="scenario-item ${isActive ? 'active' : ''}" onclick="selectScenario('${s.id}')">
            <div class="scenario-item-header">
              <span class="scenario-item-title">${s.name}</span>
              <span class="badge ${badgeCls}">${s.status}</span>
            </div>
            <div style="font-size: 0.75rem; color: #64748b; font-family: monospace;">${s.id}</div>
            <div class="scenario-item-stats">
              <span>⏱️ ${s.max_turns} turns</span>
              <span>⚔️ ${s.unit_count} units</span>
              <span>⭐ ${s.vp_count} VPs</span>
            </div>
          </div>
        `;
      }).join('');
    }

    async function selectScenario(scenarioId) {
      try {
        const res = await fetch('/api/scenarios/' + scenarioId);
        const data = await res.json();
        currentScenario = data.scenario;
        populateEditorForms();
        renderScenarioList();
        drawCanvas();
      } catch (err) {
        showBanner('Error loading scenario: ' + err.message, 'error');
      }
    }

    function populateEditorForms() {
      if (!currentScenario) return;
      
      const badge = document.getElementById('activeScenarioBadge');
      badge.textContent = (currentScenario.status || 'draft').toUpperCase();
      badge.className = 'badge ' + (currentScenario.status === 'published' ? 'badge-published' : 'badge-draft');

      const btnDel = document.getElementById('btnDeleteDraft');
      btnDel.style.display = currentScenario.status === 'draft' ? 'inline-flex' : 'none';

      // Rules / Meta tab
      document.getElementById('metaId').value = currentScenario.id || '';
      document.getElementById('metaName').value = currentScenario.name || currentScenario.id || '';
      document.getElementById('metaMaxTurns').value = currentScenario.max_turns || 8;
      document.getElementById('metaDescription').value = currentScenario.description || '';

      // Morale
      const mor = currentScenario.morale_track || {};
      const usMor = mor.US || { start: 3, retreat: 7, rout: 9, surrender: 11 };
      const itMor = mor.IT || { start: 2, retreat: 6, rout: 7, surrender: 9 };
      document.getElementById('morUsStart').value = usMor.start || 3;
      document.getElementById('morUsRetreat').value = usMor.retreat || 7;
      document.getElementById('morUsRout').value = usMor.rout || 9;
      document.getElementById('morUsSurrender').value = usMor.surrender || 11;
      document.getElementById('morItStart').value = itMor.start || 2;
      document.getElementById('morItRetreat').value = itMor.retreat || 6;
      document.getElementById('morItRout').value = itMor.rout || 7;
      document.getElementById('morItSurrender').value = itMor.surrender || 9;

      // Map Pieces Table
      renderMapPiecesTable();

      // Units Table
      renderUnitsTable();

      // Forts & VPs Table
      renderFortsAndVpsTable();

      // JSON tab
      document.getElementById('rawJsonTextarea').value = JSON.stringify(currentScenario, null, 2);
    }

    function renderMapPiecesTable() {
      const tbody = document.getElementById('mapPiecesTableBody');
      const pieces = currentScenario.map?.pieces || [];
      tbody.innerHTML = pieces.map((p, idx) => `
        <tr>
          <td><strong>${p.id}</strong></td>
          <td>[${p.origin ? p.origin[0] : 0}, ${p.origin ? p.origin[1] : 0}]</td>
          <td>Tile</td>
          <td><button class="btn btn-danger btn-sm" onclick="removeMapPiece(${idx})">✕</button></td>
        </tr>
      `).join('');
    }

    function renderUnitsTable() {
      const tbody = document.getElementById('unitsTableBody');
      const units = currentScenario.units || [];
      document.getElementById('unitCountLabel').textContent = units.length;

      tbody.innerHTML = units.map((u, idx) => `
        <tr>
          <td><span class="side-badge side-${u.side}">${u.side}</span></td>
          <td><strong>${u.unit_id}</strong></td>
          <td>${u.unit_key}</td>
          <td>[${u.position[0]}, ${u.position[1]}]</td>
          <td><span class="badge" style="background: #334155; color: #fff;">${u.experience}</span></td>
          <td><button class="btn btn-danger btn-sm" onclick="removeUnit(${idx})">✕ Remove</button></td>
        </tr>
      `).join('');
    }

    function renderFortsAndVpsTable() {
      const fortBody = document.getElementById('fortsTableBody');
      const forts = currentScenario.map?.fortifications || [];
      fortBody.innerHTML = forts.map((f, idx) => `
        <tr>
          <td><strong>${f.type}</strong></td>
          <td>[${f.q}, ${f.r}]</td>
          <td>${f.orientation || 4}</td>
          <td><button class="btn btn-danger btn-sm" onclick="removeFortification(${idx})">✕</button></td>
        </tr>
      `).join('');

      const vpBody = document.getElementById('vpsTableBody');
      const vps = currentScenario.vp?.hexes || [];
      document.getElementById('vpValuePerHex').value = currentScenario.vp?.value_per_hex || 2;
      vpBody.innerHTML = vps.map((v, idx) => `
        <tr>
          <td>[${v.q}, ${v.r}]</td>
          <td><span class="side-badge side-${v.initial_owner}">${v.initial_owner}</span></td>
          <td><strong>${v.value || 2} VP</strong></td>
          <td><button class="btn btn-danger btn-sm" onclick="removeVpHex(${idx})">✕</button></td>
        </tr>
      `).join('');
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.querySelector(`button[onclick="switchTab('${tabId}')"]`).classList.add('active');
      document.getElementById(tabId).classList.add('active');
      if (tabId === 'tabMap') drawCanvas();
      if (tabId === 'tabJson') {
        syncFormToState();
        document.getElementById('rawJsonTextarea').value = JSON.stringify(currentScenario, null, 2);
      }
    }

    function syncFormToState() {
      if (!currentScenario) return;
      currentScenario.name = document.getElementById('metaName').value;
      currentScenario.max_turns = parseInt(document.getElementById('metaMaxTurns').value, 10) || 8;
      currentScenario.description = document.getElementById('metaDescription').value;

      currentScenario.morale_track = {
        US: {
          start: parseInt(document.getElementById('morUsStart').value, 10) || 3,
          retreat: parseInt(document.getElementById('morUsRetreat').value, 10) || 7,
          rout: parseInt(document.getElementById('morUsRout').value, 10) || 9,
          surrender: parseInt(document.getElementById('morUsSurrender').value, 10) || 11,
        },
        IT: {
          start: parseInt(document.getElementById('morItStart').value, 10) || 2,
          retreat: parseInt(document.getElementById('morItRetreat').value, 10) || 6,
          rout: parseInt(document.getElementById('morItRout').value, 10) || 7,
          surrender: parseInt(document.getElementById('morItSurrender').value, 10) || 9,
        }
      };
    }

    function addMapPiece() {
      const pid = document.getElementById('selectMapPiece').value;
      const q = parseInt(document.getElementById('pieceOriginQ').value, 10) || 0;
      const r = parseInt(document.getElementById('pieceOriginR').value, 10) || 0;
      if (!currentScenario.map) currentScenario.map = { pieces: [], fortifications: [] };
      if (!currentScenario.map.pieces) currentScenario.map.pieces = [];
      currentScenario.map.pieces.push({ id: pid, origin: [q, r] });
      renderMapPiecesTable();
      drawCanvas();
    }

    function removeMapPiece(idx) {
      currentScenario.map.pieces.splice(idx, 1);
      renderMapPiecesTable();
      drawCanvas();
    }

    function addUnit() {
      const side = document.getElementById('newUnitSide').value;
      const key = document.getElementById('newUnitKey').value;
      let uid = document.getElementById('newUnitId').value.trim();
      const exp = document.getElementById('newUnitExp').value;
      const q = parseInt(document.getElementById('newUnitQ').value, 10) || 0;
      const r = parseInt(document.getElementById('newUnitR').value, 10) || 0;

      if (!uid) {
        const count = (currentScenario.units || []).filter(u => u.side === side).length + 1;
        uid = `${side}_${count}`;
      }

      if (!currentScenario.units) currentScenario.units = [];
      currentScenario.units.push({
        unit_id: uid,
        side: side,
        unit_key: key,
        position: [q, r],
        experience: exp
      });
      renderUnitsTable();
      drawCanvas();
      showBanner(`Unit ${uid} deployed at [${q}, ${r}]`, 'info');
    }

    function removeUnit(idx) {
      currentScenario.units.splice(idx, 1);
      renderUnitsTable();
      drawCanvas();
    }

    function addFortification() {
      const type = document.getElementById('fortType').value;
      const q = parseInt(document.getElementById('fortQ').value, 10) || 0;
      const r = parseInt(document.getElementById('fortR').value, 10) || 0;
      const orient = parseInt(document.getElementById('fortOrient').value, 10) || 4;

      if (!currentScenario.map) currentScenario.map = { pieces: [], fortifications: [] };
      if (!currentScenario.map.fortifications) currentScenario.map.fortifications = [];
      currentScenario.map.fortifications.push({
        type: type,
        q: q,
        r: r,
        orientation: orient,
        vertex_start: 1,
        vertex_end: 2
      });
      renderFortsAndVpsTable();
      drawCanvas();
    }

    function removeFortification(idx) {
      currentScenario.map.fortifications.splice(idx, 1);
      renderFortsAndVpsTable();
      drawCanvas();
    }

    function updateVpDefault(val) {
      if (!currentScenario.vp) currentScenario.vp = { value_per_hex: 2, hexes: [] };
      currentScenario.vp.value_per_hex = parseInt(val, 10) || 2;
    }

    function addVpHex() {
      const q = parseInt(document.getElementById('newVpQ').value, 10) || 0;
      const r = parseInt(document.getElementById('newVpR').value, 10) || 0;
      const owner = document.getElementById('newVpOwner').value;
      const val = parseInt(document.getElementById('newVpValue').value, 10) || 2;

      if (!currentScenario.vp) currentScenario.vp = { value_per_hex: 2, hexes: [] };
      if (!currentScenario.vp.hexes) currentScenario.vp.hexes = [];
      currentScenario.vp.hexes.push({ q: q, r: r, initial_owner: owner, value: val });
      renderFortsAndVpsTable();
      drawCanvas();
    }

    function removeVpHex(idx) {
      currentScenario.vp.hexes.splice(idx, 1);
      renderFortsAndVpsTable();
      drawCanvas();
    }

    // Save & Publish API
    async function saveDraft() {
      if (!currentScenario) return;
      syncFormToState();

      try {
        const res = await fetch('/api/scenarios/draft/' + currentScenario.id, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: currentScenario })
        });
        const resData = await res.json();
        if (!res.ok) throw new Error(resData.detail || 'Save failed');

        currentScenario = resData.scenario;
        populateEditorForms();
        await fetchScenarios();
        showBanner(`Draft '${currentScenario.id}' saved successfully to assets/scenarios/drafts/.`, 'success');
      } catch (err) {
        showBanner('Error saving draft: ' + err.message, 'error');
      }
    }

    async function validateCurrent() {
      syncFormToState();
      try {
        const res = await fetch('/api/scenarios/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: currentScenario })
        });
        const resData = await res.json();
        if (resData.valid) {
          const warnText = resData.warnings.length ? `<br><small>Warnings: ${resData.warnings.join(', ')}</small>` : '';
          showBanner(`Scenario is 100% valid! Ready to publish to engine.${warnText}`, 'success');
        } else {
          showBanner(`Validation failed:<br>• ${resData.errors.join('<br>• ')}`, 'error');
        }
      } catch (err) {
        showBanner('Validation error: ' + err.message, 'error');
      }
    }

    async function publishScenario() {
      if (!currentScenario) return;
      syncFormToState();
      await saveDraft();

      if (!confirm(`Publish draft '${currentScenario.id}' to canonical assets/scenarios/ ?\\n\\nThis will make it immediately available to the engine and AI runtime.`)) {
        return;
      }

      try {
        const res = await fetch(`/api/scenarios/draft/${currentScenario.id}/publish`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const resData = await res.json();
        if (!res.ok) throw new Error(resData.detail || 'Publish failed');

        await selectScenario(resData.id);
        await fetchScenarios();
        showBanner(`🚀 Scenario '${resData.id}' published successfully! Path: ${resData.published_path}`, 'success');
      } catch (err) {
        showBanner('Failed to publish: ' + err.message, 'error');
      }
    }

    async function deleteDraft() {
      if (!currentScenario || currentScenario.status !== 'draft') return;
      if (!confirm(`Are you sure you want to permanently delete draft '${currentScenario.id}'?`)) return;

      try {
        const res = await fetch(`/api/scenarios/draft/${currentScenario.id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Delete failed');
        showBanner(`Draft '${currentScenario.id}' deleted.`, 'info');
        currentScenario = null;
        await fetchScenarios();
      } catch (err) {
        showBanner('Error deleting draft: ' + err.message, 'error');
      }
    }

    function cloneCurrentScenario() {
      if (!currentScenario) return;
      const cloneId = prompt(`Enter new scenario ID to clone '${currentScenario.id}':`, `${currentScenario.id}_clone`);
      if (!cloneId) return;

      openNewModal(cloneId, `Clone of ${currentScenario.name || currentScenario.id}`, currentScenario.id);
    }

    function openNewModal(defaultId = '', defaultName = '', defaultBase = '') {
      document.getElementById('modalDraftId').value = defaultId || `draft_scenario_${Date.now().toString().slice(-4)}`;
      document.getElementById('modalDraftName').value = defaultName || 'New Tactical Scenario';
      if (defaultBase) document.getElementById('modalDraftBase').value = defaultBase;
      document.getElementById('newDraftModal').style.display = 'flex';
    }

    function closeNewModal() {
      document.getElementById('newDraftModal').style.display = 'none';
    }

    async function submitCreateDraft() {
      const id = document.getElementById('modalDraftId').value.trim();
      const name = document.getElementById('modalDraftName').value.trim();
      const cloneFrom = document.getElementById('modalDraftBase').value;

      if (!id) {
        alert('Please enter a scenario ID.');
        return;
      }

      try {
        const res = await fetch('/api/scenarios/draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: id,
            name: name,
            clone_from_id: cloneFrom || null
          })
        });
        const resData = await res.json();
        if (!res.ok) throw new Error(resData.detail || 'Creation failed');

        closeNewModal();
        await fetchScenarios();
        await selectScenario(id);
        showBanner(`New draft scenario '${id}' created!`, 'success');
      } catch (err) {
        alert('Failed to create draft: ' + err.message);
      }
    }

    function formatJsonTextarea() {
      try {
        const ta = document.getElementById('rawJsonTextarea');
        const parsed = JSON.parse(ta.value);
        ta.value = JSON.stringify(parsed, null, 2);
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
      }
    }

    function applyJsonToState() {
      try {
        const ta = document.getElementById('rawJsonTextarea');
        currentScenario = JSON.parse(ta.value);
        populateEditorForms();
        drawCanvas();
        showBanner('Raw JSON applied to editor forms.', 'info');
      } catch (e) {
        alert('Invalid JSON: ' + e.message);
      }
    }

    function showBanner(msg, type = 'info') {
      const banner = document.getElementById('statusBanner');
      banner.className = `banner banner-${type}`;
      banner.innerHTML = msg;
      banner.style.display = 'flex';
      setTimeout(() => { banner.style.display = 'none'; }, 6000);
    }

    // HTML5 Hex Canvas Rendering
    function setupCanvasEvents() {
      const canvas = document.getElementById('hexCanvas');
      canvas.addEventListener('mousedown', (e) => {
        isDragging = true;
        dragStartX = e.clientX - canvasOffsetX;
        dragStartY = e.clientY - canvasOffsetY;
      });
      window.addEventListener('mouseup', () => { isDragging = false; });
      canvas.addEventListener('mousemove', (e) => {
        if (isDragging) {
          canvasOffsetX = e.clientX - dragStartX;
          canvasOffsetY = e.clientY - dragStartY;
          drawCanvas();
        } else {
          handleCanvasHover(e);
        }
      });
      canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        zoomCanvas(factor);
      });
      canvas.addEventListener('click', (e) => {
        handleCanvasClick(e);
      });
    }

    function zoomCanvas(factor) {
      canvasZoom = Math.max(14, Math.min(60, canvasZoom * factor));
      drawCanvas();
    }

    function resetCanvas() {
      canvasZoom = 24;
      canvasOffsetX = 120;
      canvasOffsetY = 80;
      drawCanvas();
    }

    function hexToPixel(q, r) {
      const size = canvasZoom;
      const x = size * (Math.sqrt(3) * q + Math.sqrt(3)/2 * r) + canvasOffsetX;
      const y = size * (3/2 * r) + canvasOffsetY;
      return { x, y };
    }

    function pixelToHex(x, y) {
      const size = canvasZoom;
      const px = x - canvasOffsetX;
      const py = y - canvasOffsetY;
      const q = (Math.sqrt(3)/3 * px - 1/3 * py) / size;
      const r = (2/3 * py) / size;
      return axialRound(q, r);
    }

    function axialRound(x, y) {
      let xgrid = Math.round(x);
      let ygrid = Math.round(y);
      x -= xgrid;
      y -= ygrid;
      const dx = Math.round(x + 0.5 * y) * (x*x >= y*y ? 1 : 0);
      const dy = Math.round(y + 0.5 * x) * (x*x < y*y ? 1 : 0);
      return { q: xgrid + dx, r: ygrid + dy };
    }

    function drawCanvas() {
      const canvas = document.getElementById('hexCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (!currentScenario) return;

      const shape = currentScenario.shape || [18, 12];
      const maxQ = shape[0] || 18;
      const maxR = shape[1] || 12;

      // Draw Grid
      for (let r = 0; r < maxR; r++) {
        for (let q = 0; q < maxQ; q++) {
          drawHex(ctx, q, r, '#1e293b', '#0f172a');
        }
      }

      // Draw Fortifications
      (currentScenario.map?.fortifications || []).forEach(f => {
        const pt = hexToPixel(f.q, f.r);
        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(pt.x, pt.y - canvasZoom*0.35, canvasZoom*0.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#000';
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🛡️', pt.x, pt.y - canvasZoom*0.25);
      });

      // Draw VPs
      (currentScenario.vp?.hexes || []).forEach(v => {
        const pt = hexToPixel(v.q, v.r);
        ctx.fillStyle = v.initial_owner === 'US' ? '#22c55e' : (v.initial_owner === 'IT' ? '#38bdf8' : '#eab308');
        ctx.beginPath();
        ctx.arc(pt.x, pt.y + canvasZoom*0.35, canvasZoom*0.25, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#000';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`★${v.value || 2}`, pt.x, pt.y + canvasZoom*0.42);
      });

      // Draw Units
      (currentScenario.units || []).forEach(u => {
        const pt = hexToPixel(u.position[0], u.position[1]);
        const sideColor = u.side === 'US' ? '#15803d' : (u.side === 'IT' ? '#0284c7' : (u.side === 'GE' ? '#475569' : '#b45309'));
        
        ctx.fillStyle = sideColor;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, canvasZoom * 0.45, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#fff';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(u.unit_id, pt.x, pt.y + 3);
      });
    }

    function drawHex(ctx, q, r, strokeColor, fillColor) {
      const size = canvasZoom;
      const pt = hexToPixel(q, r);

      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6;
        const hx = pt.x + size * Math.cos(angle);
        const hy = pt.y + size * Math.sin(angle);
        if (i === 0) ctx.moveTo(hx, hy);
        else ctx.lineTo(hx, hy);
      }
      ctx.closePath();
      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Coordinates text
      ctx.fillStyle = '#475569';
      ctx.font = '8px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${q},${r}`, pt.x, pt.y + size * 0.65);
    }

    function handleCanvasHover(e) {
      const rect = e.target.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const hex = pixelToHex(x, y);

      const tooltip = document.getElementById('hexTooltip');
      if (!currentScenario) return;

      const unitsHere = (currentScenario.units || []).filter(u => u.position[0] === hex.q && u.position[1] === hex.r);
      const fortsHere = (currentScenario.map?.fortifications || []).filter(f => f.q === hex.q && f.r === hex.r);
      const vpsHere = (currentScenario.vp?.hexes || []).filter(v => v.q === hex.q && v.r === hex.r);

      let text = `Hex [Q: ${hex.q}, R: ${hex.r}]`;
      if (unitsHere.length) text += ` | Units: ${unitsHere.map(u => `${u.unit_id} (${u.unit_key})`).join(', ')}`;
      if (fortsHere.length) text += ` | Fort: ${fortsHere.map(f => f.type).join(', ')}`;
      if (vpsHere.length) text += ` | ⭐ VP: ${vpsHere.map(v => `${v.value || 2}pts (${v.initial_owner})`).join(', ')}`;

      tooltip.textContent = text;
    }

    function handleCanvasClick(e) {
      const rect = e.target.getBoundingClientRect();
      const hex = pixelToHex(e.clientX - rect.left, e.clientY - rect.top);
      document.getElementById('newUnitQ').value = hex.q;
      document.getElementById('newUnitR').value = hex.r;
      document.getElementById('fortQ').value = hex.q;
      document.getElementById('fortR').value = hex.r;
      document.getElementById('newVpQ').value = hex.q;
      document.getElementById('newVpR').value = hex.r;
    }
  </script>
</body>
</html>
"""


class ScenarioEditorHandler(BaseHTTPRequestHandler):
    """
    HTTP Request Handler serving the Scenario Editor Web GUI and REST endpoints.
    """

    def _send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            return json.loads(body.decode("utf-8"))
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if path == "/api/catalogs":
            unit_cat = load_unit_catalog_dict()
            piece_cat = load_map_piece_catalog_dict()
            data = {
                "ok": True,
                "units": [
                    {
                        "key": k,
                        "name": v.get("name", k),
                        "side": v.get("side", ""),
                        "default_role": v.get("doctrine_profile", {}).get("default_role", "SCREEN"),
                    }
                    for k, v in sorted(unit_cat.items())
                ],
                "map_pieces": [
                    {
                        "id": k,
                        "name": v.get("name", k),
                        "shape": v.get("shape", [9, 8]),
                    }
                    for k, v in sorted(piece_cat.items())
                ],
                "fortifications": sorted(list(VALID_FORTIFICATIONS)),
                "experiences": sorted(list(VALID_EXPERIENCES)),
                "sides": sorted(list(VALID_SIDES)),
            }
            self._send_json(200, data)
            return

        if path == "/api/scenarios":
            scenarios = scenario_editor_service.list_all_scenarios()
            self._send_json(200, {"ok": True, "count": len(scenarios), "scenarios": scenarios})
            return

        if path.startswith("/api/scenarios/"):
            scen_id = path[len("/api/scenarios/"):]
            try:
                scenario = scenario_editor_service.get_scenario(scen_id, prefer_draft=True)
                self._send_json(200, {"ok": True, "scenario": scenario})
            except FileNotFoundError as e:
                self._send_json(404, {"ok": False, "detail": str(e)})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/scenarios/draft":
            body = self._read_json()
            try:
                res = scenario_editor_service.create_draft(
                    scenario_id=body.get("id"),
                    data=body.get("data"),
                    clone_from_id=body.get("clone_from_id"),
                )
                if body.get("name") and not body.get("clone_from_id"):
                    res["name"] = body.get("name")
                    res = scenario_editor_service.update_draft(body.get("id"), res)
                self._send_json(200, {"ok": True, "scenario": res})
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/draft/") and path.endswith("/publish"):
            scen_id = path[len("/api/scenarios/draft/"):-len("/publish")]
            body = self._read_json()
            try:
                res = scenario_editor_service.publish_draft(scen_id, target_id=body.get("target_id"))
                self._send_json(200, res)
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path.startswith("/api/scenarios/unpublish/"):
            scen_id = path[len("/api/scenarios/unpublish/"):]
            try:
                res = scenario_editor_service.unpublish_scenario(scen_id)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(400, {"ok": False, "detail": str(e)})
            return

        if path == "/api/scenarios/validate":
            body = self._read_json()
            try:
                res = scenario_editor_service.validate_scenario(body.get("data", {}))
                self._send_json(200, res)
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/scenarios/draft/"):
            scen_id = path[len("/api/scenarios/draft/"):]
            body = self._read_json()
            try:
                res = scenario_editor_service.update_draft(scen_id, body.get("data", {}))
                self._send_json(200, {"ok": True, "scenario": res})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path.startswith("/api/scenarios/draft/"):
            scen_id = path[len("/api/scenarios/draft/"):]
            try:
                deleted = scenario_editor_service.delete_draft(scen_id)
                if not deleted:
                    self._send_json(404, {"ok": False, "detail": "Draft not found"})
                else:
                    self._send_json(200, {"ok": True, "message": "Draft deleted successfully."})
            except Exception as e:
                self._send_json(500, {"ok": False, "detail": str(e)})
            return

        self._send_json(404, {"ok": False, "detail": "Not found"})


def run_editor_server(host: str = "127.0.0.1", port: int = 8782):
    server = ThreadingHTTPServer((host, port), ScenarioEditorHandler)
    print(f"[ScenarioEditor] Running Tactical Scenario Editor at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ScenarioEditor] Shutting down server gracefully...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assault Tactical Scenario Editor Web GUI & Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8782, help="Port to listen on (default: 8782)")
    args = parser.parse_args()

    run_editor_server(args.host, args.port)
