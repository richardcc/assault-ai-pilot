import json
import subprocess
from pathlib import Path

# Activation extraction & HRL alignment
from assault_rag.narrative.activation_extractor import extract_rl_activations
from assault_rag.hrl.hrl_alignment import find_relevant_hrl_decision

# HRL (strategy)
from assault_rag.hrl.retriever.hrl_retriever import retrieve_hrl_principles
from assault_rag.hrl.prompt.hrl_prompt_builder import build_hrl_prompt

# Tactical (facts)
from assault_rag.explanation.activation_tactical_explainer import explain_activation_events

# Tactical (rules + LLM)
from assault_rag.explanation.tactical_rules_explainer import (
    explain_tactical_execution_with_rules,
)

# Rulebook
RULEBOOK_TYPED_PATH = Path(
    "assault_rag/data/rulebook/typed/rulebook_typed.json"
)

# Replay
REPLAY_PATH = Path(
    "assault_sim/session/replays/"
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
)

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
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
    replay = load_json(REPLAY_PATH)
    rulebook = load_json(RULEBOOK_TYPED_PATH)

    # ===== pick a turn to test =====
    turn_data = next(t for t in replay["turns"] if t["turn"] == 4)

    print(f"\n=== TURN {turn_data['turn']} ===\n")

    # ===== extract RL activations =====
    activations = extract_rl_activations(turn_data["events"])

    for idx, activation in enumerate(activations, start=1):
        print(f"\n--- ACTIVATION {idx}: {activation['unit']} ---")

        # ===== HRL alignment (closest prior HRL_DECISION) =====
        hrl_decision = find_relevant_hrl_decision(
            turn_events=turn_data["events"],
            action_index=activation["start_index"],
        )

        if hrl_decision:
            principles = retrieve_hrl_principles(hrl_decision)
            hrl_prompt = build_hrl_prompt(hrl_decision, principles)
            hrl_explanation = call_llm(hrl_prompt)
        else:
            hrl_explanation = "No strategic decision found for this activation."

        # ===== Tactical facts (deterministic) =====
        tactical_facts = explain_activation_events(activation["events"])

        # ===== Tactical rules-based explanation (RAG + LLM) =====
        tactical_rules = explain_tactical_execution_with_rules(
            activation_events=activation["events"],
            typed_rules=rulebook,
        )

        # ===== Output (console / UI preview) =====
        print("\nSTRATEGIC INTENT:\n")
        print(hrl_explanation)

        print("\nTACTICAL EXECUTION (FACTS):\n")
        print(tactical_facts)

        print("\nTACTICAL EXECUTION (RULES):\n")
        print(tactical_rules)

    print("\n=== END OF TURN ===\n")

if __name__ == "__main__":
    main()