from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from assault_backend.routers.explain import router as explain_router
from assault_backend.routers.game import router as game_router
from assault_backend.routers.rag import router as rag_router
from assault_backend.routers.scenarios import router as scenarios_router
from assault_backend.session_state import ezv2_service, game_session
from assault_rag.copilot.index_builder import (
    ensure_game_data_chunks,
    ensure_rule_chunks,
    get_rule_index_status,
    load_rule_chunks,
)
from assault_rag.copilot.retriever import invalidate_retriever_caches

RAG_STARTUP_STATUS = {
    "ok": False,
    "data_chunks": 0,
    "rule_chunks": 0,
    "rule_index_status": {},
    "error": None,
}


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """
    Build/load RAG indexes and warm up EfficientZeroV2 AI model on startup.
    """
    try:
        ensure_rule_chunks(force_rebuild=False)
        rule_index_status = get_rule_index_status()
        data_chunks = ensure_game_data_chunks()
        invalidate_retriever_caches()
        rule_chunks = load_rule_chunks()
        if not rule_chunks:
            raise RuntimeError("Rulebook index file exists but loaded zero chunks.")
        RAG_STARTUP_STATUS.update(
            {
                "ok": True,
                "data_chunks": len(data_chunks),
                "rule_chunks": len(rule_chunks),
                "rule_index_status": rule_index_status,
                "error": None,
            }
        )
        print(
            f"[RAG STARTUP] data_chunks={len(data_chunks)} rule_chunks={len(rule_chunks)} "
            f"rule_index={rule_index_status.get('active_path')}"
        )
    except Exception as e:
        RAG_STARTUP_STATUS.update(
            {
                "ok": False,
                "error": str(e),
                "rule_index_status": get_rule_index_status(),
            }
        )
        print(f"[RAG STARTUP] preload_failed={e}")

    try:
        if ezv2_service.active_checkpoint_path:
            print(f"[EZV2 STARTUP] Active checkpoint: {ezv2_service.active_checkpoint_path}")
        else:
            print("[EZV2 STARTUP] No checkpoint found yet in runs_curriculum. Heuristic fallback active.")
    except Exception as e:
        print(f"[EZV2 STARTUP] Model warmup warning: {e}")

    yield


app = FastAPI(
    title="Assault Backend & AI Platform",
    description="Motor autoritativo de reglas tácticas por turnos, inferencia MCTS con EfficientZero V2 y Copiloto RAG.",
    version="2.0.0",
    lifespan=app_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "service": "assault-backend",
        "version": "2.0.0",
        "ai_engine": "EfficientZeroV2",
        "rag_ready": RAG_STARTUP_STATUS["ok"],
    }


@app.get("/api/rag/health", tags=["rag-copilot"])
def rag_health():
    return RAG_STARTUP_STATUS


# Include Modular Sub-Routers
app.include_router(game_router)
app.include_router(scenarios_router)
app.include_router(explain_router)
app.include_router(rag_router)

# Mount Static Art Assets
from fastapi.staticfiles import StaticFiles
from assault_model.paths import ART_DIR

if ART_DIR.exists():
    app.mount("/art", StaticFiles(directory=str(ART_DIR)), name="art")
    dice_dir = ART_DIR / "dice"
    if dice_dir.exists():
        app.mount("/assets/dice", StaticFiles(directory=str(dice_dir)), name="dice")

