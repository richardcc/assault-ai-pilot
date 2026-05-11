from functools import lru_cache
import json
import logging

from assault_rag.hrl.retriever.hrl_retriever import retrieve_hrl_principles
from assault_rag.hrl.prompt.hrl_prompt_builder import build_hrl_prompt
from assault_rag.llm.ollama_client import call_llm

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Internal uncached implementation
# -------------------------------------------------

def _explain_hrl_uncached(context: dict) -> str:
    """
    Real HRL explanation logic (RAG / LLM).
    """

    print(">>> ENTER _explain_hrl_uncached (LLM) <<<")
    print("    CONTEXT:", context)

    hrl_decision = {
        "unit_id": context.get("unit_id"),
        "action": context.get("action"),
        "friendly_strength": context.get("friendly_strength"),
        "enemy_pressure": context.get("enemy_pressure"),
        "objective_distance": context.get("objective_distance"),
    }

    principles = retrieve_hrl_principles(hrl_decision)
    prompt = build_hrl_prompt(hrl_decision, principles)

    return call_llm(prompt)


# -------------------------------------------------
# Cached LLM path
# -------------------------------------------------

@lru_cache(maxsize=256)
def _cached_explanation(key: str) -> str:
    context = json.loads(key)
    return _explain_hrl_uncached(context)


# -------------------------------------------------
# HRL public entrypoint
# -------------------------------------------------

def explain_hrl_decision(context: dict) -> dict:
    """
    HRL RAG entrypoint used by the backend.
    Strategy must NEVER contradict the executed action.
    """

    print("\n=== ENTER explain_hrl_decision ===")
    for k, v in context.items():
        print(f"  {k}: {v}")
    print("=== END CONTEXT ===")

    action = context.get("action")
    enemy_pressure = context.get("enemy_pressure")
    objective_distance = context.get("objective_distance")
    unit_id = context.get("unit_id")

    # -------------------------------------------------
    # ACTION OVERRIDE: OFFENSIVE ATTACKS (CRITICAL)
    # -------------------------------------------------
    if action in ("RangedDirectAttack", "MeleeAttack"):
        print(">>> HRL ATTACK OVERRIDE <<<")

        option = "ENGAGE"
        category = "OFFENSIVE"
        explanation_text = (
            "Despite incomplete situational information, the unit executed a direct attack. "
            "This reflects an intentional offensive decision to exploit a firing opportunity "
            "and neutralize the enemy, prioritizing immediate combat advantage over positional caution."
        )

        return {
            "unit_id": unit_id,
            "option": option,
            "category": category,
            "explanation": explanation_text,
        }


    # -------------------------------------------------
    # FAST-PATH (SOLO WAIT)
    # -------------------------------------------------
    if (
        enemy_pressure == "HIGH"
        and objective_distance == "UNKNOWN"
        and action == "WaitAction"
    ):
        print(">>> HRL FAST-PATH <<<")
        print("    action =", action)

        option = "HOLD"
        category = "DEFENSIVE"
        explanation_text = (
            "Under high enemy pressure and without reliable information "
            "about the objective position, maintaining the current posture "
            "is a cautious and conservative choice."
        )

        return {
            "unit_id": unit_id,
            "option": option,
            "category": category,
            "explanation": explanation_text,
        }

    # -------------------------------------------------
    # RAG (LLM) PATH
    # -------------------------------------------------
    print(">>> HRL RAG PATH (LLM or cache) <<<")

    cache_key = json.dumps(
        {
            "friendly_strength": context.get("friendly_strength"),
            "enemy_pressure": enemy_pressure,
            "objective_distance": objective_distance,
            "action": action,
        },
        sort_keys=True,
    )

    explanation_text = _cached_explanation(cache_key)

    # -------------------------------------------------
    # ACTION-ALIGNED LABEL
    # -------------------------------------------------
    if action == "MoveAction":
        option = "MANEUVER"
        category = "DEFENSIVE" if enemy_pressure == "HIGH" else "OFFENSIVE"
    elif action == "WaitAction":
        option = "HOLD"
        category = "DEFENSIVE"
    else:
        option = "HOLD" if enemy_pressure == "HIGH" else "MANEUVER"
        category = "DEFENSIVE" if option == "HOLD" else "OFFENSIVE"

    print(f">>> RETURN RAG: unit_id={unit_id}, option={option}")

    return {
        "unit_id": unit_id,
        "option": option,
        "category": category,
        "explanation": explanation_text,
    }
