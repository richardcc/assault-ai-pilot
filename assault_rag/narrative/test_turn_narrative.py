import json
from pathlib import Path
import subprocess

# HRL
from assault_rag.hrl.retriever.hrl_retriever import retrieve_hrl_principles
from assault_rag.hrl.prompt.hrl_prompt_builder import build_hrl_prompt

# Tactical
from assault_rag.explanation.tactical_explainer import explain_tactical_action
# Narrative
from assault_rag.narrative.turn_narrative_composer import compose_turn_narrative

REPLAY_PATH = Path(
    "assault_sim/session/replays/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

def load_replay():
    with open(REPLAY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def call_llm(prompt: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", "llama3:8b"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8"))
    return proc.stdout.decode("utf-8").strip()

def main():
    replay = load_replay()

    # ===== pick a turn to test =====
    turn_data = next(t for t in replay["turns"] if t["turn"] == 4)


    # ===== Align HRL decision with the action =====
    events = turn_data["events"]

    hrl_event = None
    action_index = None

    # Find the first ACTION_EFFECT
    for i, ev in enumerate(events):
        if ev["type"] == "ACTION_EFFECT":
            action_index = i
            break

    if action_index is None:
        raise RuntimeError("No ACTION_EFFECT found in this turn.")

    # Walk backwards to find the closest preceding HRL_DECISION
    for j in range(action_index - 1, -1, -1):
        if events[j]["type"] == "HRL_DECISION":
            hrl_event = events[j]["payload"]
            break

    if hrl_event is None:
        raise RuntimeError("No HRL_DECISION found before ACTION_EFFECT.")



    principles = retrieve_hrl_principles(hrl_event)
    hrl_prompt = build_hrl_prompt(hrl_event, principles)
    hrl_explanation = call_llm(hrl_prompt)

    # ===== Tactical actions =====
    tactical_explanations = []
    for ev in turn_data["events"]:
        if ev["type"] == "ACTION_EFFECT":
            tactical_explanations.append(
                explain_tactical_action(ev["payload"])
            )

    # ===== Compose narrative =====
    narrative = compose_turn_narrative(
        turn=turn_data["turn"],
        hrl_explanation=hrl_explanation,
        tactical_explanations=tactical_explanations,
    )

    print("\n================= TURN NARRATIVE =================\n")
    print(narrative)
    print("\n==================================================\n")

if __name__ == "__main__":
    main()