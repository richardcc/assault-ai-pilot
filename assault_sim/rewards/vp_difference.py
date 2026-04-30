class VPDifferenceReward:
    def __init__(self, normalize: bool = False):
        self.normalize = normalize

    def __call__(self, prev_vp: int, current_vp: int) -> float:
        r = current_vp - prev_vp
        if self.normalize:
            return max(-1.0, min(1.0, r / 10.0))
        return float(r)