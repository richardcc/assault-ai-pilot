"""Sincronizador canónico 100% MD -> HTML para la documentación de Assault.

Garantiza que:
1. `docs/index.html` (`embeddedDocsData`) contenga el 100% íntegro y exacto
   de todos los archivos Markdown canónicos de `docs/`, con la Hoja de Ruta
   (`05_ROADMAP_EVOLUTIVO.md`) siempre en la última posición (#09).
2. El sitio estático de MkDocs (`site/`) se regenere vía `mkdocs build`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
HTML_PATH = DOCS_DIR / "index.html"

CANONICAL_DOCS_ORDER = [
    {
        "id": "doc-00-index",
        "title": "00. Portal Canónico (Inicio)",
        "icon": "🏠",
        "file": "index.md",
        "desc": "Mapa de navegación del sistema, índice general de módulos y puertos activos.",
    },
    {
        "id": "doc-00-premisas",
        "title": "00. Premisas del Proyecto y Gobernanza",
        "icon": "📜",
        "file": "00_PREMISAS_DEL_PROYECTO.md",
        "desc": "Marco maestro de diseño: límites HW, palancas en RL, nivel 0, instrumentación y calidad.",
    },
    {
        "id": "doc-01",
        "title": "01. Arquitectura del Sistema",
        "icon": "🏗️",
        "file": "01_ARQUITECTURA_DEL_SISTEMA.md",
        "desc": "Visión general 5-tier, clean architecture, contratos y flujo de datos.",
    },
    {
        "id": "doc-02",
        "title": "02. Modelo del Juego y Reglas Tácticas",
        "icon": "♟️",
        "file": "02_MODELO_DEL_JUEGO_Y_REGLAS_TACTICAS.md",
        "desc": "Topología hexagonal, LOS, dados, combate, moral, State Loop autoritativo.",
    },
    {
        "id": "doc-03",
        "title": "03. Red Neuronal EfficientZero V2",
        "icon": "🧠",
        "file": "03_RED_NEURONAL_EFFICIENTZERO_V2.md",
        "desc": "Modelo de mundo, cabezas tácticas, HL-Gauss, Symlog, HRL Macro Nivel 1.",
    },
    {
        "id": "doc-04",
        "title": "04. Plataforma MLOps y Telemetría",
        "icon": "📊",
        "file": "04_PLATAFORMA_MLOPS_Y_TELEMETRIA.md",
        "desc": "DuckDB, Parquet, Promotion Gates, catálogo interactivo y Match Replay.",
    },
    {
        "id": "doc-05-audit",
        "title": "05. Auditoría Literatura Científica y Doctrinal",
        "icon": "🔬",
        "file": "06_LITERATURE_AUDIT_CHANNELS_HEADS_TACTICS.md",
        "desc": "Estudio comparativo Palma et al. (2025), DeepMind, Dunnigan, Sun Tzu y Henry Hyde.",
    },
    {
        "id": "doc-06-rag",
        "title": "06. Sistema RAG Copilot",
        "icon": "🤖",
        "file": "06_SISTEMA_RAG_COPILOT.md",
        "desc": "BM25 híbrido, SitRep en vivo, explicabilidad normativa y soporte LLM local.",
    },
    {
        "id": "doc-07-apis",
        "title": "07. Servicios Backend y Catálogo de APIs",
        "icon": "⚡",
        "file": "07_SERVICIOS_BACKEND_Y_CATALOGO_APIS.md",
        "desc": "REST FastAPI (:8001), WebSocket binario MessagePack, RAG API y MLOps API (:8778).",
    },
    {
        "id": "doc-08-rules",
        "title": "08. Auditoría Reglamento vs. Engine",
        "icon": "⚖️",
        "file": "08_AUDITORIA_REGLAMENTO_VS_ENGINE.md",
        "desc": "Auditoría página a página del Rulebook rev6 (52 págs.) y Scenario Book (38 escenarios).",
    },
    {
        "id": "doc-13-metrics",
        "title": "09. Inventario Jerárquico Canónico de Métricas",
        "icon": "📐",
        "file": "13_INVENTARIO_CANONICO_METRICAS.md",
        "desc": "Taxonomía de 4 niveles, origen autoritativo, cero-invención y purgado de redundancias.",
    },
    {
        "id": "doc-09-roadmap",
        "title": "10. Hoja de Ruta Evolutiva (Roadmap)",
        "icon": "🗺️",
        "file": "05_ROADMAP_EVOLUTIVO.md",
        "desc": "Hitos completados (Fases 1-6, 6.1, 6.2, 6.5, Literatura SOTA) y Hoja de Ruta Unificada de Trabajo Pendiente.",
    },
]


def sync_index_html() -> None:
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"No existe {HTML_PATH}")

    payload = []
    for spec in CANONICAL_DOCS_ORDER:
        md_path = DOCS_DIR / spec["file"]
        if not md_path.exists():
            raise FileNotFoundError(f"Falta archivo Markdown canónico: {md_path}")
        md_text = md_path.read_text(encoding="utf-8")
        payload.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "icon": spec["icon"],
                "file": spec["file"],
                "desc": spec["desc"],
                "markdown": md_text,
            }
        )

    html_text = HTML_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<script id="embeddedDocsData" type="application/json">\s*)(\[.*?\])(\s*</script>)',
        flags=re.S,
    )
    match = pattern.search(html_text)
    if not match:
        raise RuntimeError("No se encontró el bloque <script id='embeddedDocsData'> en docs/index.html")

    serialized = json.dumps(payload, ensure_ascii=False)
    updated_html = html_text[: match.start(2)] + serialized + html_text[match.end(2) :]
    HTML_PATH.write_text(updated_html, encoding="utf-8")

    # Verificación estricta 1:1
    verify_match = pattern.search(HTML_PATH.read_text(encoding="utf-8"))
    loaded = json.loads(verify_match.group(2))
    assert len(loaded) == len(CANONICAL_DOCS_ORDER), "Número de documentos embebidos no coincide"
    for entry, spec in zip(loaded, CANONICAL_DOCS_ORDER):
        expected_md = (DOCS_DIR / spec["file"]).read_text(encoding="utf-8")
        assert entry["markdown"] == expected_md, f"Desajuste de contenido en {spec['file']}"
    print(f"[OK] docs/index.html sincronizado al 100% con {len(loaded)} archivos .md (último: {loaded[-1]['title']}).")


def build_mkdocs_site() -> None:
    venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable
    cmd = [python_exe, "-m", "mkdocs", "build"]
    res = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stdout)
        print(res.stderr, file=sys.stderr)
        raise RuntimeError("Fallo al ejecutar mkdocs build")
    print("[OK] Sitio estático MkDocs regenerado en site/ al 100%.")
    # Asegurar que el portal raíz de /docs/ sea el Hub Canónico interactivo
    import shutil
    shutil.copyfile(HTML_PATH, ROOT_DIR / "site" / "index.html")
    for spec in CANONICAL_DOCS_ORDER:
        doc_dir_name = spec["file"].replace(".md", "")
        target_dir = ROOT_DIR / "site" / doc_dir_name
        if target_dir.exists():
            redirect_html = f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Redirigiendo al Hub Canónico...</title>
  <meta http-equiv="refresh" content="0; url=../#{spec["id"]}">
  <script>window.location.replace("../#" + "{spec["id"]}");</script>
</head>
<body>
  Redirigiendo al portal canónico: <a href="../#{spec["id"]}">{spec["title"]}</a>
</body>
</html>'''
            (target_dir / "index.html").write_text(redirect_html, encoding="utf-8")
    print("[OK] Hub Canónico interactivo (docs/index.html) unificado al 100% como portal principal en site/index.html.")


if __name__ == "__main__":
    sync_index_html()
    build_mkdocs_site()
