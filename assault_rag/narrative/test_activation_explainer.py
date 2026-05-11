import json
import subprocess
from pathlib import Path

from assault_rag.narrative.activation_extractor import extract_rl_activations
from assault_rag.hrl.hrl_alignment import find_relevant_hrl_decision
from assault_rag.hrl.retriever.hrl_retriever import retrieve_hrl_principles
from assault_rag.hrl.prompt.hrl_prompt_builder import build_hrl_prompt
from assault_rag.explanation.activation_tactical_explainer import explain_activation_events

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

    print(f"\n=== TURN {turn_data['turn']} ===\n")

    # ===== extract RL activations =====
    activations = extract_rl_activations(turn_data["events"])

    for idx, activation in enumerate(activations, start=1):
        print(f"\n--- ACTIVATION {idx}: {activation['unit']} ---")

        # ===== HRL alignment (CORRECT) =====
        hrl_decision = find_relevant_hrl_decision(
            turn_data["events"],
            activation["start_index"]
        )

        if hrl_decision:
            principles = retrieve_hrl_principles(hrl_decision)
            hrl_prompt = build_hrl_prompt(hrl_decision, principles)
            hrl_explanation = call_llm(hrl_prompt)
        else:
            hrl_explanation = "No strategic decision found for this activation."

        # ===== Tactical explanation (FULL ACTIVATION) =====
        tactical_explanation = explain_activation_events(activation["events"])

        print("\nSTRATEGIC INTENT:\n")
        print(hrl_explanation)

        print("\nTACTICAL EXECUTION:\n")
        print(tactical_explanation)

    print("\n=== END OF TURN ===\n")

if __name__ == "__main__":
    main()