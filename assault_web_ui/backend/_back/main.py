from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path

# ================= LOAD ENGINE PARTS =================
from engine.engine import ExplainableEngine

# ================= PATHS =================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPLAYS_DIR = DATA_DIR / "replays"

HRL_PATH = DATA_DIR / "hrl_principles.json"
RULEBOOK_PATH = DATA_DIR / "rulebook_typed.json"

# ================= FASTAPI APP =================
app = FastAPI(
    title="Assault Explainable Engine",
    version="1.0",
)

# Allow frontend (Pixi UI) to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # puedes restringir luego
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ENGINE: ExplainableEngine | None = None


# ================= HELPER =================
def load_json(path: Path):
    if not path.exists():
        raise RuntimeError(f"Missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ================= STARTUP (ENGINE WARM) =================
@app.on_event("startup")
def startup():
    global ENGINE

    print("🔄 Loading HRL corpus…")
    hrl_corpus = load_json(HRL_PATH)

    print("🔄 Loading rulebook…")
    rulebook = load_json(RULEBOOK_PATH)

    print("🔄 Loading replays…")
    replays = {}

    for replay_file in REPLAYS_DIR.glob("*.json"):
        replay_id = replay_file.stem
        replays[replay_id] = load_json(replay_file)
        print(f"   ✅ Loaded replay: {replay_id}")

    ENGINE = ExplainableEngine(
        hrl_corpus=hrl_corpus,
        rulebook=rulebook,
        replays=replays,
    )

    print("🔥 Explainable Engine is warm and ready")


# ================= MAIN ENDPOINT =================
@app.get("/api/replay/{replay_id}/turn/{turn}/step/{step}")
def explain_activation(
    replay_id: str,
    turn: int,
    step: int,
):
    """
    Explains ONE activation (STEP) using RAG.
    - turn and step are 1-based (UI-friendly)
    """

    if ENGINE is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        return ENGINE.explain_step(
            replay_id=replay_id,
            turn=turn,
            step=step,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Replay not found")
    except IndexError:
        raise HTTPException(status_code=400, detail="Invalid turn or step")


# ================= HEALTH CHECK =================
@app.get("/api/engine/status")
def engine_status():
    if ENGINE is None:
        return {"status": "loading"}

    return {
        "status": "ready",
        "replays_loaded": len(ENGINE.replays),
        "cached_explanations": len(ENGINE.cache),
    }