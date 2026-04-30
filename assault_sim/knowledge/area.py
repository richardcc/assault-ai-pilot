class KnowledgeArea:
    """
    Groups multiple KnowledgeBricks into a semantic area.
    Contract:
    - evaluate_all(...) -> dict[str, dict]
    """
    def __init__(self, bricks: list):
        self.bricks = bricks

    def evaluate_all(self, state, unit_id, context=None) -> dict:
        raise NotImplementedError
