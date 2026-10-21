"""Generador canónico de PDF para la documentación completa de Assault.

Compila los 21 módulos canónicos de documentación en un único documento
imprimible de alta calidad, renderizando:
- Portada ejecutiva y tabla de contenidos navegable.
- Formato tipográfico optimizado para lectura y archivo.
- Ecuaciones matemáticas KaTeX ($...$, $$...$$, \\[...\\]).
- Diagramas de arquitectura y flujo Mermaid.
- Tablas comparativas y callouts de alertas tácticas.
- Salida en: `docs/Assault_Documentacion_Tecnica_Completa.pdf`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Import canonical order from sync_docs_html
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
DOCS_DIR = ROOT_DIR / "docs"
PDF_OUT_PATH = DOCS_DIR / "Assault_Documentacion_Tecnica_Completa.pdf"
PRINT_HTML_PATH = DOCS_DIR / "docs_full_print_view.html"

from scripts.sync_docs_html import CANONICAL_DOCS_ORDER


def find_browser_executable() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def generate_full_docs_html() -> Path:
    docs_payload = []
    toc_items = []

    for idx, item in enumerate(CANONICAL_DOCS_ORDER, start=1):
        rel_file = item["file"]
        fp = DOCS_DIR / rel_file
        if not fp.exists():
            print(f"[WARN] Archivo no encontrado: {fp}")
            continue

        content = fp.read_text(encoding="utf-8", errors="replace")
        doc_id = item["id"]
        title = item["title"]

        docs_payload.append({
            "id": doc_id,
            "title": title,
            "icon": item.get("icon", "📄"),
            "desc": item.get("desc", ""),
            "content": content,
            "index": idx
        })
        toc_items.append({
            "id": doc_id,
            "title": title,
            "icon": item.get("icon", "📄"),
            "desc": item.get("desc", ""),
            "index": idx
        })

    payload_json = json.dumps(docs_payload, ensure_ascii=False)
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Assault Wargame & AI Platform — Documentación Técnica Completa</title>

  <!-- Google Fonts for Print Quality -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700&family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">

  <!-- KaTeX for Mathematics -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>

  <!-- Marked.js for Markdown -->
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>

  <!-- Mermaid for Diagrams -->
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>

  <style>
    @page {{
      size: A4;
      margin: 20mm 15mm 20mm 15mm;
      @bottom-center {{
        content: counter(page);
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 9pt;
        color: #64748b;
      }}
    }}

    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 10pt;
      line-height: 1.6;
      color: #0f172a;
      background: #ffffff;
      margin: 0;
      padding: 0;
    }}

    /* Cover Page */
    .cover-page {{
      height: 100vh;
      display: flex;
      flex-direction: column;
      justifyContent: center;
      align-items: center;
      text-align: center;
      page-break-after: always;
      break-after: page;
      padding: 40px;
      border: 4px double #0284c7;
      margin-bottom: 40px;
    }}

    .cover-title {{
      font-family: 'Cinzel', serif;
      font-size: 28pt;
      font-weight: 700;
      letter-spacing: 2px;
      color: #0369a1;
      margin-bottom: 12px;
      text-transform: uppercase;
    }}

    .cover-subtitle {{
      font-size: 15pt;
      font-weight: 600;
      color: #334155;
      margin-bottom: 30px;
      max-width: 600px;
    }}

    .cover-badge {{
      display: inline-block;
      padding: 6px 16px;
      background: #e0f2fe;
      color: #0369a1;
      border: 1px solid #7dd3fc;
      border-radius: 20px;
      font-weight: 700;
      font-size: 11pt;
      margin-bottom: 40px;
    }}

    .cover-meta {{
      font-size: 10pt;
      color: #64748b;
      margin-top: 60px;
      line-height: 1.8;
    }}

    /* Table of Contents */
    .toc-page {{
      page-break-after: always;
      break-after: page;
      padding-top: 20px;
    }}

    .toc-title {{
      font-size: 20pt;
      font-weight: 800;
      color: #0369a1;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 8px;
      margin-bottom: 24px;
    }}

    .toc-grid {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .toc-item {{
      display: flex;
      justifyContent: space-between;
      align-items: baseline;
      padding: 6px 0;
      border-bottom: 1px dotted #cbd5e1;
      font-size: 10pt;
    }}

    .toc-link {{
      color: #0f172a;
      text-decoration: none;
      font-weight: 600;
    }}

    .toc-desc {{
      color: #64748b;
      font-size: 8.5pt;
      margin-left: 24px;
    }}

    /* Document Chapter */
    .doc-chapter {{
      page-break-before: always;
      break-before: page;
      padding-top: 20px;
      margin-bottom: 40px;
    }}

    .chapter-header {{
      border-bottom: 2px solid #0284c7;
      padding-bottom: 10px;
      margin-bottom: 24px;
    }}

    .chapter-title {{
      font-size: 18pt;
      font-weight: 800;
      color: #0369a1;
      margin-bottom: 4px;
    }}

    .chapter-desc {{
      font-size: 10pt;
      color: #64748b;
      font-style: italic;
    }}

    /* Content Typography & Tables */
    h1, h2, h3, h4 {{
      color: #0f172a;
      font-weight: 700;
      margin-top: 20px;
      margin-bottom: 10px;
      page-break-after: avoid;
      break-after: avoid;
    }}

    h1 {{ font-size: 15pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; color: #0369a1; }}
    h2 {{ font-size: 13pt; border-bottom: 1px solid #f1f5f9; padding-bottom: 2px; color: #0284c7; }}
    h3 {{ font-size: 11pt; color: #334155; }}
    h4 {{ font-size: 10pt; color: #475569; }}

    p {{
      margin-bottom: 10px;
      text-align: justify;
    }}

    ul, ol {{
      margin-left: 20px;
      margin-bottom: 12px;
    }}

    li {{
      margin-bottom: 4px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      font-size: 8.5pt;
      page-break-inside: auto;
    }}

    tr {{
      page-break-inside: avoid;
      page-break-after: auto;
    }}

    th, td {{
      padding: 6px 8px;
      border: 1px solid #cbd5e1;
      text-align: left;
    }}

    th {{
      background-color: #f8fafc;
      font-weight: 700;
      color: #1e293b;
    }}

    tr:nth-child(even) {{
      background-color: #f8fafc;
    }}

    code {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 8.5pt;
      background: #f1f5f9;
      color: #0f172a;
      padding: 2px 4px;
      border-radius: 3px;
      border: 1px solid #e2e8f0;
    }}

    pre {{
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 10px 14px;
      overflow-x: auto;
      margin: 14px 0;
      page-break-inside: avoid;
    }}

    pre code {{
      background: transparent;
      padding: 0;
      border: none;
      font-size: 8pt;
      line-height: 1.4;
    }}

    blockquote {{
      margin: 14px 0;
      padding: 8px 14px;
      background: #f0f9ff;
      border-left: 4px solid #0284c7;
      color: #0369a1;
      font-size: 9pt;
      page-break-inside: avoid;
    }}

    blockquote strong {{
      color: #0284c7;
    }}

    .mermaid {{
      margin: 20px 0;
      text-align: center;
      page-break-inside: avoid;
    }}

    .mermaid svg {{
      max-width: 100% !important;
      height: auto !important;
    }}
  </style>
</head>
<body>

  <!-- Cover Page -->
  <div class="cover-page">
    <div style="font-size: 40pt; margin-bottom: 10px;">♟️</div>
    <div class="cover-title">ASSAULT WARGAME & AI PLATFORM</div>
    <div class="cover-subtitle">Documentación Técnica Canónica y Hoja de Ruta de Arquitectura (2024–2027)</div>
    <div class="cover-badge">EFFICIENTZERO V2 • VOEC SIM • MLOPS FORENSE DUCKDB • WARGAME REV6</div>
    <div class="cover-meta">
      <div><b>Edición Completa Unificada (21 Módulos Canónicos)</b></div>
      <div>Fecha de Generación: {now_str}</div>
      <div>Plataforma de Simulación y Motor de Inteligencia Artificial</div>
    </div>
  </div>

  <!-- Table of Contents -->
  <div class="toc-page">
    <div class="toc-title">Índice General de Módulos Técnicos</div>
    <div class="toc-grid">
"""

    for item in toc_items:
        html_content += f"""      <div class="toc-item">
        <a class="toc-link" href="#{item['id']}">
          <span>{item['icon']}</span> {item['title']}
        </a>
      </div>
      <div class="toc-desc">{item['desc']}</div>
"""

    html_content += f"""    </div>
  </div>

  <!-- Container for rendered markdown modules -->
  <div id="content-container"></div>

  <script>
    const docsData = {payload_json};
    const container = document.getElementById("content-container");

    // Initialize Mermaid
    mermaid.initialize({{
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose',
      fontFamily: 'Plus Jakarta Sans',
      fontSize: 12
    }});

    // Configure Marked
    marked.setOptions({{
      gfm: true,
      breaks: false,
      tables: true
    }});

    // Render each document module
    docsData.forEach((doc) => {{
      const chapter = document.createElement("div");
      chapter.className = "doc-chapter";
      chapter.id = doc.id;

      // Clean markdown content: remove HTML comments
      let cleanMd = doc.content.replace(/<!--[\\s\\S]*?-->/g, "");

      // Render markdown to HTML
      let html = marked.parse(cleanMd);

      chapter.innerHTML = `
        <div class="chapter-header">
          <div class="chapter-title">${{doc.icon}} ${{doc.title}}</div>
          <div class="chapter-desc">${{doc.desc}}</div>
        </div>
        <div class="doc-body">${{html}}</div>
      `;

      container.appendChild(chapter);
    }});

    // Render KaTeX Math
    renderMathInElement(document.body, {{
      delimiters: [
        {{left: '$$', right: '$$', display: true}},
        {{left: '$', right: '$', display: false}},
        {{left: '\\\\[', right: '\\\\]', display: true}},
        {{left: '\\\\(', right: '\\\\)', display: false}}
      ],
      throwOnError: false
    }});

    // Render Mermaid diagrams
    async function renderMermaidDiagrams() {{
      const codeBlocks = document.querySelectorAll("pre code.language-mermaid");
      for (let i = 0; i < codeBlocks.length; i++) {{
        const code = codeBlocks[i];
        const pre = code.parentElement;
        const text = code.textContent;
        const div = document.createElement("div");
        div.className = "mermaid";
        div.id = "mermaid-" + i;
        try {{
          const {{ svg }} = await mermaid.render("mermaid-svg-" + i, text);
          div.innerHTML = svg;
          pre.parentNode.replaceChild(div, pre);
        }} catch (err) {{
          console.warn("Mermaid render error:", err);
        }}
      }}
      // Signal ready
      document.body.setAttribute("data-render-ready", "true");
    }}

    renderMermaidDiagrams();
  </script>
</body>
</html>
"""

    PRINT_HTML_PATH.write_text(html_content, encoding="utf-8")
    return PRINT_HTML_PATH


def main():
    print("=" * 70)
    print(" GENERADOR DE PDF DE DOCUMENTACIÓN CANÓNICA COMPLETA (ASSAULT)")
    print("=" * 70)

    browser = find_browser_executable()
    if not browser:
        print("[ERROR] No se encontró Microsoft Edge ni Google Chrome para compilar el PDF.")
        sys.exit(1)

    print(f"[1/3] Generando vista imprimible HTML unificada (21 módulos canónicos)...")
    html_path = generate_full_docs_html()
    print(f"      Vista HTML generada en: {html_path} ({os.path.getsize(html_path):,} bytes)")

    print(f"[2/3] Compilando a PDF con motor Chromium headless ({os.path.basename(browser)})...")
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=15000",
        f"--print-to-pdf={PDF_OUT_PATH}",
        f"file:///{html_path.resolve()}"
    ]

    t0 = time.time()
    try:
        subprocess.run(cmd, check=True, timeout=120)
    except Exception as e:
        print(f"[ERROR] Error al compilar el PDF: {e}")
        sys.exit(1)

    elapsed = time.time() - t0
    if PDF_OUT_PATH.exists():
        size_mb = os.path.getsize(PDF_OUT_PATH) / (1024 * 1024)
        print(f"[3/3] ¡PDF generado con éxito en {elapsed:.1f}s!")
        print(f"      Archivo: {PDF_OUT_PATH}")
        print(f"      Tamaño : {size_mb:.2f} MB")
        print("=" * 70)
    else:
        print("[ERROR] El archivo PDF no se generó.")
        sys.exit(1)


if __name__ == "__main__":
    main()
