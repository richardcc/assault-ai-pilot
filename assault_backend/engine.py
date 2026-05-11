from cache_hrl import HRLCache
from cache_tactical import TacticalCache


class ExplainableEngine:
    """
    Engine that orchestrates strategic (HRL) and tactical explanations
    using two independent caches.
    """

    def __init__(self, hrl_service, tactical_service):
        self.hrl_service = hrl_service
        self.tactical_service = tactical_service

        self.hrl_cache = HRLCache()
        self.tactical_cache = TacticalCache()

    def explain_activation(self, activation):
        """
        Explain a single activation with coherent HRL + Tactical layers.
        """

        # -------------------------------------------------
        # STRATEGIC (HRL) — CACHED BY SEMANTIC STATE
        # -------------------------------------------------
        hrl_key = self.hrl_cache.make_key(
            unit_id=activation.unit_id,
            action=activation.action,
            strategic_state=activation.strategic_state,
        )

        strategic_intent = self.hrl_cache.get(hrl_key)
        if strategic_intent is None:
            strategic_intent = self.hrl_service.explain(
                strategic_state=activation.strategic_state,
                unit_id=activation.unit_id,
                action=activation.action,
            )
            self.hrl_cache.set(hrl_key, strategic_intent)

        # ✅ FORZAR coherencia del payload
        strategic_intent["unit_id"] = activation.unit_id

        # -------------------------------------------------
        # TACTICAL — CACHED BY EVENTS
        # -------------------------------------------------
        tactical_key = self.tactical_cache.make_key(
            unit_id=activation.unit_id,
            events=activation.events,
        )

        tactical_execution = self.tactical_cache.get(tactical_key)
        if tactical_execution is None:
            tactical_execution = self.tactical_service.explain(
                activation.events
            )
            self.tactical_cache.set(tactical_key, tactical_execution)

        return {
            "strategic_intent": strategic_intent,
            "tactical_execution": tactical_execution,
        }