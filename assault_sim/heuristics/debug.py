class HeuristicTracer:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def trace(self, tag: str, **data):
        if not self.enabled:
            return
        payload = " ".join(f"{k}={v}" for k, v in data.items())
        print(f"[H-TRACE][{tag}] {payload}")