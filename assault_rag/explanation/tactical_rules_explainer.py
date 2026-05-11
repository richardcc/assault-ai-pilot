import subprocess
from typing import List, Dict

from assault_rag.explanation.tactical_prompt_builder import build_tactical_prompt
from assault_rag.retrieval.tactical_rule_selector import select_tactical_rules
from assault_rag.explanation.tactical_guards import has_combat_effect


def call_llm(prompt: str) -> str:
    """
    Call the local LLM (Llama via Ollama) with the given prompt.
    """
    proc = subprocess.run(
        ["ollama", "run", "llama3:8b"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8"))

    return proc.stdout.decode("utf-8").strip()


def explain_standard_dice_resolution(activation_events: List[Dict]) -> str:
    """
    Build a rule-based explanation of standard dice resolution
    using only the observed dice results from the replay.
    """

    for ev in activation_events:
        if ev["type"] == "ACTION_EFFECT":
            p = ev["payload"]
            res = p.get("resolution", {})

            attacker_dice = [
                f"{d.get('color')} die [{', '.join(d.get('faces', [])) or 'blank'}]"
                for d in p.get("attacker_attack_dice", [])
            ]

            defender_dice = [
                f"{d.get('color')} die [{', '.join(d.get('faces', [])) or 'blank'}]"
                for d in p.get("defender_defense_dice", [])
            ]

            explanation = [
                "According to the standard ranged combat resolution rules, attack and defense dice are compared and opposing symbols cancel each other.",
                "",
                f"The attacker rolled: {', '.join(attacker_dice)}.",
                f"The defender rolled: {', '.join(defender_dice)}.",
                "",
                f"After cancellation, {res.get('remaining_damage', 0)} damage and "
                f"{res.get('remaining_criticals', 0)} critical symbols remained uncancelled.",
                f"These remaining symbols were applied to the defender, reducing its hit points "
                f"from {p.get('defender_hp_before')} to {p.get('defender_hp_after')}.",
            ]

            return " ".join(explanation)

    # Fallback (should not normally happen)
    return (
        "According to the standard combat rules, attack and defense dice are "
        "compared and remaining symbols are applied to the defender."
    )


def explain_tactical_execution_with_rules(
    activation_events: List[Dict],
    typed_rules: List[Dict],
) -> str:
    """
    Explain tactical execution of an activation using
    rulebook-based RAG and an LLM.
    """

    # ✅ Guard 1: no combat, no rule-based explanation
    if not has_combat_effect(activation_events):
        return "No combat resolution occurred during this activation."

    # ✅ Guard 2: select only rules strictly required by observed facts
    tactical_rules = select_tactical_rules(
        typed_rules=typed_rules,
        activation_events=activation_events,
    )

    # ✅ Guard 3: standard resolution → explain dice explicitly
    if not tactical_rules:
        return explain_standard_dice_resolution(activation_events)

    # ✅ Otherwise, explain via RAG + LLM (special rules case)
    prompt = build_tactical_prompt(
        activation_events=activation_events,
        tactical_rules=tactical_rules,
    )

    return call_llm(prompt)