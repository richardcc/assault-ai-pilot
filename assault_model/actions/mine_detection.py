from assault_model.actions.action import Action
from assault_model.actions.action_type import ActionType


class MineDetectionAction(Action):
    """
    Declares minefield detection / reconnaissance action (Rule 9.6.6.2 & Combat Engineers card).

    Design:
    - Initiated by an engineer or recon unit with MINE_DETECTION.
    - Can target current hex or an adjacent hex (distance 1) containing a minefield or dummy marker.
    - Grants +2 bonus to the D6 detection roll.
    - On success: identifies/unhides the minefield and clears/marks safe lanes.
    """

    def __init__(
        self,
        unit_id: str,
        target_hex: tuple[int, int],
    ):
        super().__init__(unit_id, ActionType.MINE_DETECTION)
        self.target_hex = (int(target_hex[0]), int(target_hex[1]))
        q, r = self.target_hex
        self.action_id = f"MINE_DETECTION:{unit_id}:{q}:{r}"

    def __repr__(self) -> str:
        return f"MineDetectionAction(unit_id={self.unit_id}, target_hex={self.target_hex})"
