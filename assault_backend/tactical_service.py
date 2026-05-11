from assault_rag.explanation.activation_tactical_explainer import (
    explain_activation_events,
)
from assault_rag.explanation.tactical_rules_explainer import (
    explain_tactical_execution_with_rules,
)


class TacticalService:
    """
    Backend-driven tactical explanation service.

    Responsibilities:
    - Explain WHAT happened (deterministic facts).
    - Explain WHY it happened (rulebook-based reasoning).
    """

    def __init__(self, typed_rules):
        """
        Initialize the tactical service with a preloaded rulebook.

        :param typed_rules: Parsed rulebook (list of typed rule dicts).
        """
        self.typed_rules = typed_rules

    def explain(self, activation_events):
        """
        Explain the tactical resolution of a single activation.

        :param activation_events: List of events produced by the UI
                                  during the activation.
        :return: Dict with 'facts' and 'rules'.
        """

        # -------------------------------------------------
        # Guard: no events at all
        # -------------------------------------------------
        if not activation_events:
            return {
                "facts": "The unit performed the action without any tactical resolution.",
                "rules": "No tactical rules were applied.",
            }

        # -------------------------------------------------
        # 1. Deterministic factual explanation (WHAT happened)
        # -------------------------------------------------
        facts = explain_activation_events(activation_events)

        # -------------------------------------------------
        # 2. Rule-based explanation (WHY it happened)
        #    - Standard dice rules
        #    - Or special rules via RAG + LLM
        # -------------------------------------------------
        rules = explain_tactical_execution_with_rules(
            activation_events=activation_events,
            typed_rules=self.typed_rules,
        )

        return {
            "facts": facts,
            "rules": rules,
        }