class ExplainableEngine:
    def __init__(self, hrl_corpus, rulebook, replays):
        self.hrl_corpus = hrl_corpus          # RAM
        self.rulebook = rulebook              # RAM
        self.replays = replays                # RAM
        self.cache = {}                       # (replay, turn, step) -> explanation

    def explain_step(self, replay_id, turn, step):
        key = (replay_id, turn, step)
        if key in self.cache:
            return self.cache[key]

        replay = self.replays[replay_id]
        activation = extract_activation(replay, turn, step)

        strategic = explain_hrl_rag(
            activation.context,
            self.hrl_corpus
        )

        tactical_facts = explain_activation_facts(
            activation.events
        )

        tactical_rules = explain_tactical_rules(
            activation.events,
            self.rulebook
        )

        result = {
            "activation": {
                "unit_id": activation.unit_id,
                "action": activation.action,
                "strategic_intent": strategic,
                "tactical_execution": {
                    "facts": tactical_facts,
                    "rules": tactical_rules
                }
            }
        }

        self.cache[key] = result
        return result
