from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(".").resolve()
    runs_dir = root / "experiments_v2" / "runs"
    if not runs_dir.exists():
        print("No runs directory yet: experiments_v2/runs")
        return 0

    result_files = sorted(runs_dir.glob("*/result.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not result_files:
        print("No result.json files yet.")
        return 0

    print("Experiment V2 status:")
    for p in result_files[:20]:
        try:
            obj = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            print(f"- {p.parent.name}: PARSE_ERROR")
            continue
        print(
            f"- {p.parent.name}: {obj.get('status')} "
            f"(train={obj.get('train_exit_code')}, gate={obj.get('gate_exit_code')})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

