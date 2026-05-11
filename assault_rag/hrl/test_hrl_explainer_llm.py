import json
import subprocess
from pathlib import Path

from retriever.hrl_retriever import retrieve_hrl_principles
from prompt.hrl_prompt_builder import build_hrl_prompt

REPLAY_PATH = Path(
    "assault_sim/session/replays/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

def load_replay():
    with open(REPLAY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_hrl_decisions(replay):
    decisions = []
    for turn in replay.get("turns", []):
        for ev in turn.get("events", []):
            if ev.get("type") == "HRL_DECISION":
                decisions.append(ev["payload"])
    return decisions

def call_llm(prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", "llama3:8b"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8"))
    return proc.stdout.decode("utf-8")

def main():
    replay = load_replay()
    decisions = extract_hrl_decisions(replay)

    # Pick one decision to test (e.g., ATTACK at turn 3)
    decision = next(d for d in decisions if d["turn"] == 3 and d["option"] == "ATTACK")

    principles = retrieve_hrl_principles(decision)
    prompt = build_hrl_prompt(decision, principles)

    print("====== PROMPT SENT TO LLM ======\n")
    print(prompt)
    print("\n====== LLM EXPLANATION ======\n")

    explanation = call_llm(prompt)
    print(explanation)

if __name__ == "__main__":
    main()