from assault_model.actions.action import Action


class EmbarkAction(Action):
    """
    Infantry embarks into a friendly vehicle.
    Triggered by movement.
    """

    def __init__(self, unit_id: str, vehicle_id: str, entry_hex: tuple[int, int]):
        self.unit_id = unit_id
        self.vehicle_id = vehicle_id
        self.entry_hex = entry_hex

    def __repr__(self):
        return f"EmbarkAction(unit={self.unit_id}, vehicle={self.vehicle_id})"
