"""Sincronizador canónico 100% MD -> HTML para la documentación de Assault.

Garantiza que:
1. `docs/index.html` (`embeddedDocsData`) contenga el 100% íntegro y exacto
   de todos los archivos Markdown canónicos de `docs/`, con la Hoja de Ruta
   (`05_ROADMAP_EVOLUTIVO.md`) siempre en la última posición (#13).
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
    # ─── I. GOBERNANZA Y ARQUITECTURA ───
    {
        "id": "doc-00-index",
        "category": "I. Gobernanza y Arquitectura",
        "category_icon": "🏛️",
        "title": "01. Portal Canónico (Inicio)",
        "icon": "🏠",
        "file": "index.md",
        "desc": "Mapa de navegación del sistema, índice general de módulos y puertos activos.",
    },
    {
        "id": "doc-00-premisas",
        "category": "I. Gobernanza y Arquitectura",
        "category_icon": "🏛️",
        "title": "02. Premisas del Proyecto y Gobernanza",
        "icon": "📜",
        "file": "00_PREMISAS_DEL_PROYECTO.md",
        "desc": "Marco maestro de diseño: límites HW, palancas en RL, nivel 0, instrumentación y calidad.",
    },
    {
        "id": "doc-01",
        "category": "I. Gobernanza y Arquitectura",
        "category_icon": "🏛️",
        "title": "03. Arquitectura del Sistema (5-Tier)",
        "icon": "🏗️",
        "file": "01_ARQUITECTURA_DEL_SISTEMA.md",
        "desc": "Visión general 5-tier, clean architecture, contratos y flujo de datos.",
    },

    # ─── II. MOTOR DEL WARGAME Y REGLAS TÁCTICAS ───
    {
        "id": "doc-02",
        "category": "II. Motor Wargame y Reglas Tácticas",
        "category_icon": "♟️",
        "title": "04. Modelo del Juego y Reglas Tácticas",
        "icon": "🎲",
        "file": "02_MODELO_DEL_JUEGO_Y_REGLAS_TACTICAS.md",
        "desc": "Topología hexagonal, LOS, dados, combate, moral, State Loop autoritativo.",
    },
    {
        "id": "doc-08-rules",
        "category": "II. Motor Wargame y Reglas Tácticas",
        "category_icon": "♟️",
        "title": "05. Auditoría Reglamento vs. Engine",
        "icon": "⚖️",
        "file": "08_AUDITORIA_REGLAMENTO_VS_ENGINE.md",
        "desc": "Auditoría página a página del Rulebook rev6 (52 págs.) y Scenario Book (38 escenarios).",
    },

    # ─── III. INTELIGENCIA ARTIFICIAL (EFFICIENTZERO V2) ───
    {
        "id": "doc-03",
        "category": "III. Inteligencia Artificial (EfficientZero V2)",
        "category_icon": "🧠",
        "title": "06. Red Neuronal EfficientZero V2",
        "icon": "🧠",
        "file": "03_RED_NEURONAL_EFFICIENTZERO_V2.md",
        "desc": "Modelo de mundo, cabezas tácticas, HL-Gauss, Symlog, HRL Macro Nivel 1.",
    },
    {
        "id": "doc-05-audit",
        "category": "III. Inteligencia Artificial (EfficientZero V2)",
        "category_icon": "🧠",
        "title": "07. Auditoría Literatura Científica y Doctrinal",
        "icon": "🔬",
        "file": "06_LITERATURE_AUDIT_CHANNELS_HEADS_TACTICS.md",
        "desc": "Estudio comparativo Palma et al. (2025), DeepMind, Dunnigan, Sun Tzu y Henry Hyde.",
    },
    {
        "id": "doc-14-profiling",
        "category": "III. Inteligencia Artificial (EfficientZero V2)",
        "category_icon": "🧠",
        "title": "08. Plan Estratégico Perfilado de Unidades IA",
        "icon": "🎖️",
        "file": "14_PLAN_PERFILADO_UNIDADES_IA.md",
        "desc": "Arquitectura doctrinal 3 capas, mutación dinámica contextual y observabilidad MLOps.",
    },
    {
        "id": "doc-15-curriculums",
        "category": "III. Inteligencia Artificial (EfficientZero V2)",
        "category_icon": "🧠",
        "title": "09. Currículums y Entrenamiento Progresivo",
        "icon": "🎯",
        "file": "15_CURRICULUMS_Y_ENTRENAMIENTO_PROGRESSIVO.md",
        "desc": "Currículum acelerado de VPs, currículum multi-escenario y puertas de calidad dinámicas.",
    },

    # ─── IV. MLOPS, TELEMETRÍA Y SERVICIOS ───
    {
        "id": "doc-04",
        "category": "IV. MLOps, Telemetría y Servicios",
        "category_icon": "📊",
        "title": "10. Plataforma MLOps y Telemetría",
        "icon": "📊",
        "file": "04_PLATAFORMA_MLOPS_Y_TELEMETRIA.md",
        "desc": "DuckDB, Parquet, Promotion Gates, catálogo interactivo y Match Replay.",
    },
    {
        "id": "doc-13-metrics",
        "category": "IV. MLOps, Telemetría y Servicios",
        "category_icon": "📊",
        "title": "11. Inventario Jerárquico Canónico de Métricas",
        "icon": "📐",
        "file": "13_INVENTARIO_CANONICO_METRICAS.md",
        "desc": "Taxonomía de 4 niveles, origen autoritativo, cero-invención y purgado de redundancias.",
    },
    {
        "id": "doc-07-apis",
        "category": "IV. MLOps, Telemetría y Servicios",
        "category_icon": "📊",
        "title": "12. Servicios Backend y Catálogo de APIs",
        "icon": "⚡",
        "file": "07_SERVICIOS_BACKEND_Y_CATALOGO_APIS.md",
        "desc": "REST FastAPI (:8001), WebSocket binario MessagePack, RAG API y MLOps API (:8778).",
    },
    {
        "id": "doc-06-rag",
        "category": "IV. MLOps, Telemetría y Servicios",
        "category_icon": "📊",
        "title": "13. Sistema RAG Copilot",
        "icon": "🤖",
        "file": "06_SISTEMA_RAG_COPILOT.md",
        "desc": "BM25 híbrido, SitRep en vivo, explicabilidad normativa y soporte LLM local.",
    },

    # ─── V. INFORMES DE EJECUCIÓN Y AUDITORÍAS FORENSES ───
    {
        "id": "doc-16-informes-cabecera",
        "category": "V. Informes de Ejecución y Auditorías",
        "category_icon": "📋",
        "title": "14. Informes de Ejecución: Cabecera y Catálogo",
        "icon": "📋",
        "file": "informes_ejecucion/00_CABECERA_INFORMES_EJECUCION.md",
        "desc": "Protocolo de auditoría forense, taxonomía TQS y repositorio centralizado de informes.",
    },
    {
        "id": "doc-16-informe-01",
        "category": "V. Informes de Ejecución y Auditorías",
        "category_icon": "📋",
        "title": "15. Informe 01: Currículum y Auditoría Táctica Forense",
        "icon": "📑",
        "file": "informes_ejecucion/INFORME_01_CURRICULUM_Y_AUDITORIA_TACTICA.md",
        "desc": "Auditoría de 31 ciclos, diagnóstico de parálisis ofensiva, bloqueo de canales 36/37 y plan de mitigación.",
    },
    {
        "id": "doc-16-informe-02",
        "category": "V. Informes de Ejecución y Auditorías",
        "category_icon": "📋",
        "title": "16. Informe 02: Currículum Multi-Fase y Comandante Prudente",
        "icon": "📈",
        "file": "informes_ejecucion/INFORME_02_CURRICULUM_Y_AUDITORIA_TACTICA.md",
        "desc": "Evaluación post-estandarización telemetría (34 evals), 1.ª victoria en campo abierto y confirmación de la Paradoja del Comandante Prudente.",
    },

    # ─── VI. HOJA DE RUTA EVOLUTIVA (ROADMAP) ───
    {
        "id": "doc-linea-1",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.1. Roadmap: Línea 1 (Observabilidad y Telemetría)",
        "icon": "🔴",
        "file": "roadmap/01_LINEA_1_OBSERVABILIDAD_Y_TELEMETRIA.md",
        "desc": "Conformidad de esquema, profiler de sondas zero-mock, validador E2E y depuración de redundancias.",
    },
    {
        "id": "doc-linea-2",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.2. Roadmap: Línea 2 (Captura de VPs y Paridad Humana)",
        "icon": "🔴",
        "file": "roadmap/02_LINEA_2_ACELERACION_CAPTURA_VPS.md",
        "desc": "Potencial radial a VP, sesgo prior MCTS, urgencia temporal y currículum acelerado.",
    },
    {
        "id": "doc-linea-3",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.3. Roadmap: Línea 3 (Fidelidad Normativa y Wargame)",
        "icon": "🟢",
        "file": "roadmap/03_LINEA_3_FIDELIDAD_NORMATIVA_Y_REGLAMENTO.md",
        "desc": "Retirada en desenfilada 6.4, Dig-in, Humo, Transporte, formaciones combinadas y mitigación 3.6.",
    },
    {
        "id": "doc-linea-4",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.4. Roadmap: Línea 4 (Explicabilidad XAI e IPB)",
        "icon": "🟢",
        "file": "roadmap/04_LINEA_4_EXPLICABILIDAD_XAI_E_IPB.md",
        "desc": "Atribución causal IGNH/GradCAM, perfilador forense, chokepoints IPB y perfilado doctrinal.",
    },
    {
        "id": "doc-linea-5",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.5. Roadmap: Línea 5 (Generalización Procedural)",
        "icon": "🔵",
        "file": "roadmap/05_LINEA_5_GENERALIZACION_PROCEDURAL.md",
        "desc": "Mutador procedural con clumping geográfico y validación Zero-Shot en mapas 32x32 y 64x64.",
    },
    {
        "id": "doc-historial-versiones",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17.6. Historial de Versiones e Hitos Consolidados",
        "icon": "📦",
        "file": "HISTORIAL_VERSIONES_COMPLETADAS.md",
        "desc": "Registro oficial de auditoría, changelog técnico por versiones v1.0.0 a v2.5.3 e hitos consolidados.",
    },
    {
        "id": "doc-09-roadmap",
        "category": "VI. Hoja de Ruta Evolutiva (Roadmap)",
        "category_icon": "🗺️",
        "title": "17. Hoja de Ruta Evolutiva (Roadmap Maestro)",
        "icon": "🗺️",
        "file": "05_ROADMAP_EVOLUTIVO.md",
        "desc": "Visión ejecutiva, matriz maestra global, orden de ejecución y changelog canónico de versiones.",
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
                "category": spec["category"],
                "category_icon": spec["category_icon"],
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
    pdf_path = DOCS_DIR / "Assault_Documentacion_Tecnica_Completa.pdf"
    if pdf_path.exists():
        shutil.copyfile(pdf_path, ROOT_DIR / "site" / "Assault_Documentacion_Tecnica_Completa.pdf")
    for spec in CANONICAL_DOCS_ORDER:
        doc_dir_name = spec["file"].replace(".md", "")
        target_dir = ROOT_DIR / "site" / doc_dir_name
        if target_dir.exists():
            # Handle possible nested directories
            nest_depth = len(Path(doc_dir_name).parts)
            prefix = "../" * nest_depth
            redirect_html = f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Redirigiendo al Hub Canónico...</title>
  <meta http-equiv="refresh" content="0; url={prefix}#{spec["id"]}">
  <script>window.location.replace("{prefix}#" + "{spec["id"]}");</script>
</head>
<body>
  Redirigiendo al portal canónico: <a href="{prefix}#{spec["id"]}">{spec["title"]}</a>
</body>
</html>'''
            (target_dir / "index.html").write_text(redirect_html, encoding="utf-8")
    print("[OK] Hub Canónico interactivo (docs/index.html) unificado al 100% como portal principal en site/index.html.")


if __name__ == "__main__":
    sync_index_html()
    build_mkdocs_site()
    if "--pdf" in sys.argv:
        try:
            from scripts.generate_docs_pdf import main as generate_pdf_main
        except ModuleNotFoundError:
            from generate_docs_pdf import main as generate_pdf_main
        generate_pdf_main()
