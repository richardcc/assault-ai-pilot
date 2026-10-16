from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PHASE_RE = re.compile(r"\bphase=(?P<phase>[a-zA-Z0-9_]+)|==\s*Phase:\s*(?P<phase2>[a-zA-Z0-9_]+)\s*==")
PROFILE_RE = re.compile(r"\bprofile=(?P<profile>[a-zA-Z0-9_]+)|\bmatchup_profile=(?P<profile2>[a-zA-Z0-9_]+)")
METRIC_RE = re.compile(
    r"agent=(?P<agent>\S+)\s+done\s+avg_return=(?P<avg_return>-?\d+\.\d+)\s+"
    r"avg_steps=(?P<avg_steps>\d+\.\d+)\s+terminal_rate=(?P<terminal_rate>\d+\.\d+)\s+"
    r"timeout_rate=(?P<timeout_rate>\d+\.\d+)\s+win_rate=(?P<win_rate>\d+\.\d+)"
)
GATE_FAIL_RE = re.compile(r"\*\s+(?P<reason>.+)$")
BENCH_PAYLOAD_RE = re.compile(r"Bench payload used for gate:\s*(?P<path>.+)$")
BENCH_RUN_ID_RE = re.compile(r"\[Bench\]\s+completed\s+run_id=(?P<run_id>(?:efficientzero_v2|muzero)_[0-9a-f]+)")


def _read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except Exception:
            pass
    try:
        return raw.decode("utf-8-sig")
    except Exception:
        return raw.decode("utf-8", errors="ignore")


def _phase_from_path(log_path: Path) -> str:
    p = str(log_path).replace("\\", "/")
    m = re.search(r"(phase[0-9]+(?:_[a-z0-9]+)*)", p, flags=re.IGNORECASE)
    if not m:
        return "unknown_phase"
    return str(m.group(1)).lower()


def parse_metrics(log_path: Path) -> tuple[dict[str, dict[str, float]], dict[str, list[str]]]:
    out: dict[str, dict[str, float]] = {}
    gate_reasons_by_phase: dict[str, list[str]] = {}
    current_phase = _phase_from_path(log_path)
    current_profile = "all_profiles"
    for line in _read_text_auto(log_path).splitlines():
        phase_m = PHASE_RE.search(line)
        if phase_m:
            current_phase = str(phase_m.group("phase") or phase_m.group("phase2") or "unknown_phase").lower()
        profile_m = PROFILE_RE.search(line)
        if profile_m:
            current_profile = str(profile_m.group("profile") or profile_m.group("profile2") or "all_profiles").lower()
        gate_m = GATE_FAIL_RE.search(line)
        if gate_m and " < " in line:
            gate_reasons_by_phase.setdefault(current_phase, []).append(str(gate_m.group("reason")).strip())

        m = METRIC_RE.search(line)
        if not m:
            continue
        agent = str(m.group("agent"))
        key = f"{current_phase}|{current_profile}|{agent}"
        out[key] = {
            "phase": current_phase,
            "profile": current_profile,
            "agent": agent,
            "avg_return": float(m.group("avg_return")),
            "avg_steps": float(m.group("avg_steps")),
            "terminal_rate": float(m.group("terminal_rate")),
            "timeout_rate": float(m.group("timeout_rate")),
            "win_rate": float(m.group("win_rate")),
        }
    return out, gate_reasons_by_phase


def _read_bench_payload_from_eval_log(log_path: Path) -> dict:
    text = _read_text_auto(log_path)
    payload_path = ""
    run_id = ""
    for line in text.splitlines():
        m = BENCH_PAYLOAD_RE.search(line)
        if m:
            payload_path = str(m.group("path") or "").strip()
        m2 = BENCH_RUN_ID_RE.search(line)
        if m2:
            run_id = str(m2.group("run_id") or "").strip()
    if not payload_path:
        if run_id:
            xai_dir = (Path.cwd() / "runs_curriculum" / run_id / "xai").resolve()
            if xai_dir.exists():
                candidates = sorted(xai_dir.glob("bench_eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if candidates:
                    payload_path = str(candidates[0])
    if not payload_path:
        return {}
    p = Path(payload_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def _results_from_bench_payload(payload: dict, phase_hint: str) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    gate = dict(payload.get("phase_2_9_promotion_gate", {}) or {})
    gate_metrics = dict(gate.get("metrics", {}) or {})
    gate_xai_vp_capture_take_rate = gate_metrics.get("vp_capture_take_rate", None)
    if gate_xai_vp_capture_take_rate is None:
        gate_xai_vp_capture_take_rate = gate.get("xai_vp_capture_take_rate", None)
    gate_tracked_captured_avg = gate_metrics.get("tracked_captured_avg", None)
    if gate_tracked_captured_avg is None:
        gate_tracked_captured_avg = gate.get("muzero_tracked_captured_avg", None)
    for row in list(payload.get("results", []) or []):
        if not isinstance(row, dict):
            continue
        profile = str(row.get("matchup_profile", "all_profiles") or "all_profiles").lower()
        agent = str(row.get("agent_name", row.get("policy_name", "unknown_agent")) or "unknown_agent")
        key = f"{phase_hint}|{profile}|{agent}"
        kpis = dict(row.get("phase_2_9_eval_kpis", {}) or {})
        xai_vp_capture_take_rate = kpis.get("xai_vp_capture_take_rate", None)
        tracked_captured_avg = row.get("tracked_captured_avg", None)
        if xai_vp_capture_take_rate is None:
            opp = kpis.get("xai_vp_capture_opportunity_steps", None)
            taken = kpis.get("xai_vp_capture_taken_steps", None)
            try:
                if opp is not None and taken is not None and float(opp) > 0:
                    xai_vp_capture_take_rate = float(taken) / float(opp)
            except Exception:
                pass
        if xai_vp_capture_take_rate is None:
            xai_vp_capture_take_rate = gate_xai_vp_capture_take_rate
        if tracked_captured_avg is None:
            tracked_captured_avg = gate_tracked_captured_avg
        out[key] = {
            "phase": phase_hint,
            "profile": profile,
            "agent": agent,
            "win_rate": float(row.get("win_rate", 0.0) or 0.0),
            "avg_return": float(row.get("avg_return", 0.0) or 0.0),
            "timeout_rate": float(row.get("timeout_rate", 0.0) or 0.0),
            "avg_steps": float(row.get("avg_steps", 0.0) or 0.0),
            "xai_vp_capture_take_rate": (None if xai_vp_capture_take_rate is None else float(xai_vp_capture_take_rate)),
            "tracked_captured_avg": (None if tracked_captured_avg is None else float(tracked_captured_avg)),
        }
    return out


def fmt_delta(new: float, old: float) -> str:
    d = new - old
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare two curriculum eval logs.")
    ap.add_argument("--baseline", required=True, help="Path to baseline 02_eval.log")
    ap.add_argument("--candidate", required=True, help="Path to candidate 02_eval.log")
    ap.add_argument(
        "--common-only",
        action="store_true",
        help="Compare only profile+agent combinations present in both baseline and candidate payloads.",
    )
    args = ap.parse_args()

    base_path = Path(args.baseline).resolve()
    cand_path = Path(args.candidate).resolve()
    if not base_path.exists():
        raise FileNotFoundError(f"baseline log not found: {base_path}")
    if not cand_path.exists():
        raise FileNotFoundError(f"candidate log not found: {cand_path}")

    base, base_gate = parse_metrics(base_path)
    cand, cand_gate = parse_metrics(cand_path)
    phase_hint = _phase_from_path(cand_path)

    base_payload = _read_bench_payload_from_eval_log(base_path)
    cand_payload = _read_bench_payload_from_eval_log(cand_path)
    if base_payload and cand_payload:
        base = _results_from_bench_payload(base_payload, phase_hint)
        cand = _results_from_bench_payload(cand_payload, phase_hint)

    if bool(args.common_only):
        keys = sorted(set(base.keys()) & set(cand.keys()))
    else:
        keys = sorted(set(base.keys()) | set(cand.keys()))

    print(f"baseline={base_path}")
    print(f"candidate={cand_path}")
    print(f"common_only={bool(args.common_only)}")
    print("")
    print("phase\tprofile\tagent\tmetric\tbaseline\tcandidate\tdelta")
    for key in keys:
        b = base.get(key, {})
        c = cand.get(key, {})
        phase = str((c or b).get("phase", "unknown_phase"))
        profile = str((c or b).get("profile", "all_profiles"))
        agent = str((c or b).get("agent", "unknown_agent"))
        for metric in (
            "win_rate",
            "avg_return",
            "timeout_rate",
            "avg_steps",
            "xai_vp_capture_take_rate",
            "tracked_captured_avg",
        ):
            bv = b.get(metric)
            cv = c.get(metric)
            if bv is None or cv is None:
                print(f"{phase}\t{profile}\t{agent}\t{metric}\t{bv}\t{cv}\tNA")
                continue
            print(f"{phase}\t{profile}\t{agent}\t{metric}\t{bv:.3f}\t{cv:.3f}\t{fmt_delta(cv, bv)}")
    print("")
    print("gate_fail_reasons_by_phase (baseline):")
    print(json.dumps(base_gate, indent=2, ensure_ascii=False))
    print("")
    print("gate_fail_reasons_by_phase (candidate):")
    print(json.dumps(cand_gate, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
