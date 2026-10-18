"""
Builds the standalone, fully interactive HTML documentation portal (docs/index.html)
by embedding all 6 canonical markdown documents with client-side Marked.js,
Mermaid.js, and KaTeX rendering.
"""
from pathlib import Path
import json

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

DOC_FILES = [
    {
        "id": "doc-01",
        "title": "01. Arquitectura del Sistema",
        "icon": "🏗️",
        "file": "01_ARQUITECTURA_DEL_SISTEMA.md",
        "desc": "Visión general 5-tier, clean architecture, contratos y flujo de datos."
    },
    {
        "id": "doc-02",
        "title": "02. Modelo del Juego y Reglas Tácticas",
        "icon": "♟️",
        "file": "02_MODELO_DEL_JUEGO_Y_REGLAS_TACTICAS.md",
        "desc": "Topología hexagonal, LOS, dados, combate, moral, State Loop autoritativo."
    },
    {
        "id": "doc-03",
        "title": "03. Red Neuronal EfficientZero V2",
        "icon": "🧠",
        "file": "03_RED_NEURONAL_EFFICIENTZERO_V2.md",
        "desc": "Modelo de mundo, cabezas tácticas, HL-Gauss, Symlog, HRL Macro Nivel 1."
    },
    {
        "id": "doc-04",
        "title": "04. Plataforma MLOps y Telemetría",
        "icon": "📊",
        "file": "04_PLATAFORMA_MLOPS_Y_TELEMETRIA.md",
        "desc": "DuckDB, Parquet, promotion gates, backend multihilo y simulador 5173."
    },
    {
        "id": "doc-05",
        "title": "05. Hoja de Ruta Evolutiva (Roadmap)",
        "icon": "🛣️",
        "file": "05_ROADMAP_EVOLUTIVO.md",
        "desc": "Matriz de síntesis de la auditoría técnica y fases evolutivas 1 a 5."
    },
    {
        "id": "doc-06",
        "title": "06. Sistema RAG Copilot",
        "icon": "🤖",
        "file": "06_SISTEMA_RAG_COPILOT.md",
        "desc": "Base de conocimiento, recuperador híbrido BM25, Ollama y APIs REST."
    },
    {
        "id": "doc-07",
        "title": "07. Servicios Backend y Catálogo de APIs",
        "icon": "⚡",
        "file": "07_SERVICIOS_BACKEND_Y_CATALOGO_APIS.md",
        "desc": "Catálogo exhaustivo de endpoints REST, WebSocket, esquemas OpenAPI y Swagger UI (8001 y 8778)."
    }
]

def load_docs_data():
    docs_data = []
    for d in DOC_FILES:
        filepath = DOCS_DIR / d["file"]
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
        else:
            content = f"# Error: {d['file']} no encontrado."
        docs_data.append({
            "id": d["id"],
            "title": d["title"],
            "icon": d["icon"],
            "file": d["file"],
            "desc": d["desc"],
            "markdown": content
        })
    return docs_data

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Assault Wargame & AI Platform — Portal Canónico de Documentación</title>
  
  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  
  <!-- KaTeX -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>

  <!-- Marked.js for Markdown parsing -->
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>

  <!-- Mermaid for diagrams -->
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>

  <style>
    :root {
      --bg-dark: #080d1a;
      --bg-card: #0f172a;
      --bg-elevated: #1e293b;
      --border: #223147;
      --border-accent: #0284c7;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-cyan: #38bdf8;
      --accent-green: #34d399;
      --accent-purple: #c084fc;
      --accent-amber: #fbbf24;
      --accent-rose: #f43f5e;
      --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-dark);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.7;
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }

    /* Top Navigation Bar */
    header {
      background: var(--bg-card);
      border-bottom: 1px solid var(--border);
      padding: 10px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
      z-index: 50;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 15px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: #fff;
    }
    .brand-badge {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid var(--accent-cyan);
      color: var(--accent-cyan);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 4px;
      font-weight: 700;
    }
    .header-links {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .btn-link {
      background: var(--bg-elevated);
      color: var(--accent-cyan);
      border: 1px solid var(--border);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
      cursor: pointer;
    }
    .btn-link:hover {
      background: rgba(2, 132, 199, 0.2);
      border-color: var(--accent-cyan);
      color: #fff;
    }
    .btn-link.active {
      background: #0284c7;
      border-color: #38bdf8;
      color: #fff;
    }

    /* Layout Wrapper */
    .app-layout {
      display: flex;
      flex: 1;
      overflow: hidden;
    }

    /* Sidebar Navigation */
    aside {
      width: 330px;
      background: #0b1325;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }
    .search-box {
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
    }
    .search-input {
      width: 100%;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: #fff;
      padding: 8px 12px;
      font-size: 13px;
      outline: none;
      font-family: inherit;
    }
    .search-input:focus {
      border-color: var(--accent-cyan);
    }
    .doc-nav-list {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .nav-doc-card {
      padding: 10px 12px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .nav-doc-card:hover {
      border-color: var(--accent-cyan);
      background: rgba(2, 132, 199, 0.1);
    }
    .nav-doc-card.active {
      border-color: var(--accent-cyan);
      background: rgba(2, 132, 199, 0.2);
      border-left: 4px solid var(--accent-cyan);
    }
    .nav-doc-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .nav-doc-desc {
      font-size: 11.5px;
      color: var(--text-muted);
      line-height: 1.4;
    }

    /* Table of contents in current doc */
    .toc-container {
      border-top: 1px solid var(--border);
      padding: 12px 16px;
      max-height: 240px;
      overflow-y: auto;
      background: rgba(11, 19, 37, 0.8);
    }
    .toc-title {
      font-size: 11px;
      font-weight: 800;
      color: var(--accent-cyan);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
    }
    .toc-link {
      display: block;
      font-size: 12px;
      color: #94a3b8;
      text-decoration: none;
      padding: 3px 0;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: color 0.15s ease;
    }
    .toc-link:hover { color: #fff; }
    .toc-link.h3 { padding-left: 12px; font-size: 11.5px; }

    /* Main Content Area */
    main {
      flex: 1;
      overflow-y: auto;
      padding: 36px 48px;
      scroll-behavior: smooth;
      background: var(--bg-dark);
    }
    .content-wrapper {
      max-width: 1040px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 32px;
    }

    /* Markdown Rendered Typography */
    .markdown-body {
      color: #cbd5e1;
      font-size: 14.5px;
      line-height: 1.75;
    }
    .markdown-body h1 {
      font-size: 30px;
      font-weight: 800;
      color: #fff;
      letter-spacing: -0.02em;
      border-bottom: 2px solid var(--border);
      padding-bottom: 12px;
      margin-top: 24px;
      margin-bottom: 20px;
    }
    .markdown-body h2 {
      font-size: 22px;
      font-weight: 800;
      color: var(--accent-cyan);
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
      margin-top: 36px;
      margin-bottom: 16px;
    }
    .markdown-body h3 {
      font-size: 17px;
      font-weight: 700;
      color: #f8fafc;
      margin-top: 24px;
      margin-bottom: 12px;
    }
    .markdown-body h4 {
      font-size: 15px;
      font-weight: 700;
      color: var(--accent-amber);
      margin-top: 18px;
      margin-bottom: 8px;
    }
    .markdown-body p { margin-bottom: 16px; }
    .markdown-body ul, .markdown-body ol {
      margin-bottom: 16px;
      padding-left: 24px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .markdown-body li strong { color: #fff; }
    .markdown-body blockquote {
      border-left: 4px solid var(--accent-cyan);
      background: rgba(2, 132, 199, 0.08);
      padding: 12px 18px;
      border-radius: 0 8px 8px 0;
      margin: 16px 0;
      color: #94a3b8;
      font-size: 14px;
    }
    .markdown-body blockquote strong { color: #f8fafc; }
    
    /* Code and Pre */
    .markdown-body code {
      font-family: var(--font-mono);
      font-size: 13px;
      background: #1e293b;
      color: var(--accent-cyan);
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .markdown-body pre {
      background: #090e1a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
      margin: 16px 0;
    }
    .markdown-body pre code {
      background: transparent;
      padding: 0;
      border: none;
      color: #f1f5f9;
      font-size: 13px;
    }

    /* Tables */
    .markdown-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0;
      font-size: 13.5px;
    }
    .markdown-body th {
      background: #131d31;
      color: #94a3b8;
      font-weight: 700;
      text-align: left;
      padding: 10px 14px;
      border: 1px solid var(--border);
    }
    .markdown-body td {
      padding: 10px 14px;
      border: 1px solid var(--border);
      color: #e2e8f0;
    }
    .markdown-body tr:nth-child(even) td {
      background: rgba(22, 33, 56, 0.4);
    }
    .markdown-body tr:hover td {
      background: rgba(56, 189, 248, 0.05);
    }

    /* Math display styling */
    .math-display {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 20px;
      margin: 16px 0;
      text-align: center;
      overflow-x: auto;
      font-size: 16px;
      color: var(--accent-cyan);
    }

    /* Mermaid diagrams container & wrapper */
    .mermaid-wrapper {
      background: #090e1a;
      border: 1px solid var(--border);
      border-radius: 12px;
      margin: 28px 0;
      overflow: hidden;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
    }
    .mermaid-header {
      background: #0f172a;
      border-bottom: 1px solid var(--border);
      padding: 10px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 10px;
    }
    .mermaid-header-title {
      font-size: 12px;
      font-weight: 700;
      color: var(--accent-cyan);
      display: flex;
      align-items: center;
      gap: 8px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .mermaid-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .mermaid-btn {
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      color: #cbd5e1;
      font-size: 11px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .mermaid-btn:hover {
      background: #0284c7;
      color: #fff;
      border-color: #38bdf8;
    }
    .mermaid-container {
      padding: 28px 20px;
      overflow-x: auto;
      overflow-y: hidden;
      text-align: center;
      background: radial-gradient(circle at center, #111a2f 0%, #070c17 100%);
      position: relative;
    }
    .mermaid-container svg {
      display: inline-block !important;
      margin: 0 auto !important;
      width: 100% !important;
      max-width: 1100px !important;
      min-width: min(100%, 750px) !important;
      height: auto !important;
    }

    /* Fullscreen Modal for diagrams */
    .diagram-modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(4, 7, 15, 0.95);
      backdrop-filter: blur(10px);
      z-index: 9999;
      padding: 24px;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    .diagram-modal.open {
      display: flex;
    }
    .diagram-modal-box {
      background: #0b1325;
      border: 1px solid var(--border-accent);
      border-radius: 14px;
      width: 95vw;
      height: 90vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.85);
      overflow: hidden;
    }
    .diagram-modal-topbar {
      padding: 12px 20px;
      background: #0f172a;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .diagram-modal-title {
      font-size: 14px;
      font-weight: 800;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .diagram-modal-body {
      flex: 1;
      overflow: auto;
      padding: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #070c17;
    }
    .diagram-modal-body svg {
      width: 100% !important;
      max-width: 1600px !important;
      min-width: 900px !important;
      height: auto !important;
    }

    /* Document header badge */
    .doc-meta-banner {
      background: #0b1426;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .doc-meta-left {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .doc-icon-large {
      font-size: 32px;
    }
    .doc-meta-title {
      font-size: 18px;
      font-weight: 800;
      color: #fff;
    }
    .doc-meta-desc {
      font-size: 12.5px;
      color: var(--text-muted);
    }
  </style>
</head>
<body>

  <!-- Top Header -->
  <header>
    <div class="brand">
      <span>🛡️</span> Assault Documentation Hub
      <span class="brand-badge">EfficientZero V2 Canónico</span>
    </div>
    <div class="header-links">
      <button class="btn-link" id="btnAllDocs" onclick="switchDocument('all')">📚 Vista Completa (Todos)</button>
      <a href="http://127.0.0.1:8001/docs" target="_blank" class="btn-link" style="border-color: #38bdf8; color: #38bdf8;">⚡ Swagger UI (8001)</a>
      <a href="http://127.0.0.1:8001/redoc" target="_blank" class="btn-link">📖 ReDoc (8001)</a>
      <a href="http://127.0.0.1:8778" class="btn-link">📊 MLOps Viewer (8778)</a>
      <a href="http://localhost:5173" target="_blank" class="btn-link">🎮 Simulador Táctico (5173)</a>
    </div>
  </header>

  <!-- Main Application Layout -->
  <div class="app-layout">
    
    <!-- Sidebar -->
    <aside>
      <div class="search-box">
        <input type="text" id="docSearch" class="search-input" placeholder="🔍 Buscar en toda la documentación...">
      </div>
      
      <div class="doc-nav-list" id="docNavList">
        <!-- Generated Nav Items -->
      </div>

      <div class="toc-container" id="tocContainer">
        <div class="toc-title">En este documento</div>
        <div id="tocLinks"></div>
      </div>
    </aside>

    <!-- Main Content Reader -->
    <main id="mainContent">
      <div class="content-wrapper" id="contentWrapper">
        <!-- Rendered Markdown will be injected here -->
      </div>
    </main>

  </div>

  <!-- Fullscreen Diagram Inspection Modal -->
  <div class="diagram-modal" id="diagramModal" onclick="if(event.target===this)closeDiagramModal()">
    <div class="diagram-modal-box">
      <div class="diagram-modal-topbar">
        <div class="diagram-modal-title">
          <span>🔍</span> Visor Táctico de Diagrama en Alta Resolución
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="mermaid-btn" onclick="modalZoom(1.2)">🔍 +</button>
          <button class="mermaid-btn" onclick="modalZoom(0.8)">🔍 -</button>
          <button class="mermaid-btn" onclick="modalReset()">↺ Reset</button>
          <button class="mermaid-btn" style="background:#e11d48; color:#fff;" onclick="closeDiagramModal()">✕ Cerrar</button>
        </div>
      </div>
      <div class="diagram-modal-body" id="diagramModalBody">
      </div>
    </div>
  </div>

  <!-- Raw Embedded Markdown Data -->
  <script id="embeddedDocsData" type="application/json">
    ###EMBEDDED_JSON###
  </script>

  <script>
    // Initialize Mermaid with Dark Tactical Theme and large readable typography
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        curve: 'basis'
      },
      sequence: {
        useMaxWidth: false
      },
      state: {
        useMaxWidth: false
      },
      themeVariables: {
        darkMode: true,
        background: '#090e1a',
        primaryColor: '#1e293b',
        primaryTextColor: '#f8fafc',
        primaryBorderColor: '#38bdf8',
        lineColor: '#38bdf8',
        secondaryColor: '#1e3a8a',
        tertiaryColor: '#0f172a',
        fontSize: '15px',
        fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif"
      }
    });

    const docsData = JSON.parse(document.getElementById('embeddedDocsData').textContent);
    let currentDocId = docsData[0].id;
    const diagramScales = {};
    let modalScale = 1.0;

    // Build Sidebar Nav Items
    const docNavList = document.getElementById('docNavList');
    docsData.forEach(d => {
      const card = document.createElement('div');
      card.className = 'nav-doc-card' + (d.id === currentDocId ? ' active' : '');
      card.id = `nav-${d.id}`;
      card.onclick = () => switchDocument(d.id);
      card.innerHTML = `
        <div class="nav-doc-title"><span>${d.icon}</span> ${d.title}</div>
        <div class="nav-doc-desc">${d.desc}</div>
      `;
      docNavList.appendChild(card);
    });

    // Custom marked renderer for math & mermaid
    let diagramCounter = 0;
    function parseAndRenderMarkdown(markdownText) {
      // 1. Preprocess: Protect display math $$...$$
      const mathBlocks = [];
      let processed = markdownText.replace(/\\$\\$([\\s\\S]*?)\\$\\$/g, (match, formula) => {
        const id = `MATH_BLOCK_${mathBlocks.length}`;
        mathBlocks.push(formula);
        return id;
      });

      // 2. Parse Markdown
      let html = marked.parse(processed);

      // 3. Restore Math Blocks as div.math-display
      mathBlocks.forEach((formula, idx) => {
        html = html.replace(`<p>MATH_BLOCK_${idx}</p>`, `<div class="math-display">$$${formula}$$</div>`);
        html = html.replace(`MATH_BLOCK_${idx}`, `<div class="math-display">$$${formula}$$</div>`);
      });

      // 4. Transform <pre><code class="language-mermaid"> into responsive interactive containers
      html = html.replace(/<pre><code class="language-mermaid">([\\s\\S]*?)<\\/code><\\/pre>/g, (match, code) => {
        diagramCounter++;
        const diagId = `diagram-${diagramCounter}`;
        const decoded = code
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&amp;/g, '&')
          .replace(/&quot;/g, '"');
        return `
          <div class="mermaid-wrapper" id="wrap-${diagId}">
            <div class="mermaid-header">
              <span class="mermaid-header-title">📊 Diagrama Táctico #${diagramCounter}</span>
              <div class="mermaid-actions">
                <button class="mermaid-btn" onclick="zoomDiagram('${diagId}', 1.25)" title="Acercar">🔍 +</button>
                <button class="mermaid-btn" onclick="zoomDiagram('${diagId}', 0.8)" title="Alejar">🔍 -</button>
                <button class="mermaid-btn" onclick="resetZoom('${diagId}')" title="Restablecer">↺ Reset</button>
                <button class="mermaid-btn" onclick="openDiagramModal('${diagId}')" title="Ver en Pantalla Completa">⛶ Pantalla Completa</button>
              </div>
            </div>
            <div class="mermaid-container" id="${diagId}">
              <pre class="mermaid">${decoded}</pre>
            </div>
          </div>
        `;
      });

      return html;
    }

    // Switch active document
    function switchDocument(docId) {
      currentDocId = docId;
      diagramCounter = 0;

      // Update sidebar active classes
      document.querySelectorAll('.nav-doc-card').forEach(c => c.classList.remove('active'));
      const activeCard = document.getElementById(`nav-${docId}`);
      if (activeCard) activeCard.classList.add('active');

      const btnAll = document.getElementById('btnAllDocs');
      if (docId === 'all') {
        btnAll.classList.add('active');
      } else {
        btnAll.classList.remove('active');
      }

      const wrapper = document.getElementById('contentWrapper');
      wrapper.innerHTML = '';

      if (docId === 'all') {
        // Render all docs sequentially
        docsData.forEach(d => {
          const docSection = document.createElement('div');
          docSection.className = 'markdown-body';
          docSection.id = d.id;
          docSection.innerHTML = `
            <div class="doc-meta-banner">
              <div class="doc-meta-left">
                <span class="doc-icon-large">${d.icon}</span>
                <div>
                  <div class="doc-meta-title">${d.title}</div>
                  <div class="doc-meta-desc">${d.desc}</div>
                </div>
              </div>
              <a href="/docs/${d.file}" class="btn-link" target="_blank">📄 Ver Markdown Crudo (${d.file})</a>
            </div>
            ${parseAndRenderMarkdown(d.markdown)}
            <hr style="border: 0; border-top: 2px dashed var(--border); margin: 48px 0;">
          `;
          wrapper.appendChild(docSection);
        });
      } else {
        const doc = docsData.find(d => d.id === docId);
        if (doc) {
          const docSection = document.createElement('div');
          docSection.className = 'markdown-body';
          docSection.id = doc.id;
          docSection.innerHTML = `
            <div class="doc-meta-banner">
              <div class="doc-meta-left">
                <span class="doc-icon-large">${doc.icon}</span>
                <div>
                  <div class="doc-meta-title">${doc.title}</div>
                  <div class="doc-meta-desc">${doc.desc}</div>
                </div>
              </div>
              <a href="/docs/${doc.file}" class="btn-link" target="_blank">📄 Ver Markdown Crudo (${doc.file})</a>
            </div>
            ${parseAndRenderMarkdown(doc.markdown)}
          `;
          wrapper.appendChild(docSection);
        }
      }

      // Re-run Mermaid & KaTeX on injected content
      setTimeout(async () => {
        try {
          await mermaid.run();
          // Clean Mermaid's inline constraints so SVGs render crisp and wide
          document.querySelectorAll('.mermaid-container svg').forEach(svg => {
            svg.removeAttribute('height');
            svg.style.maxWidth = '1100px';
            svg.style.width = '100%';
            svg.style.minWidth = 'min(100%, 750px)';
            svg.style.height = 'auto';
            svg.style.fontFamily = "'Plus Jakarta Sans', system-ui, sans-serif";
          });
        } catch (e) {
          console.warn("Mermaid run warning:", e);
        }

        if (window.renderMathInElement) {
          renderMathInElement(wrapper, {
            delimiters: [
              {left: '$$', right: '$$', display: true},
              {left: '\\\\[', right: '\\\\]', display: true},
              {left: '\\\\(', right: '\\\\)', display: false},
              {left: '$', right: '$', display: false}
            ],
            throwOnError: false,
            ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code"]
          });
        }

        // Rebuild Table of Contents for the active document
        buildTableOfContents();

        // Scroll back to top
        document.getElementById('mainContent').scrollTop = 0;
      }, 50);
    }

    // Interactive Diagram Zoom Controls
    function zoomDiagram(diagId, factor) {
      const container = document.getElementById(diagId);
      if (!container) return;
      const svg = container.querySelector('svg');
      if (!svg) return;
      
      const currentScale = diagramScales[diagId] || 1.0;
      const newScale = Math.min(Math.max(currentScale * factor, 0.5), 3.0);
      diagramScales[diagId] = newScale;
      
      svg.style.transformOrigin = 'center top';
      svg.style.transform = `scale(${newScale})`;
      svg.style.transition = 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
    }

    function resetZoom(diagId) {
      const container = document.getElementById(diagId);
      if (!container) return;
      const svg = container.querySelector('svg');
      if (!svg) return;
      diagramScales[diagId] = 1.0;
      svg.style.transform = 'scale(1.0)';
    }

    // Modal Fullscreen Functions
    function openDiagramModal(diagId) {
      const container = document.getElementById(diagId);
      if (!container) return;
      const svg = container.querySelector('svg');
      if (!svg) return;
      
      const modal = document.getElementById('diagramModal');
      const modalBody = document.getElementById('diagramModalBody');
      modalBody.innerHTML = svg.outerHTML;
      const modalSvg = modalBody.querySelector('svg');
      if (modalSvg) {
        modalSvg.style.width = '100%';
        modalSvg.style.minWidth = '900px';
        modalSvg.style.maxWidth = '1500px';
        modalSvg.style.height = 'auto';
        modalSvg.style.transform = 'none';
      }
      modalScale = 1.0;
      modal.classList.add('open');
    }

    function closeDiagramModal() {
      const modal = document.getElementById('diagramModal');
      modal.classList.remove('open');
    }

    function modalZoom(factor) {
      const modalBody = document.getElementById('diagramModalBody');
      const svg = modalBody.querySelector('svg');
      if (!svg) return;
      modalScale = Math.min(Math.max(modalScale * factor, 0.5), 4.0);
      svg.style.transformOrigin = 'center center';
      svg.style.transform = `scale(${modalScale})`;
      svg.style.transition = 'transform 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
    }

    function modalReset() {
      const modalBody = document.getElementById('diagramModalBody');
      const svg = modalBody.querySelector('svg');
      if (!svg) return;
      modalScale = 1.0;
      svg.style.transform = 'scale(1.0)';
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDiagramModal();
    });

    // Build Table of Contents dynamically from rendered headers
    function buildTableOfContents() {
      const tocLinks = document.getElementById('tocLinks');
      tocLinks.innerHTML = '';
      const headers = document.querySelectorAll('.markdown-body h2, .markdown-body h3');
      headers.forEach((h, index) => {
        if (!h.id) {
          h.id = 'heading-' + index;
        }
        const a = document.createElement('a');
        a.className = 'toc-link ' + (h.tagName.toLowerCase());
        a.href = '#' + h.id;
        a.textContent = h.textContent;
        tocLinks.appendChild(a);
      });
    }

    // Search filter across documents and headers
    const docSearch = document.getElementById('docSearch');
    docSearch.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase().trim();
      document.querySelectorAll('.nav-doc-card').forEach(card => {
        const text = card.textContent.toLowerCase();
        card.style.display = (term === '' || text.includes(term)) ? 'flex' : 'none';
      });
    });

    // Initial render
    switchDocument(currentDocId);
  </script>
</body>
</html>
"""

def main():
    docs_data = load_docs_data()
    json_data = json.dumps(docs_data, ensure_ascii=False)
    # Escape closing script tag if any inside json
    json_data = json_data.replace("</script>", "<\\/script>")
    output_html = HTML_TEMPLATE.replace("###EMBEDDED_JSON###", json_data)
    
    out_file = DOCS_DIR / "index.html"
    out_file.write_text(output_html, encoding="utf-8")
    print(f"[OK] Generated {out_file} with {len(docs_data)} full embedded documents.")

if __name__ == "__main__":
    main()
