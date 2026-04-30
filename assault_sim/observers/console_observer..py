class ConsoleObserver:
    def __call__(self, event: dict) -> None:
        etype = event.get("type")
        payload = event.get("payload", {})
        print(f"[DEBUG] {etype}: {payload}")