"""
tools/unit_editor_server.py

Standalone Web GUI / REST Server for the Assault Unit Catalog Editor.
Workflow:
1. Loads current assets/catalogs/unit_catalog.json and assets/catalogs/unit_art_inventory.json.
2. Supports staging proposed unit definitions (pending review).
3. Serves an interactive Web UI with card/counter previews, side-by-side visual editing of stats,
   interactive attacks & range bands table with die badges, visual trait chip selector & custom trait adder.
4. Auto-saves approved / edited units directly to assets/catalogs/unit_catalog.json with full validation.
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
CATALOG_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_catalog.json"
INVENTORY_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_art_inventory.json"
STAGING_PATH = REPO_ROOT / "assets" / "catalogs" / "unit_staging_proposals.json"

STANDARD_TRAITS = [
    "ANTI_TANK",
    "ASSAULT",
    "CAMOUFLAGED",
    "CONCEALED",
    "EXPLOSIVE_CHARGE",
    "FAST_DISEMBARK",
    "FRAGILE_UNIT",
    "HIDDEN",
    "INDIRECT_FIRE",
    "MINE_DETECTION",
    "NO_LINE_OF_SIGHT",
    "PARATROOPS",
    "PIVOT",
    "RAPID_FIRE",
    "RECON_PATROL",
    "RIFLE_GRENADES",
    "SCOUT",
    "SLOW_UNIT",
    "SMOKE",
    "SNIPER",
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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>Assault - Editor Táctico de Tropas y Flujo de Aprobación</title>
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
    body { background: var(--bg); color: var(--text); padding: 1.5rem; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 1px solid var(--card-border); }
    h1 { font-size: 1.5rem; color: #fff; display: flex; align-items: center; gap: 0.5rem; }
    .badge { padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .badge-published { background: #065f46; color: #6ee7b7; border: 1px solid #10b981; }
    .badge-staged { background: #854d0e; color: #fde047; border: 1px solid #f59e0b; }
    .badge-pending { background: #374151; color: #d1d5db; border: 1px solid #6b7280; }
    
    .layout { display: grid; grid-template-columns: 360px 1fr; gap: 1.5rem; }
    .sidebar { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; max-height: calc(100vh - 120px); overflow-y: auto; }
    .search-box { width: 100%; padding: 0.6rem; border-radius: 6px; border: 1px solid var(--card-border); background: #0f172a; color: #fff; margin-bottom: 1rem; }
    .unit-list { list-style: none; display: flex; flex-direction: column; gap: 0.4rem; }
    .unit-item { padding: 0.6rem 0.8rem; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; background: #131d31; border: 1px solid transparent; transition: all 0.15s; }
    .unit-item:hover { border-color: var(--accent); background: #1e293b; }
    .unit-item.active { border-color: var(--accent); background: #0369a1; }
    .unit-item .name { font-weight: 600; font-size: 0.88rem; }
    .unit-item .meta { font-size: 0.72rem; color: var(--text-muted); }

    .status-filters { display: flex; gap: 0.35rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
    .faction-filters { display: flex; gap: 0.35rem; margin-bottom: 0.8rem; flex-wrap: wrap; }
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

    /* Chips de Rasgos */
    .traits-container { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.8rem; }
    .trait-chip { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.65rem; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; border: 1px solid var(--card-border-light); background: #1e293b; color: #94a3b8; transition: all 0.15s; user-select: none; }
    .trait-chip:hover { border-color: var(--accent-hover); color: #fff; }
    .trait-chip.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .trait-chip.active .chip-icon { color: #fde047; }
    .add-trait-bar { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.5rem; }
    .add-trait-bar input { flex: 1; padding: 0.45rem 0.6rem; border-radius: 6px; border: 1px solid var(--card-border); background: #131d31; color: #fff; font-size: 0.82rem; }
    .add-trait-bar button { padding: 0.45rem 0.9rem; font-size: 0.82rem; background: #0284c7; color: #fff; border-radius: 6px; }

    /* Tabla y Bloques de Ataque */
    .attack-mode-card { background: #131d31; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.8rem; margin-bottom: 0.8rem; }
    .attack-mode-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem; }
    .attack-mode-title { font-size: 0.85rem; font-weight: 700; color: #e2e8f0; display: flex; align-items: center; gap: 0.4rem; }
    .bands-table { width: 100%; border-collapse: collapse; margin-top: 0.4rem; font-size: 0.82rem; }
    .bands-table th { text-align: left; padding: 0.4rem 0.6rem; background: #0b1120; color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; border-bottom: 1px solid var(--card-border); }
    .bands-table td { padding: 0.45rem 0.6rem; border-bottom: 1px solid #1e293b; vertical-align: middle; }
    .bands-table tr:hover td { background: #1a2438; }

    /* Badges de Dados */
    .dice-badge-container { display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
    .die-badge { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 4px; font-size: 0.7rem; font-weight: 800; color: #fff; cursor: pointer; user-select: none; box-shadow: 0 1px 3px rgba(0,0,0,0.4); }
    .die-badge:hover { opacity: 0.8; transform: scale(1.05); }
    .die-RED { background: #dc2626; border: 1px solid #f87171; }
    .die-YELLOW { background: #d97706; border: 1px solid #fbbf24; color: #000; }
    .die-GREEN { background: #16a34a; border: 1px solid #4ade80; }
    .die-BLUE { background: #2563eb; border: 1px solid #60a5fa; }
    .die-empty { font-size: 0.75rem; color: #64748b; font-style: italic; }

    /* Dice Picker Bar */
    .die-picker { display: inline-flex; gap: 0.2rem; align-items: center; background: #0b1120; padding: 0.2rem 0.4rem; border-radius: 6px; border: 1px solid var(--card-border); margin-left: 0.5rem; }
    .btn-add-die { width: 18px; height: 18px; border-radius: 3px; font-size: 0.65rem; font-weight: 900; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; border: none; }

    .btn-small { padding: 0.25rem 0.5rem; font-size: 0.75rem; border-radius: 4px; cursor: pointer; border: none; font-weight: 600; }
    .btn-del-band { background: #7f1d1d; color: #fca5a5; }
    .btn-del-band:hover { background: #991b1b; }
    .btn-add-band { background: #1e3a5f; color: #38bdf8; border: 1px dashed #0284c7; width: 100%; text-align: center; padding: 0.4rem; margin-top: 0.4rem; border-radius: 6px; cursor: pointer; font-size: 0.78rem; font-weight: 600; }
    .btn-add-band:hover { background: #0369a1; color: #fff; }

    .actions-bar { display: flex; justify-content: flex-end; gap: 0.8rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--card-border); }
    button { padding: 0.6rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }
    .btn-save-draft { background: var(--yellow); color: #000; }
    .btn-save-draft:hover { background: #fbbf24; }
    .btn-approve { background: var(--green); color: #fff; }
    .btn-approve:hover { background: var(--green-hover); }

    .json-preview { width: 100%; height: 120px; font-family: monospace; font-size: 0.78rem; background: #0b1120; color: #38bdf8; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.5rem; resize: vertical; margin-top: 0.5rem; }
    .notification { position: fixed; bottom: 20px; right: 20px; padding: 1rem 1.5rem; border-radius: 6px; background: #10b981; color: #fff; font-weight: 600; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.4); z-index: 1000; }
  </style>
</head>
<body>
  <header>
    <h1>🎖️ Assault - Editor Táctico de Tropas y Flujo de Aprobación</h1>
    <div style="display: flex; gap: 0.8rem; align-items: center;">
      <span id="catalog-count" class="badge badge-published" style="cursor: pointer;" onclick="setStatusFilter('published')">16 Publicadas</span>
      <span id="staging-count" class="badge badge-staged" style="cursor: pointer;" onclick="setStatusFilter('staged')">0 Propuestas</span>
    </div>
  </header>

  <div class="layout">
    <div class="sidebar">
      <input type="text" id="search" class="search-box" placeholder="Buscar unidad (ej. Airborne, Rifles, Mortar)..." oninput="filterUnits()" />
      <div class="status-filters">
        <button type="button" id="filter-all" class="filter-btn active" onclick="setStatusFilter('all')">Todas (<span id="count-all">0</span>)</button>
        <button type="button" id="filter-published" class="filter-btn filter-published" onclick="setStatusFilter('published')">🟢 Publicadas (<span id="count-pub">0</span>)</button>
        <button type="button" id="filter-staged" class="filter-btn filter-staged" onclick="setStatusFilter('staged')">🟡 Propuestas (<span id="count-stg">0</span>)</button>
        <button type="button" id="filter-pending" class="filter-btn filter-pending" onclick="setStatusFilter('pending')">⚪ Pendientes (<span id="count-pen">0</span>)</button>
      </div>
      <div class="faction-filters">
        <button type="button" id="filter-faction-all" class="filter-btn filter-faction active" onclick="setFactionFilter('all')">Todos</button>
        <button type="button" id="filter-faction-GE" class="filter-btn filter-faction" onclick="setFactionFilter('GE')">🇩🇪 GE (<span id="count-fac-GE">0</span>)</button>
        <button type="button" id="filter-faction-US" class="filter-btn filter-faction" onclick="setFactionFilter('US')">🇺🇸 US (<span id="count-fac-US">0</span>)</button>
        <button type="button" id="filter-faction-UK" class="filter-btn filter-faction" onclick="setFactionFilter('UK')">🇬🇧 UK (<span id="count-fac-UK">0</span>)</button>
        <button type="button" id="filter-faction-IT" class="filter-btn filter-faction" onclick="setFactionFilter('IT')">🇮🇹 IT (<span id="count-fac-IT">0</span>)</button>
      </div>
      <div style="margin-bottom: 0.8rem;">
        <select id="filter-trait-select" class="search-box" style="margin-bottom: 0; padding: 0.45rem; font-size: 0.8rem;" onchange="setTraitFilter(this.value)">
          <option value="all">⚡ Filtrar por Rasgo / Habilidad (Todos)</option>
        </select>
      </div>
      <ul id="unit-list" class="unit-list"></ul>
    </div>

    <div class="main-editor">
      <div id="no-selection" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        Selecciona una unidad de la lista para inspeccionar su carta táctica, editar sus rangos, dados y palabras clave o aprobarla.
      </div>

      <div id="editor-form" style="display: none; height: 100%;">
        <div class="editor-top">
          <div class="preview-box">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
              <h3 style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">Carta de Unidad</h3>
              <div class="card-tabs">
                <button type="button" id="tab-card-front" class="btn-card-tab active" onclick="switchCardSide('front')">Anverso (A)</button>
                <button type="button" id="tab-card-back" class="btn-card-tab" onclick="switchCardSide('back')">Reverso (B)</button>
              </div>
            </div>
            <div style="position: relative;">
              <img id="card-front-img" class="card-img" src="" alt="Carta Anverso" />
              <img id="card-back-img" class="card-img" src="" alt="Carta Reverso" style="display: none;" />
            </div>
            <div class="counter-row">
              <div>
                <img id="counter-front-img" src="" alt="Ficha Anverso" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Ficha A</div>
              </div>
              <div>
                <img id="counter-back-img" src="" alt="Ficha Reverso" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Ficha B</div>
              </div>
            </div>
          </div>

          <div class="form-scroll-container">
            <!-- Parte Superior: Header, Atributos, Escudos y Rasgos (con scroll propio) -->
            <div class="editor-top-section">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
                <h2 id="unit-title" style="font-size: 1.15rem; color: #fff;">-</h2>
                <span id="status-badge" class="badge">-</span>
              </div>

              <div class="fields-grid">
                <div class="field-group">
                  <label>ID Canónico</label>
                  <input type="text" id="field-id" />
                </div>
                <div class="field-group">
                  <label>Facción</label>
                  <select id="field-side">
                    <option value="GE">GE (Alemania)</option>
                    <option value="IT">IT (Italia)</option>
                    <option value="UK">UK (Gran Bretaña)</option>
                    <option value="US">US (Estados Unidos)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Categoría</label>
                  <select id="field-category">
                    <option value="INFANTRY">INFANTRY (Infantería)</option>
                    <option value="GUN_ARTILLERY">GUN_ARTILLERY (Cañones/Art.)</option>
                    <option value="VEHICLE">VEHICLE (Blindados/Vehículos)</option>
                    <option value="TRANSPORT">TRANSPORT (Transporte)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>Subtipo Doctrinal</label>
                  <input type="text" id="field-subtype" placeholder="ej. STANDARD_INFANTRY..." />
                </div>
                <div class="field-group">
                  <label>Clasificación</label>
                  <input type="text" id="field-classification" placeholder="ej. SPECIALIZED_INFANTRY..." />
                </div>
                <div class="field-group">
                  <label>Card ID (Pág/Campaña)</label>
                  <input type="text" id="field-card-id" placeholder="ej. S43, Pr43..." />
                </div>
                <div class="field-group">
                  <label>Coste en Puntos</label>
                  <input type="number" id="field-cost" min="1" max="50" />
                </div>
                <div class="field-group">
                  <label>Movimiento (PA)</label>
                  <input type="number" id="field-movement" min="0" max="10" />
                </div>
                <div class="field-group">
                  <label>Salud Máx (HP)</label>
                  <input type="number" id="field-max-strength" min="1" max="10" />
                </div>
              </div>

              <!-- Escudos de Defensa Base (Selector Visual de Dados) -->
              <div class="defense-section">
                <div class="section-title">
                  <span>Escudos de Defensa Base (Dados de Salvación por Arco)</span>
                  <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">Haz clic en el dado para eliminarlo o usa el selector</span>
                </div>
                <div id="defense-arcs-container" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.8rem;"></div>
              </div>

              <!-- Palabras Clave y Rasgos Tácticos (Chips interactivos) -->
              <div class="traits-section">
                <div class="section-title">
                  <span>Palabras Clave y Habilidades Tácticas (Traits)</span>
                  <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">Haz clic para activar/desactivar o añade nuevas</span>
                </div>
                <div id="traits-chips-container" class="traits-container"></div>
                <div class="add-trait-bar">
                  <input type="text" id="new-trait-input" placeholder="Nueva palabra clave (ej. PANZERFAUST_AMBUSH, MINE_LAYER...)" onkeydown="if(event.key==='Enter') addNewTrait()" />
                  <button type="button" onclick="addNewTrait()">➕ Añadir Palabra Clave</button>
                </div>
              </div>
            </div>

            <!-- Parte Inferior: Dividida en Dos Columnas con Scroll Independiente al de arriba -->
            <div class="editor-bottom-split">
              <!-- Columna Izquierda: Fuego Directo e Indirecto -->
              <div class="split-col-attacks">
                <div class="attack-section" style="height: 100%; display: flex; flex-direction: column; overflow: hidden; margin-bottom: 0;">
                  <div class="section-title" style="flex-shrink: 0; margin-bottom: 0.5rem;">
                    <span>Matriz de Fuego de Ataque (Directo e Indirecto)</span>
                    <div style="display: flex; gap: 0.5rem;">
                      <button type="button" class="btn-small" style="background: #0284c7; color: #fff;" onclick="addAttackMode('DIRECT_FIRE')">+ Fuego Directo</button>
                      <button type="button" class="btn-small" style="background: #7c3aed; color: #fff;" onclick="addAttackMode('INDIRECT_FIRE')">+ Fuego Indirecto</button>
                    </div>
                  </div>
                  <div id="attack-modes-container" style="flex: 1; min-height: 0; overflow-y: auto; padding-right: 0.3rem;"></div>
                </div>
              </div>

              <!-- Columna Derecha: Cortina de Humo, Inspector JSON y Acciones -->
              <div class="split-col-tactical">
                <!-- Componente Dedicado para Acción Táctica de Humo (Smoke) -->
                <div id="smoke-action-container"></div>

                <!-- Inspector y Edición JSON sin procesar -->
                <div style="background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 0.8rem;">
                  <details>
                    <summary style="font-size: 0.75rem; color: var(--accent); cursor: pointer; font-weight: 600;">🔍 Ver / Editar JSON de Ataque sin procesar</summary>
                    <textarea id="field-attack-json" class="json-preview" oninput="onJsonInput()"></textarea>
                  </details>
                </div>

                <!-- Botones de Acción (Guardar y Publicar) -->
                <div class="actions-bar" style="margin-top: auto; display: flex; gap: 0.6rem;">
                  <button class="btn-save-draft" style="flex: 1;" onclick="saveDraft()">💾 Guardar Borrador</button>
                  <button class="btn-approve" style="flex: 1;" onclick="approveAndPublish()">🚀 Aprobar y Publicar</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="notif" class="notification">Acción completada con éxito.</div>

  <script>
    let inventory = [];
    let catalog = {};
    let staging = {};
    let currentUnit = null;

    let availableTraits = [];
    let activeTraits = new Set();
    let attackData = {};

    let currentStatusFilter = 'all';
    let currentFactionFilter = 'all';
    let currentTraitFilter = 'all';

    async function loadData() {
      const res = await fetch('/api/units/state');
      const data = await res.json();
      inventory = data.inventory || [];
      catalog = data.catalog?.units || {};
      staging = data.staging || {};
      availableTraits = data.traits || [];
      
      const pubCount = Object.keys(catalog).length;
      const stgCount = Object.keys(staging).length;
      const totalCount = inventory.length;
      const penCount = inventory.filter(u => !catalog[u.id] && !staging[u.id]).length;

      document.getElementById('catalog-count').innerText = pubCount + ' Publicadas';
      document.getElementById('staging-count').innerText = stgCount + ' Propuestas';

      document.getElementById('count-all').innerText = totalCount;
      document.getElementById('count-pub').innerText = pubCount;
      document.getElementById('count-stg').innerText = stgCount;
      document.getElementById('count-pen').innerText = penCount;

      // Faction counts
      const factions = ['GE', 'US', 'UK', 'IT'];
      factions.forEach(f => {
        const el = document.getElementById('count-fac-' + f);
        if (el) el.innerText = inventory.filter(u => u.faction === f).length;
      });

      // Populate Trait Filter Select
      const traitSelect = document.getElementById('filter-trait-select');
      if (traitSelect) {
        const savedVal = currentTraitFilter;
        traitSelect.innerHTML = '<option value="all">⚡ Filtrar por Rasgo / Habilidad (Todos)</option>';
        availableTraits.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t;
          opt.innerText = t;
          traitSelect.appendChild(opt);
        });
        traitSelect.value = savedVal;
      }

      renderSidebar();
    }

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
      const q = document.getElementById('search').value.toLowerCase();
      const list = document.getElementById('unit-list');
      list.innerHTML = '';

      inventory.forEach(u => {
        const id = u.id;
        const name = u.name;
        if (q && !id.toLowerCase().includes(q) && !name.toLowerCase().includes(q) && !u.faction.toLowerCase().includes(q)) {
          return;
        }

        // Apply faction filter
        if (currentFactionFilter !== 'all' && u.faction !== currentFactionFilter) {
          return;
        }

        // Unit active traits from catalog > staging
        const sourceData = catalog[id] || staging[id] || {};
        const unitTraits = sourceData.traits || [];

        // Apply trait filter
        if (currentTraitFilter !== 'all' && !unitTraits.includes(currentTraitFilter)) {
          return;
        }

        const isPublished = Boolean(catalog[id]);
        const isStaged = Boolean(staging[id]);

        let badgeClass = 'badge-pending';
        let badgeText = 'Pendiente';
        let status = 'pending';
        if (isPublished) {
          badgeClass = 'badge-published';
          badgeText = 'Publicada';
          status = 'published';
        } else if (isStaged) {
          badgeClass = 'badge-staged';
          badgeText = 'Propuesta';
          status = 'staged';
        }

        // Apply status filter
        if (currentStatusFilter !== 'all' && currentStatusFilter !== status) {
          return;
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

      // Configurar cartas front y back
      document.getElementById('card-front-img').src = '/' + u.card_front;
      document.getElementById('card-back-img').src = '/' + (u.card_back || u.card_front);
      switchCardSide('front');

      document.getElementById('counter-front-img').src = '/' + u.counter_front;
      document.getElementById('counter-back-img').src = '/' + (u.counter_back || u.counter_front);

      document.getElementById('unit-title').innerText = u.name + ' (' + u.id + ')';

      const isPublished = Boolean(catalog[u.id]);
      const isStaged = Boolean(staging[u.id]);
      const badge = document.getElementById('status-badge');
      if (isPublished) {
        badge.className = 'badge badge-published';
        badge.innerText = '🟢 Publicada en Catálogo';
      } else if (isStaged) {
        badge.className = 'badge badge-staged';
        badge.innerText = '🟡 Propuesta en Revisión';
      } else {
        badge.className = 'badge badge-pending';
        badge.innerText = '⚪ Pendiente de Valores';
      }

      // Populate form from catalog > staging > fallback
      const source = catalog[u.id] || staging[u.id] || {};

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

      // Palabras Clave (Traits) - Filtrar propiedades de modo de ataque que no son habilidades de carta
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

      // Ataques y Rangos
      attackData = JSON.parse(JSON.stringify(source.attack || {
        DIRECT_FIRE: {
          VEHICLE: { "0-10": { dice: [] } },
          INFANTRY: { "0": { dice: ["RED", "RED"] }, "1-3": { dice: ["RED", "YELLOW"] } }
        }
      }));

      // Normalizar SMOKE al formato exacto de la carta (target hex + hexágonos adyacentes)
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

      // Normalizar INDIRECT_FIRE a rangos directos si viene en formato anidado (INFANTRY/VEHICLE/ALL)
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

    // --- MANEJO DE ESCUDOS DE DEFENSA BASE (DADOS) ---
    const ARC_LABELS = {
      FRONT: "FRONT (Frente)",
      FLANK_LEFT: "FLANK L (Flanco Izq.)",
      FLANK_RIGHT: "FLANK R (Flanco Dcho.)",
      REAR: "REAR (Retaguardia)"
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
          diceBadges = '<span class="die-empty" style="font-size: 0.72rem;">Sin dados (0)</span>';
        } else {
          diceBadges = dice.map((d, idx) => `
            <span class="die-badge die-${d}" title="Eliminar dado ${d}" onclick="removeDefenseDie('${arc}', ${idx})">${d[0]}</span>
          `).join('');
        }

        card.innerHTML = `
          <div style="font-size: 0.75rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.4rem; display: flex; justify-content: space-between; align-items: center;">
            <span>${ARC_LABELS[arc] || arc}</span>
            <span style="font-size: 0.65rem; color: var(--text-muted);">${dice ? dice.length : 0} dado(s)</span>
          </div>
          <div class="dice-badge-container" style="min-height: 26px; margin-bottom: 0.4rem;">
            ${diceBadges}
          </div>
          <div style="display: flex; gap: 0.2rem; align-items: center; background: #0b1120; padding: 0.2rem 0.35rem; border-radius: 4px; border: 1px solid var(--card-border);">
            <span style="font-size: 0.65rem; color: var(--text-muted); margin-right: 2px;">+</span>
            <button type="button" class="btn-add-die die-RED" title="Añadir dado Rojo" onclick="addDefenseDie('${arc}', 'RED')">R</button>
            <button type="button" class="btn-add-die die-YELLOW" title="Añadir dado Amarillo" onclick="addDefenseDie('${arc}', 'YELLOW')">Y</button>
            <button type="button" class="btn-add-die die-GREEN" title="Añadir dado Verde" onclick="addDefenseDie('${arc}', 'GREEN')">G</button>
            <button type="button" class="btn-add-die die-BLUE" title="Añadir dado Azul" onclick="addDefenseDie('${arc}', 'BLUE')">B</button>
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

    const TRAIT_HELP = {
      'EXPLOSIVE_CHARGE': '💣 [Regla 12.5 / Carta]: Detonación de carga explosiva en fase de apoyo contra edificio, fortificación u obstáculo adyacente. Tira 1 dado ROJO vs defensa más fuerte del terreno (o 1 VERDE si no hay). Destruye o colapsa el objetivo.',
      'MINE_DETECTION': '🔍 [Reglas 9.6.6.2 / 9.6.4.2]: Reconocimiento y detección de campos de minas. Otorga bonificador de +2 al dado D6 para identificar o sortear minas con seguridad.',
      'SMOKE': '💨 [Regla 7.2]: Capacidad de disparo de proyectiles de humo en hexágono objetivo y hasta 2 adyacentes para bloquear o dificultar LOS.',
      'ASSAULT': '⚔️ [Regla 10.10]: Bonificador / capacidad para asalto en combate cerrado contra unidades enemigas.',
      'ANTI_TANK': '🛡️ [Regla 10.7]: Armamento antitanque con penetración optimizada contra blindajes de vehículos.',
      'SCOUT': '🔭 [Regla 9.6.6.2]: Reconocimiento avanzado (+1 a la tirada de detección de minas y avistamiento).',
      'TOUGH': '💪 [Regla 10.7]: Resistencia tenaz en combate cerrado (ignora el primer impacto recibido en el turno 1).',
      'RAPID_FIRE': '🔥 [Regla 10.7]: Ráfagas sostenidas con re-roll de dado de ataque.',
      'SNIPER': '🎯 [Regla 10.7]: Tirador de élite; anula el dado de defensa de terreno más fuerte del defensor.',
      'CAMOUFLAGED': '🌿 [Regla 10.5]: Camuflaje pasivo que dificulta la detección del enemigo.',
      'HIDDEN': '👁️‍🗨️ [Regla 13.1]: Unidad oculta que recibe +1 dado azul de defensa adicional hasta su activación.',
      'PARATROOPS': '🪂 [Regla 9.8]: Despliegue paracaidista aerotransportado con equipo ligero de asalto.',
    };

    // --- MANEJO DE TRAITS / PALABRAS CLAVE ---
    function renderTraitsChips() {
      const container = document.getElementById('traits-chips-container');
      container.innerHTML = '';

      availableTraits.forEach(trait => {
        const isActive = activeTraits.has(trait);
        const chip = document.createElement('div');
        chip.className = 'trait-chip' + (isActive ? ' active' : '');
        chip.title = TRAIT_HELP[trait] || `Habilidad / Rasgo táctico: ${trait}`;
        chip.innerHTML = `
          <span class="chip-icon">${isActive ? '✓' : '+'}</span>
          <span>${trait}</span>
        `;
        chip.onclick = () => toggleTrait(trait);
        container.appendChild(chip);
      });
    }


    function toggleTrait(trait) {
      if (activeTraits.has(trait)) {
        activeTraits.delete(trait);
        if (trait === 'SMOKE' && attackData.SMOKE) {
          delete attackData.SMOKE;
          syncAttackToUI();
        }
      } else {
        activeTraits.add(trait);
        if (trait === 'SMOKE' && !attackData.SMOKE) {
          attackData.SMOKE = {
            target_hex: true,
            max_adjacent_hexes: 2,
            dice: ["GREEN", "GREEN", "GREEN", "BLUE", "BLUE", "BLUE"]
          };
          syncAttackToUI();
        }
      }
      renderTraitsChips();
    }

    function addNewTrait() {
      const input = document.getElementById('new-trait-input');
      const val = input.value.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
      if (!val) return;
      if (!availableTraits.includes(val)) {
        availableTraits.push(val);
        availableTraits.sort();
      }
      activeTraits.add(val);
      input.value = '';
      renderTraitsChips();
    }

    // --- MANEJO VISUAL DE MATRIZ DE ATAQUE Y RANGOS ---
    function syncAttackToUI() {
      const container = document.getElementById('attack-modes-container');
      container.innerHTML = '';

      Object.entries(attackData).forEach(([modeName, targetObj]) => {
        if (modeName === 'SMOKE') return; // Se renderiza en el componente dedicado de Humo

        const card = document.createElement('div');
        card.className = 'attack-mode-card';

        // Manejo unificado de Fuego Indirecto (Fuego de Área a Hexágono - Regla 7.1)
        if (modeName === 'INDIRECT_FIRE') {
          const rangeMap = targetObj || {};
          let rowsHtml = '';
          Object.entries(rangeMap).forEach(([rangeBand, bandData]) => {
            if (rangeBand === 'defense_loss' || rangeBand === 'reroll') return;
            if (!bandData || !bandData.dice) return;
            const dice = bandData.dice || [];
            let diceBadges = '';
            if (dice.length === 0) {
              diceBadges = '<span class="die-empty">Sin daño (0 dados)</span>';
            } else {
              diceBadges = dice.map((d, dIdx) => `
                <span class="die-badge die-${d}" title="Eliminar dado ${d}" onclick="removeIndirectDie('${rangeBand}', ${dIdx})">${d[0]}</span>
              `).join('');
            }

            rowsHtml += `
              <tr>
                <td style="width: 140px;">
                  <input type="text" value="${rangeBand}" style="width: 110px; padding: 0.25rem 0.4rem; font-size: 0.8rem; background: #0b1120; color: #fff; border: 1px solid var(--card-border); border-radius: 4px;"
                    onchange="renameIndirectRangeBand('${rangeBand}', this.value)" />
                </td>
                <td>
                  <div class="dice-badge-container">
                    ${diceBadges}
                    <div class="die-picker">
                      <span style="font-size: 0.65rem; color: var(--text-muted); margin-right: 2px;">+</span>
                      <button type="button" class="btn-add-die die-RED" title="Añadir dado Rojo" onclick="addIndirectDie('${rangeBand}', 'RED')">R</button>
                      <button type="button" class="btn-add-die die-YELLOW" title="Añadir dado Amarillo" onclick="addIndirectDie('${rangeBand}', 'YELLOW')">Y</button>
                      <button type="button" class="btn-add-die die-GREEN" title="Añadir dado Verde" onclick="addIndirectDie('${rangeBand}', 'GREEN')">G</button>
                      <button type="button" class="btn-add-die die-BLUE" title="Añadir dado Azul" onclick="addIndirectDie('${rangeBand}', 'BLUE')">B</button>
                    </div>
                  </div>
                </td>
                <td style="width: 40px; text-align: right;">
                  <button type="button" class="btn-small btn-del-band" title="Eliminar rango" onclick="removeIndirectRangeBand('${rangeBand}')">✕</button>
                </td>
              </tr>
            `;
          });

          const defLoss = attackData.INDIRECT_FIRE.defense_loss || 'NONE';
          const isReroll = Boolean(attackData.INDIRECT_FIRE.reroll);

          card.innerHTML = `
            <div class="attack-mode-header">
              <div class="attack-mode-title">
                <span>☄️ MODO: INDIRECT FIRE (FUEGO INDIRECTO)</span>
              </div>
              <button type="button" class="btn-small btn-del-band" onclick="removeAttackMode('INDIRECT_FIRE')">Eliminar Modo</button>
            </div>
            <div style="font-size: 0.72rem; color: #cbd5e1; background: #0b1322; padding: 0.4rem 0.6rem; border-radius: 5px; margin: 0.4rem 0 0.6rem 0; border-left: 3px solid #8b5cf6; line-height: 1.35;">
              📜 <strong>Fuego a Hexágono (Regla 7.1):</strong> Afecta por igual a cualquier tropa en el hexágono (Infantería o Blindados). Unificado sin tablas duplicadas.
            </div>
            <div style="background: #0c1424; padding: 0.65rem 0.8rem; border-radius: 6px; border: 1px solid var(--card-border);">
              <table class="bands-table">
                <thead>
                  <tr>
                    <th>Rango (Hex)</th>
                    <th>Dados Asignados (Clic en dado para quitar)</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  ${rowsHtml || '<tr><td colspan="3" style="text-align:center; color: var(--text-muted); font-size: 0.75rem;">Sin rangos configurados</td></tr>'}
                </tbody>
              </table>
              <div class="btn-add-band" onclick="addNewIndirectRangeBand()">
                + Añadir Rango de Fuego Indirecto
              </div>

              <!-- Propiedades Adicionales de Fuego Indirecto -->
              <div style="margin-top: 0.75rem; padding-top: 0.65rem; border-top: 1px solid #1e293b;">
                <div style="font-size: 0.74rem; font-weight: 700; color: #a78bfa; margin-bottom: 0.45rem; display: flex; align-items: center; gap: 0.35rem;">
                  <span>⚙️ Propiedades Tácticas Adicionales (Carta Física / Regla 7.1)</span>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; background: #070d19; padding: 0.6rem; border-radius: 6px; border: 1px solid #1e293b;">
                  <div>
                    <label style="font-size: 0.7rem; color: #94a3b8; display: block; margin-bottom: 0.25rem;">
                      🛡️ Pérdida de Dado de Defensa (Terreno):
                    </label>
                    <select style="width: 100%; padding: 0.3rem 0.45rem; font-size: 0.74rem; background: #0b1120; color: #fff; border: 1px solid var(--card-border); border-radius: 4px;"
                      onchange="updateIndirectDefenseLoss(this.value)">
                      <option value="NONE" ${defLoss === 'NONE' ? 'selected' : ''}>Ninguna (Defensor tira normal)</option>
                      <option value="WEAKEST_TERRAIN" ${defLoss === 'WEAKEST_TERRAIN' ? 'selected' : ''}>Pierde el dado de terreno más débil (Weakest)</option>
                      <option value="STRONGEST_TERRAIN" ${defLoss === 'STRONGEST_TERRAIN' ? 'selected' : ''}>Pierde el dado de terreno más fuerte (Strongest)</option>
                    </select>
                  </div>
                  <div style="display: flex; flex-direction: column; justify-content: center;">
                    <label style="font-size: 0.72rem; color: #cbd5e1; display: flex; align-items: center; gap: 0.4rem; cursor: pointer; margin-top: 0.85rem;">
                      <input type="checkbox" ${isReroll ? 'checked' : ''} style="cursor: pointer; width: 15px; height: 15px;"
                        onchange="updateIndirectReroll(this.checked)" />
                      <span>🎲 <strong>Re-roll:</strong> Relanzar 1 dado de ataque</span>
                    </label>
                    <span style="font-size: 0.65rem; color: var(--text-muted); margin-left: 1.4rem;">(Rifle Grenades: re-roll one attack die)</span>
                  </div>
                </div>
              </div>
            </div>
          `;
          container.appendChild(card);
          return;
        }

        // Ordenar objetivos: VEHICLE primero (fila superior en carta física), luego INFANTRY
        const existingTargets = Object.keys(targetObj || {}).sort((a, b) => {
          if (a === 'VEHICLE') return -1;
          if (b === 'VEHICLE') return 1;
          return 0;
        });

        let targetsHtml = '';
        existingTargets.forEach(targetType => {
          const rangeMap = targetObj[targetType] || {};
          let rowsHtml = '';
          Object.entries(rangeMap).forEach(([rangeBand, bandData]) => {
            const dice = (bandData && bandData.dice) ? bandData.dice : [];
            let diceBadges = '';
            if (dice.length === 0) {
              diceBadges = '<span class="die-empty">Sin daño (0 dados)</span>';
            } else {
              diceBadges = dice.map((d, dIdx) => `
                <span class="die-badge die-${d}" title="Eliminar dado ${d}" onclick="removeDie('${modeName}', '${targetType}', '${rangeBand}', ${dIdx})">${d[0]}</span>
              `).join('');
            }

            rowsHtml += `
              <tr>
                <td style="width: 140px;">
                  <input type="text" value="${rangeBand}" style="width: 110px; padding: 0.25rem 0.4rem; font-size: 0.8rem; background: #0b1120; color: #fff; border: 1px solid var(--card-border); border-radius: 4px;"
                    onchange="renameRangeBand('${modeName}', '${targetType}', '${rangeBand}', this.value)" />
                </td>
                <td>
                  <div class="dice-badge-container">
                    ${diceBadges}
                    <div class="die-picker">
                      <span style="font-size: 0.65rem; color: var(--text-muted); margin-right: 2px;">+</span>
                      <button type="button" class="btn-add-die die-RED" title="Añadir dado Rojo" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'RED')">R</button>
                      <button type="button" class="btn-add-die die-YELLOW" title="Añadir dado Amarillo" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'YELLOW')">Y</button>
                      <button type="button" class="btn-add-die die-GREEN" title="Añadir dado Verde" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'GREEN')">G</button>
                      <button type="button" class="btn-add-die die-BLUE" title="Añadir dado Azul" onclick="addDie('${modeName}', '${targetType}', '${rangeBand}', 'BLUE')">B</button>
                    </div>
                  </div>
                </td>
                <td style="width: 40px; text-align: right;">
                  <button type="button" class="btn-small btn-del-band" title="Eliminar rango" onclick="removeRangeBand('${modeName}', '${targetType}', '${rangeBand}')">✕</button>
                </td>
              </tr>
            `;
          });

          let targetLabel = targetType;
          let targetColor = '#f472b6';
          let targetIcon = '🪖';
          if (targetType === 'VEHICLE') {
            targetLabel = 'VEHÍCULO / BLINDADO (VEHICLE)';
            targetColor = '#38bdf8';
            targetIcon = '🛡️';
          } else if (targetType === 'INFANTRY') {
            targetLabel = 'INFANTERÍA / CAÑÓN (INFANTRY)';
            targetColor = '#f472b6';
            targetIcon = '🪖';
          }

          targetsHtml += `
            <div style="margin-top: 0.75rem; background: #0c1424; padding: 0.65rem 0.8rem; border-radius: 6px; border: 1px solid var(--card-border);">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <div style="font-size: 0.76rem; font-weight: 700; color: ${targetColor}; display: flex; align-items: center; gap: 0.35rem;">
                  <span>${targetIcon}</span>
                  <span>${targetLabel}</span>
                </div>
                <button type="button" class="btn-small btn-del-band" style="font-size: 0.65rem;" onclick="removeTargetCategory('${modeName}', '${targetType}')">✕ Quitar ${targetType}</button>
              </div>
              <table class="bands-table">
                <thead>
                  <tr>
                    <th>Rango (Hex)</th>
                    <th>Dados Asignados (Clic en dado para quitar)</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  ${rowsHtml}
                </tbody>
              </table>
              <div class="btn-add-band" onclick="addNewRangeBand('${modeName}', '${targetType}')">
                + Añadir Rango a ${targetType}
              </div>
            </div>
          `;
        });

        if (existingTargets.length === 0) {
          targetsHtml = `
            <div style="padding: 0.8rem; text-align: center; color: var(--text-muted); font-size: 0.75rem;">
              No hay objetivos configurados en este modo. Usa los botones superiores para añadir VEHÍCULO o INFANTERÍA.
            </div>
          `;
        }

        let missingButtons = '';
        if (!targetObj.VEHICLE) {
          missingButtons += `<button type="button" class="btn-small" style="background: #0284c7; color: white; font-weight: 600;" onclick="addTargetCategory('${modeName}', 'VEHICLE')">🛡️ + Añadir Objetivo VEHÍCULO</button>`;
        }
        if (!targetObj.INFANTRY) {
          missingButtons += `<button type="button" class="btn-small" style="background: #db2777; color: white; font-weight: 600;" onclick="addTargetCategory('${modeName}', 'INFANTRY')">🪖 + Añadir Objetivo INFANTERÍA</button>`;
        }

        let modeIcon = '🎯';
        let modeDisplay = modeName;
        if (modeName === 'DIRECT_FIRE') modeDisplay = 'DIRECT FIRE (FUEGO DIRECTO)';
        if (modeName === 'INDIRECT_FIRE') { modeIcon = '☄️'; modeDisplay = 'INDIRECT FIRE (FUEGO INDIRECTO)'; }

        card.innerHTML = `
          <div class="attack-mode-header">
            <div class="attack-mode-title">
              <span>${modeIcon} MODO: ${modeDisplay}</span>
            </div>
            <div style="display: flex; gap: 0.4rem; align-items: center;">
              ${missingButtons}
              <button type="button" class="btn-small btn-del-band" onclick="removeAttackMode('${modeName}')">Eliminar Modo</button>
            </div>
          </div>
          ${targetsHtml}
        `;

        container.appendChild(card);
      });

      // Renderizar componente dedicado de Humo (Smoke)
      renderSmokeUI();

      // Update JSON preview textarea
      document.getElementById('field-attack-json').value = JSON.stringify(attackData, null, 2);
    }

    // --- COMPONENTE DEDICADO PARA ACCIÓN TÁCTICA DE HUMO (SMOKE) ---
    function renderSmokeUI() {
      const container = document.getElementById('smoke-action-container');
      if (!container) return;

      if (!attackData.SMOKE) {
        container.innerHTML = `
          <div style="margin-top: 0; padding: 0.75rem 1rem; background: #0c1322; border: 1px dashed #334155; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-size: 0.8rem; font-weight: 700; color: #94a3b8; display: flex; align-items: center; gap: 0.4rem;">
                <span>💨 Acción Táctica: Cortina de Humo (Smoke)</span>
              </div>
              <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem;">
                Esta unidad no tiene configurada cortina de humo. Habilitar para morteros o artillería con proyectiles fumígenos.
              </div>
            </div>
            <button type="button" class="btn-small" style="background: #0284c7; color: white;" onclick="enableSmokeAction()">+ Habilitar Humo (Smoke)</button>
          </div>
        `;
        return;
      }

      const smoke = attackData.SMOKE;
      const maxAdj = smoke.max_adjacent_hexes !== undefined ? smoke.max_adjacent_hexes : 2;
      const dice = smoke.dice || [];

      let diceBadges = '';
      if (dice.length === 0) {
        diceBadges = '<span class="die-empty">Sin dados de humo (0)</span>';
      } else {
        diceBadges = dice.map((d, idx) => `
          <span class="die-badge die-${d}" title="Eliminar dado ${d}" onclick="removeSmokeDie(${idx})">${d[0]}</span>
        `).join('');
      }

      container.innerHTML = `
        <div style="margin-top: 0; background: #111d2e; border: 1px solid #38bdf844; border-radius: 8px; padding: 0.9rem;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.6rem;">
            <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.84rem; font-weight: 700; color: #38bdf8;">
              <span>💨 ACCIÓN TÁCTICA: CORTINA DE HUMO (SMOKE)</span>
              <span class="badge" style="background: #0284c7; color: white; font-size: 0.65rem;">Regla 7.2</span>
            </div>
            <button type="button" class="btn-small btn-del-band" onclick="removeSmokeAction()">✕ Eliminar Humo</button>
          </div>

          <div style="font-size: 0.73rem; color: #94a3b8; background: #0b1322; padding: 0.5rem 0.75rem; border-radius: 6px; margin-bottom: 0.75rem; border-left: 3px solid #38bdf8; line-height: 1.4;">
            📜 <strong>Texto Oficial de la Carta:</strong> <em>"This unit can fire smoke into a target hex and up to two nominated adjacent hexes."</em><br/>
            ℹ️ <strong>Mecánica (Regla 7.2):</strong> El humo <strong>no tiene rango numérico propio</strong> en la acción: utiliza el alcance de tiro de la unidad (Fuego Indirecto o Directo). Designa un hexágono objetivo y hasta hexágonos adyacentes nominados.
          </div>

          <div style="display: grid; grid-template-columns: 260px 1fr; gap: 1rem; align-items: start;">
            <!-- Cobertura de Hexágonos (Target Hex + Adyacentes) -->
            <div style="background: #0d1527; padding: 0.65rem 0.85rem; border-radius: 6px; border: 1px solid var(--card-border);">
              <div style="font-size: 0.74rem; font-weight: 700; color: #e2e8f0; margin-bottom: 0.5rem;">
                🎯 Cobertura de la Cortina de Humo
              </div>
              <div style="font-size: 0.75rem; color: #38bdf8; font-weight: 600; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.35rem;">
                <span>✓</span> <span>Hexágono Objetivo (Target Hex)</span>
              </div>
              <div>
                <label style="font-size: 0.68rem; color: var(--text-muted); display: block; margin-bottom: 2px;">
                  Hexágonos Adyacentes Nominados (Máx):
                </label>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <span style="font-size: 0.75rem; color: #cbd5e1;">Hasta</span>
                  <input type="number" min="0" max="6" value="${maxAdj}" 
                    onchange="updateSmokeAdjacent(this.value)" 
                    style="width: 55px; padding: 0.25rem 0.4rem; font-size: 0.82rem; background: #070d18; color: #fff; border: 1px solid var(--card-border); border-radius: 4px; text-align: center;" />
                  <span style="font-size: 0.75rem; color: #cbd5e1;">adyacentes</span>
                </div>
              </div>
            </div>

            <!-- Dados de Humo -->
            <div style="background: #0d1527; padding: 0.65rem 0.85rem; border-radius: 6px; border: 1px solid var(--card-border);">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
                <span style="font-size: 0.74rem; font-weight: 700; color: #e2e8f0;">🎲 Dados de Disparo de Humo</span>
                <div style="display: flex; gap: 0.3rem;">
                  <button type="button" class="btn-small" style="font-size: 0.65rem; background: #1e293b; color: #94a3b8;" onclick="applySmokePreset('50mm')">Mortero 50mm (3G+3B)</button>
                  <button type="button" class="btn-small" style="font-size: 0.65rem; background: #1e293b; color: #94a3b8;" onclick="applySmokePreset('81mm')">Mortero 81mm (4G+4B)</button>
                </div>
              </div>
              <div class="dice-badge-container" style="min-height: 28px; margin-bottom: 0.45rem;">
                ${diceBadges}
              </div>
              <div style="display: flex; gap: 0.25rem; align-items: center; background: #070d18; padding: 0.25rem 0.4rem; border-radius: 4px; border: 1px solid var(--card-border); width: fit-content;">
                <span style="font-size: 0.65rem; color: var(--text-muted); margin-right: 2px;">+ Añadir:</span>
                <button type="button" class="btn-add-die die-RED" title="Añadir dado Rojo" onclick="addSmokeDie('RED')">R</button>
                <button type="button" class="btn-add-die die-YELLOW" title="Añadir dado Amarillo" onclick="addSmokeDie('YELLOW')">Y</button>
                <button type="button" class="btn-add-die die-GREEN" title="Añadir dado Verde" onclick="addSmokeDie('GREEN')">G</button>
                <button type="button" class="btn-add-die die-BLUE" title="Añadir dado Azul" onclick="addSmokeDie('BLUE')">B</button>
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
        dice: ["GREEN", "GREEN", "GREEN", "BLUE", "BLUE", "BLUE"]
      };
      activeTraits.add("SMOKE");
      renderTraitsChips();
      syncAttackToUI();
    }

    function removeSmokeAction() {
      if (confirm("¿Eliminar la acción de humo (Smoke)?")) {
        delete attackData.SMOKE;
        activeTraits.delete("SMOKE");
        renderTraitsChips();
        syncAttackToUI();
      }
    }

    function updateSmokeAdjacent(val) {
      if (!attackData.SMOKE) return;
      const num = parseInt(val, 10);
      if (isNaN(num)) return;
      attackData.SMOKE.max_adjacent_hexes = num;
      attackData.SMOKE.target_hex = true;
      document.getElementById('field-attack-json').value = JSON.stringify(attackData, null, 2);
    }

    function addSmokeDie(color) {
      if (!attackData.SMOKE) enableSmokeAction();
      if (!attackData.SMOKE.dice) attackData.SMOKE.dice = [];
      attackData.SMOKE.dice.push(color);
      syncAttackToUI();
    }

    function removeSmokeDie(index) {
      if (attackData.SMOKE && attackData.SMOKE.dice) {
        attackData.SMOKE.dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function applySmokePreset(presetKey) {
      if (!attackData.SMOKE) enableSmokeAction();
      attackData.SMOKE.target_hex = true;
      attackData.SMOKE.max_adjacent_hexes = 2;
      if (presetKey === '50mm') {
        attackData.SMOKE.dice = ["GREEN", "GREEN", "GREEN", "BLUE", "BLUE", "BLUE"];
      } else if (presetKey === '81mm') {
        attackData.SMOKE.dice = ["GREEN", "GREEN", "GREEN", "GREEN", "BLUE", "BLUE", "BLUE", "BLUE"];
      }
      syncAttackToUI();
    }

    function addAttackMode(modeName) {
      if (modeName === 'SMOKE') {
        enableSmokeAction();
        return;
      }
      if (attackData[modeName]) {
        alert("El modo " + modeName + " ya existe.");
        return;
      }
      if (modeName === 'INDIRECT_FIRE') {
        attackData.INDIRECT_FIRE = {
          "3-8": { dice: ["GREEN", "GREEN", "BLUE"] },
          defense_loss: "WEAKEST_TERRAIN",
          reroll: false
        };
        syncAttackToUI();
        return;
      }
      attackData[modeName] = {
        VEHICLE: { "0-10": { dice: [] } },
        INFANTRY: { "0": { dice: ["RED", "YELLOW"] }, "1-3": { dice: ["RED"] } }
      };
      syncAttackToUI();
    }

    function removeAttackMode(modeName) {
      if (confirm("¿Eliminar el modo de ataque " + modeName + "?")) {
        delete attackData[modeName];
        syncAttackToUI();
      }
    }

    // --- FUNCIONES HELPER PARA FUEGO INDIRECTO (UNIFICADO) ---
    function addNewIndirectRangeBand() {
      const bandName = prompt("Introduce el rango de Fuego Indirecto (ej. 3-8, 2-7, 1-3):", "3-8");
      if (!bandName) return;
      if (!attackData.INDIRECT_FIRE) attackData.INDIRECT_FIRE = {};
      attackData.INDIRECT_FIRE[bandName] = { dice: ["GREEN", "GREEN", "BLUE"] };
      syncAttackToUI();
    }

    function renameIndirectRangeBand(oldBand, newBand) {
      newBand = newBand.trim();
      if (!newBand || oldBand === newBand) return;
      if (!attackData.INDIRECT_FIRE) return;
      const data = attackData.INDIRECT_FIRE[oldBand];
      delete attackData.INDIRECT_FIRE[oldBand];
      attackData.INDIRECT_FIRE[newBand] = data;
      syncAttackToUI();
    }

    function removeIndirectRangeBand(bandName) {
      if (attackData.INDIRECT_FIRE) {
        delete attackData.INDIRECT_FIRE[bandName];
        syncAttackToUI();
      }
    }

    function addIndirectDie(rangeBand, dieColor) {
      if (!attackData.INDIRECT_FIRE) attackData.INDIRECT_FIRE = {};
      if (!attackData.INDIRECT_FIRE[rangeBand]) attackData.INDIRECT_FIRE[rangeBand] = { dice: [] };
      if (!attackData.INDIRECT_FIRE[rangeBand].dice) attackData.INDIRECT_FIRE[rangeBand].dice = [];
      attackData.INDIRECT_FIRE[rangeBand].dice.push(dieColor);
      syncAttackToUI();
    }

    function removeIndirectDie(rangeBand, index) {
      if (attackData.INDIRECT_FIRE && attackData.INDIRECT_FIRE[rangeBand] && attackData.INDIRECT_FIRE[rangeBand].dice) {
        attackData.INDIRECT_FIRE[rangeBand].dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function updateIndirectDefenseLoss(val) {
      if (!attackData.INDIRECT_FIRE) return;
      attackData.INDIRECT_FIRE.defense_loss = val;
      document.getElementById('field-attack-json').value = JSON.stringify(attackData, null, 2);
    }

    function updateIndirectReroll(checked) {
      if (!attackData.INDIRECT_FIRE) return;
      attackData.INDIRECT_FIRE.reroll = checked;
      document.getElementById('field-attack-json').value = JSON.stringify(attackData, null, 2);
    }

    function addTargetCategory(modeName, targetType) {
      if (!attackData[modeName]) attackData[modeName] = {};
      if (!attackData[modeName][targetType]) {
        if (targetType === 'VEHICLE') {
          attackData[modeName].VEHICLE = { "0": { dice: ["GREEN", "BLUE"] } };
        } else if (targetType === 'INFANTRY') {
          attackData[modeName].INFANTRY = { "0": { dice: ["YELLOW", "GREEN"] } };
        }
      }
      syncAttackToUI();
    }

    function removeTargetCategory(modeName, targetType) {
      if (confirm(`¿Eliminar la tabla de ataque contra ${targetType} en ${modeName}?`)) {
        if (attackData[modeName]) {
          delete attackData[modeName][targetType];
          syncAttackToUI();
        }
      }
    }

    function addNewRangeBand(modeName, targetType) {
      const bandName = prompt("Introduce el rango (ej. 4-6, 7-10, 0):", "1-3");
      if (!bandName) return;
      if (!attackData[modeName][targetType]) {
        attackData[modeName][targetType] = {};
      }
      attackData[modeName][targetType][bandName] = { dice: ["YELLOW"] };
      syncAttackToUI();
    }

    function renameRangeBand(modeName, targetType, oldBand, newBand) {
      newBand = newBand.trim();
      if (!newBand || oldBand === newBand) return;
      const targetObj = attackData[modeName][targetType];
      const data = targetObj[oldBand];
      delete targetObj[oldBand];
      targetObj[newBand] = data;
      syncAttackToUI();
    }

    function removeRangeBand(modeName, targetType, bandName) {
      delete attackData[modeName][targetType][bandName];
      syncAttackToUI();
    }

    function addDie(modeName, targetType, rangeBand, dieColor) {
      const band = attackData[modeName][targetType][rangeBand];
      if (!band.dice) band.dice = [];
      band.dice.push(dieColor);
      syncAttackToUI();
    }

    function removeDie(modeName, targetType, rangeBand, index) {
      const band = attackData[modeName][targetType][rangeBand];
      if (band && band.dice) {
        band.dice.splice(index, 1);
        syncAttackToUI();
      }
    }

    function onJsonInput() {
      try {
        const parsed = JSON.parse(document.getElementById('field-attack-json').value);
        attackData = parsed;
        syncAttackToUI();
      } catch (e) {
        // Ignorar mientras se escribe JSON inválido
      }
    }

    function gatherFormData() {
      const id = document.getElementById('field-id').value.trim();
      const parseDice = val => val.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);

      const payload = {
        side: document.getElementById('field-side').value,
        category: document.getElementById('field-category').value,
        subtype: document.getElementById('field-subtype').value.trim(),
        classification: document.getElementById('field-classification').value.trim(),
        card_id: document.getElementById('field-card-id').value.trim(),
        cost: parseInt(document.getElementById('field-cost').value, 10),
        movement: parseInt(document.getElementById('field-movement').value, 10),
        max_strength: parseInt(document.getElementById('field-max-strength').value, 10),
        has_counter_flip: true,
        base_defense: {
          FRONT: defenseData.FRONT || ["YELLOW"],
          FLANK_LEFT: defenseData.FLANK_LEFT || ["YELLOW"],
          FLANK_RIGHT: defenseData.FLANK_RIGHT || ["YELLOW"],
          REAR: defenseData.REAR || ["YELLOW"]
        },
        attack: attackData,
        traits: Array.from(activeTraits).sort()
      };

      return { id, data: payload };
    }

    async function saveDraft() {
      const item = gatherFormData();
      if (!item) return;

      const res = await fetch('/api/units/stage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("Borrador guardado en propuestas para " + item.id);
        await loadData();
      }
    }

    async function approveAndPublish() {
      const item = gatherFormData();
      if (!item) return;

      const res = await fetch('/api/units/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item)
      });
      const data = await res.json();
      if (data.ok) {
        showNotif("🚀 Unidad " + item.id + " aprobada y publicada en unit_catalog.json!");
        await loadData();
      }
    }

    function showNotif(msg) {
      const el = document.getElementById('notif');
      el.innerText = msg;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 3000);
    }

    window.onload = loadData;
  </script>
</body>
</html>
"""


class UnitEditorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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

            # Save to catalog
            cat = load_catalog()
            cat["units"][unit_id] = data
            save_catalog(cat)

            # Remove from staging if present
            staging = load_staging()
            if unit_id in staging:
                del staging[unit_id]
                save_staging(staging)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        self.send_response(404)
        self.end_headers()


def run_server(port: int = 8780):
    server = ThreadingHTTPServer(("0.0.0.0", port), UnitEditorHandler)
    print(f"[*] Assault Unit Catalog Editor listening at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    run_server(args.port)
