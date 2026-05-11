from assault_rag.hrl.explain import explain_hrl_decision


class HRLService:
    def explain(self, strategic_state, unit_id, action):
        """
        Explain the strategic decision using real HRL RAG logic
        provided by assault_rag.
        """

        # Build context for HRL RAG
        context = {
            "friendly_strength": strategic_state.friendly_strength,
            "enemy_pressure": strategic_state.enemy_pressure,
            "objective_distance": strategic_state.objective_distance,
            "unit_id": unit_id,
            "action": action,
        }

        # Delegate explanation to assault_rag
        hrl_result = explain_hrl_decision(context)

        return {
            "option": hrl_result["option"],
            "category": hrl_result["category"],
            "explanation": hrl_result["explanation"],
        }