"""
tools/unit_editor_server.py

Standalone Web GUI / REST Server for the Assault Unit Catalog Editor.
Workflow:
1. Loads current assets/catalogs/unit_catalog.json and assets/catalogs/unit_art_inventory.json.
2. Supports staging proposed unit definitions (pending review).
3. Serves an interactive Web UI with card/counter previews, side-by-side editing, approval, and live editing of published units.
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
  <title>Assault - Editor de Unidades y Flujo de Aprobación</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
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
    h1 { font-size: 1.6rem; color: #fff; display: flex; align-items: center; gap: 0.5rem; }
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
    .unit-item .name { font-weight: 600; font-size: 0.9rem; }
    .unit-item .meta { font-size: 0.75rem; color: var(--text-muted); }

    .main-editor { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 8px; padding: 1.5rem; overflow-y: auto; max-height: calc(100vh - 120px); }
    .editor-top { display: grid; grid-template-columns: 320px 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }
    .preview-box { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; text-align: center; }
    .preview-box img.card-img { max-width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
    .counter-row { display: flex; justify-content: center; gap: 1rem; margin-top: 1rem; }
    .counter-row img { width: 90px; height: 90px; border-radius: 6px; border: 1px solid var(--card-border); }

    .fields-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
    .field-group { display: flex; flex-direction: column; gap: 0.3rem; }
    .field-group label { font-size: 0.8rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
    .field-group input, .field-group select { padding: 0.55rem; border-radius: 6px; border: 1px solid var(--card-border); background: #0f172a; color: #fff; font-size: 0.9rem; }

    .defense-section, .attack-section { background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
    .section-title { font-size: 0.95rem; font-weight: 700; color: var(--accent); margin-bottom: 0.8rem; display: flex; justify-content: space-between; align-items: center; }

    .actions-bar { display: flex; justify-content: flex-end; gap: 0.8rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--card-border); }
    button { padding: 0.6rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }
    .btn-save-draft { background: var(--yellow); color: #000; }
    .btn-save-draft:hover { background: #fbbf24; }
    .btn-approve { background: var(--green); color: #fff; }
    .btn-approve:hover { background: var(--green-hover); }
    .btn-delete { background: var(--red); color: #fff; }
    .btn-delete:hover { background: #f87171; }

    .json-preview { width: 100%; height: 160px; font-family: monospace; font-size: 0.8rem; background: #0b1120; color: #38bdf8; border: 1px solid var(--card-border); border-radius: 6px; padding: 0.5rem; resize: vertical; }
    .notification { position: fixed; bottom: 20px; right: 20px; padding: 1rem 1.5rem; border-radius: 6px; background: #10b981; color: #fff; font-weight: 600; display: none; box-shadow: 0 4px 12px rgba(0,0,0,0.4); z-index: 1000; }
  </style>
</head>
<body>
  <header>
    <h1>🎖️ Assault - Editor de Tropas y Flujo de Aprobación</h1>
    <div style="display: flex; gap: 0.8rem; align-items: center;">
      <span id="catalog-count" class="badge badge-published">16 Publicadas</span>
      <span id="staging-count" class="badge badge-staged">0 Propuestas</span>
    </div>
  </header>

  <div class="layout">
    <div class="sidebar">
      <input type="text" id="search" class="search-box" placeholder="Buscar por nombre o ID (ej. Airborne, Rifles)..." oninput="filterUnits()" />
      <ul id="unit-list" class="unit-list"></ul>
    </div>

    <div class="main-editor">
      <div id="no-selection" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        Selecciona una unidad de la lista para inspeccionar su carta, editar parámetros o aprobar su publicación en <code>unit_catalog.json</code>.
      </div>

      <div id="editor-form" style="display: none;">
        <div class="editor-top">
          <div class="preview-box">
            <h3 style="font-size: 0.9rem; margin-bottom: 0.5rem; color: var(--text-muted);">Carta Oficial (Unit Card)</h3>
            <img id="card-img" class="card-img" src="" alt="Carta" />
            <div class="counter-row">
              <div>
                <img id="counter-front-img" src="" alt="Ficha Anverso" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Anverso</div>
              </div>
              <div>
                <img id="counter-back-img" src="" alt="Ficha Reverso" />
                <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">Reverso</div>
              </div>
            </div>
          </div>

          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
              <h2 id="unit-title" style="font-size: 1.3rem;">-</h2>
              <span id="status-badge" class="badge">-</span>
            </div>

            <div class="fields-grid">
              <div class="field-group">
                <label>ID Canónico</label>
                <input type="text" id="field-id" />
              </div>
              <div class="field-group">
                <label>Facción (Bando)</label>
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
                <input type="text" id="field-subtype" placeholder="ej. STANDARD_INFANTRY, AIRBORNE..." />
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
                <label>Salud Máx (Corazones HP)</label>
                <input type="number" id="field-max-strength" min="1" max="10" />
              </div>
            </div>

            <div class="defense-section">
              <div class="section-title">Escudos de Defensa Base (Dados de Salvación)</div>
              <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;">
                <div class="field-group">
                  <label>FRONT</label>
                  <input type="text" id="field-def-front" placeholder="YELLOW" />
                </div>
                <div class="field-group">
                  <label>FLANK LEFT</label>
                  <input type="text" id="field-def-flank-left" placeholder="YELLOW" />
                </div>
                <div class="field-group">
                  <label>FLANK RIGHT</label>
                  <input type="text" id="field-def-flank-right" placeholder="YELLOW" />
                </div>
                <div class="field-group">
                  <label>REAR</label>
                  <input type="text" id="field-def-rear" placeholder="YELLOW" />
                </div>
              </div>
            </div>

            <div class="field-group" style="margin-bottom: 1rem;">
              <label>Rasgos y Habilidades Tácticas (Separados por coma)</label>
              <input type="text" id="field-traits" placeholder="TOUGH, RIFLE_GRENADES, CAMOUFLAGED..." />
            </div>

            <div class="attack-section">
              <div class="section-title">
                <span>Estructura de Ataque y Rangos (JSON)</span>
                <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: normal;">Edita directamente el objeto <code>attack</code></span>
              </div>
              <textarea id="field-attack-json" class="json-preview"></textarea>
            </div>

            <div class="actions-bar">
              <button class="btn-save-draft" onclick="saveDraft()">💾 Guardar Borrador / Propuesta</button>
              <button class="btn-approve" onclick="approveAndPublish()">🚀 Aprobar y Publicar en unit_catalog.json</button>
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

    async function loadData() {
      const res = await fetch('/api/units/state');
      const data = await res.json();
      inventory = data.inventory || [];
      catalog = data.catalog?.units || {};
      staging = data.staging || {};
      
      document.getElementById('catalog-count').innerText = Object.keys(catalog).length + ' Publicadas';
      document.getElementById('staging-count').innerText = Object.keys(staging).length + ' Propuestas';

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

        const isPublished = Boolean(catalog[id]);
        const isStaged = Boolean(staging[id]);

        let badgeClass = 'badge-pending';
        let badgeText = 'Pendiente';
        if (isPublished) {
          badgeClass = 'badge-published';
          badgeText = 'Publicada';
        } else if (isStaged) {
          badgeClass = 'badge-staged';
          badgeText = 'Propuesta';
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

    function selectUnit(u) {
      currentUnit = u;
      renderSidebar();

      document.getElementById('no-selection').style.display = 'none';
      document.getElementById('editor-form').style.display = 'block';

      document.getElementById('card-img').src = '/' + u.card_front;
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
      document.getElementById('field-def-front').value = (baseDef.FRONT || ["YELLOW"]).join(', ');
      document.getElementById('field-def-flank-left').value = (baseDef.FLANK_LEFT || ["YELLOW"]).join(', ');
      document.getElementById('field-def-flank-right').value = (baseDef.FLANK_RIGHT || ["YELLOW"]).join(', ');
      document.getElementById('field-def-rear').value = (baseDef.REAR || ["YELLOW"]).join(', ');

      document.getElementById('field-traits').value = (source.traits || []).join(', ');

      const attackObj = source.attack || {
        DIRECT_FIRE: {
          VEHICLE: { "0-10": { dice: [] } },
          INFANTRY: { "0": { dice: ["RED", "RED"] }, "1-3": { dice: ["RED", "YELLOW"] } }
        }
      };
      document.getElementById('field-attack-json').value = JSON.stringify(attackObj, null, 2);
    }

    function gatherFormData() {
      const id = document.getElementById('field-id').value.trim();
      let attackObj = {};
      try {
        attackObj = JSON.parse(document.getElementById('field-attack-json').value);
      } catch (e) {
        alert("Error en el formato JSON de ataque: " + e.message);
        return null;
      }

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
          FRONT: parseDice(document.getElementById('field-def-front').value),
          FLANK_LEFT: parseDice(document.getElementById('field-def-flank-left').value),
          FLANK_RIGHT: parseDice(document.getElementById('field-def-flank-right').value),
          REAR: parseDice(document.getElementById('field-def-rear').value)
        },
        attack: attackObj,
        traits: document.getElementById('field-traits').value.split(',').map(s => s.trim()).filter(Boolean)
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
        showNotif("🚀 Unidad " + item.id + " publicada con éxito en unit_catalog.json!");
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
        path = parsed.path

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
            payload = {
                "catalog": catalog,
                "inventory": inventory.get("units", []),
                "staging": staging,
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        # Serve static assets (images from assets/art/...)
        if path.startswith("/assets/art/"):
            rel_path = path.lstrip("/")
            full_path = REPO_ROOT / rel_path
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
    print(f"🚀 Assault Unit Catalog Editor listening at http://127.0.0.1:{port}")
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
