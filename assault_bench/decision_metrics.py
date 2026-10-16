from __future__ import annotations

import math
from typing import Dict, List, Optional

from assault_bench.telemetry_models import normalize_side_key
from assault_bench.transform_ops import index_rows_by_int_key, to_dict_rows


def build_eval_decision_summary(
    trace_rows: List[Dict[str, object]],
) -> tuple[Dict[str, object], List[Dict[str, object]]]:
    rows = to_dict_rows(trace_rows)
    if not rows:
        return {
            "total_decisions": 0,
            "by_action_kind": {},
            "by_action_kind_and_side": {},
        }, []
    by_kind: Dict[str, Dict[str, float]] = {}
    by_kind_side: Dict[str, Dict[str, float]] = {}
    by_action_id: Dict[str, Dict[str, float]] = {}
    ownership_by_side: Dict[str, Dict[str, float]] = {}
    mismatch_by_side: Dict[str, Dict[str, float]] = {}
    attack_effectiveness_groups: Dict[str, Dict[str, float]] = {}
    attack_effectiveness_bins: Dict[str, Dict[str, float]] = {}

    def _distance_bucket(raw: object) -> str:
        try:
            v = float(raw)
        except Exception:
            return "unknown"
        if v < 0.0:
            return "unknown"
        if v < 1.5:
            return "0-1"
        if v < 3.5:
            return "2-3"
        if v < 6.5:
            return "4-6"
        return "7+"

    def _cover_bucket(raw: object) -> str:
        try:
            v = float(raw)
        except Exception:
            return "unknown"
        if v < 0.0:
            return "unknown"
        if v < 0.25:
            return "low"
        if v < 0.60:
            return "medium"
        return "high"

    def _bucketize_prob(raw: object) -> str:
        try:
            p = float(raw)
        except Exception:
            p = 0.0
        p = min(1.0, max(0.0, p))
        lo = int(p * 5.0) / 5.0
        hi = min(1.0, lo + 0.2)
        return f"[{lo:.1f},{hi:.1f})"

    def _is_attack_like(kind: str) -> bool:
        k = str(kind or "").strip().upper()
        return k not in {"", "MOVE", "WAIT", "TIMEOUT", "OPPORTUNITY_SKIP"}

    def _acc_attack_group(
        group_key: str, dmg: float, kills: float, p_good: float, y_good: float
    ) -> None:
        g = attack_effectiveness_groups.setdefault(
            str(group_key),
            {
                "count": 0.0,
                "damage_sum": 0.0,
                "damage_sq_sum": 0.0,
                "exchange_win_sum": 0.0,
                "attack_good_label_sum": 0.0,
                "attack_good_prob_sum": 0.0,
                "brier_sum": 0.0,
            },
        )
        g["count"] += 1.0
        g["damage_sum"] += float(dmg)
        g["damage_sq_sum"] += float(dmg) * float(dmg)
        g["exchange_win_sum"] += float(
            1.0 if (float(dmg) > 0.0 or float(kills) > 0.0) else 0.0
        )
        g["attack_good_label_sum"] += float(y_good)
        g["attack_good_prob_sum"] += float(p_good)
        g["brier_sum"] += float((float(p_good) - float(y_good)) ** 2)

    def _acc_attack_bin(bin_key: str, p_good: float, y_good: float) -> None:
        b = attack_effectiveness_bins.setdefault(
            str(bin_key),
            {"count": 0.0, "prob_sum": 0.0, "label_sum": 0.0, "brier_sum": 0.0},
        )
        b["count"] += 1.0
        b["prob_sum"] += float(p_good)
        b["label_sum"] += float(y_good)
        b["brier_sum"] += float((float(p_good) - float(y_good)) ** 2)

    def _to_binary_int_or_none(value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            try:
                return 1 if int(value) == 1 else 0
            except Exception:
                return None
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return 1
        if text in {"0", "false", "no", "n"}:
            return 0
        return None

    def _accumulate_dims(dst: Dict[str, float], row: Dict[str, object]) -> None:
        target_q = row.get("target_q", None)
        target_r = row.get("target_r", None)
        attack_distance = row.get("attack_distance_mean", None)
        target_cover = row.get("attack_target_cover_mean", None)
        target_los = row.get("attack_target_los_block_mean", None)
        if isinstance(target_q, (int, float)):
            dst["target_q_sum"] = float(dst.get("target_q_sum", 0.0)) + float(target_q)
            dst["target_q_n"] = float(dst.get("target_q_n", 0.0)) + 1.0
        if isinstance(target_r, (int, float)):
            dst["target_r_sum"] = float(dst.get("target_r_sum", 0.0)) + float(target_r)
            dst["target_r_n"] = float(dst.get("target_r_n", 0.0)) + 1.0
        if isinstance(attack_distance, (int, float)) and float(attack_distance) >= 0.0:
            dst["distance_sum"] = float(dst.get("distance_sum", 0.0)) + float(
                attack_distance
            )
            dst["distance_n"] = float(dst.get("distance_n", 0.0)) + 1.0
        if isinstance(target_cover, (int, float)) and float(target_cover) >= 0.0:
            dst["cover_sum"] = float(dst.get("cover_sum", 0.0)) + float(target_cover)
            dst["cover_n"] = float(dst.get("cover_n", 0.0)) + 1.0
        if isinstance(target_los, (int, float)) and float(target_los) >= 0.0:
            dst["los_sum"] = float(dst.get("los_sum", 0.0)) + float(target_los)
            dst["los_n"] = float(dst.get("los_n", 0.0)) + 1.0
        latent_dims = str(row.get("latent_top_dims", "") or "").strip()
        if latent_dims:
            votes = dst.get("_latent_dims_votes", {})
            if not isinstance(votes, dict):
                votes = {}
            votes[latent_dims] = float(votes.get(latent_dims, 0.0)) + 1.0
            dst["_latent_dims_votes"] = votes

    def _metric_from_row(row: Dict[str, object], *keys: str, default: float = 0.0) -> float:
        for key in keys:
            if key not in row:
                continue
            raw = row.get(key, None)
            if raw is None:
                continue
            try:
                return float(raw)
            except Exception:
                continue
        return float(default)

    for r in rows:
        kind = str(r.get("action_kind", "") or "").strip().upper() or "UNKNOWN"
        side = normalize_side_key(r.get("unit_side", "")) or "UNKNOWN"
        action_id = str(r.get("action_id", "") or "").strip() or "UNKNOWN_ACTION"
        requested_action_id = str(r.get("requested_action_id", "") or "").strip() or action_id
        action_mismatch = bool(r.get("action_mismatch", False))
        execution_mismatch = action_mismatch or (requested_action_id != action_id)
        policy_override = _to_binary_int_or_none(r.get("policy_overridden_by_mcts", None))
        has_override_signal = policy_override is not None
        kept = bool(policy_override == 0) if has_override_signal else False
        own = ownership_by_side.setdefault(
            side,
            {
                "rows": 0.0,
                "policy_kept": 0.0,
                "overwritten": 0.0,
                "override_signal_rows": 0.0,
                "unknown_override_rows": 0.0,
            },
        )
        own["rows"] += 1.0
        if not has_override_signal:
            own["unknown_override_rows"] += 1.0
        elif kept:
            own["policy_kept"] += 1.0
        else:
            own["overwritten"] += 1.0
        if has_override_signal:
            own["override_signal_rows"] += 1.0
        mm = mismatch_by_side.setdefault(
            side, {"rows": 0.0, "execution_mismatch": 0.0, "execution_match": 0.0}
        )
        mm["rows"] += 1.0
        if execution_mismatch:
            mm["execution_mismatch"] += 1.0
        else:
            mm["execution_match"] += 1.0
        dmg = _metric_from_row(r, "damage_dealt", "enemy_damage", "damage", "damage_sum", default=0.0)
        kills = _metric_from_row(r, "kills_dealt", "enemy_kills", "kills", "kills_sum", default=0.0)
        k = by_kind.setdefault(kind, {"count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0})
        k["count"] += 1.0
        k["damage_sum"] += dmg
        k["kills_sum"] += kills
        _accumulate_dims(k, r)
        ks_key = f"{kind}|{side}"
        ks = by_kind_side.setdefault(
            ks_key,
            {"action_kind": kind, "unit_side": side, "count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0},
        )
        ks["count"] += 1.0
        ks["damage_sum"] += dmg
        ks["kills_sum"] += kills
        _accumulate_dims(ks, r)
        aid = by_action_id.setdefault(
            action_id,
            {"action_id": action_id, "action_kind": kind, "unit_side": side, "count": 0.0, "damage_sum": 0.0, "kills_sum": 0.0},
        )
        aid["count"] += 1.0
        aid["damage_sum"] += dmg
        aid["kills_sum"] += kills
        _accumulate_dims(aid, r)
        if _is_attack_like(kind):
            p_good = _metric_from_row(r, "chosen_action_prob", "policy_prior", default=0.0)
            p_good = min(1.0, max(0.0, float(p_good)))
            y_good = 1.0 if (float(dmg) > 0.0 or float(kills) > 0.0) else 0.0
            dist_bucket = _distance_bucket(r.get("attack_distance_mean", None))
            cover_bucket = _cover_bucket(r.get("attack_target_cover_mean", None))
            unit_key = str(r.get("unit_label", "") or r.get("unit_id", "") or "UNKNOWN")
            _acc_attack_group("global", dmg, kills, p_good, y_good)
            _acc_attack_group(f"kind::{kind}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"unit::{unit_key}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"distance::{dist_bucket}", dmg, kills, p_good, y_good)
            _acc_attack_group(f"cover::{cover_bucket}", dmg, kills, p_good, y_good)
            _acc_attack_bin(_bucketize_prob(p_good), p_good, y_good)

    def _enrich(v: Dict[str, float]) -> Dict[str, float]:
        c = float(v.get("count", 0.0))
        tqn = float(v.get("target_q_n", 0.0))
        trn = float(v.get("target_r_n", 0.0))
        dn = float(v.get("distance_n", 0.0))
        cn = float(v.get("cover_n", 0.0))
        ln = float(v.get("los_n", 0.0))
        latent_votes = v.get("_latent_dims_votes", {})
        if not isinstance(latent_votes, dict):
            latent_votes = {}
        latent_mode = ""
        latent_mode_count = 0.0
        if latent_votes:
            latent_mode, latent_mode_count = max(
                ((str(k), float(val)) for k, val in latent_votes.items()),
                key=lambda kv: kv[1],
            )
        base = {k: val for k, val in v.items() if not str(k).startswith("_")}
        return {
            **base,
            "damage_per_action": (float(v.get("damage_sum", 0.0)) / float(c)) if c > 0 else 0.0,
            "kills_per_action": (float(v.get("kills_sum", 0.0)) / float(c)) if c > 0 else 0.0,
            "target_q_avg": (float(v.get("target_q_sum", 0.0)) / float(tqn)) if tqn > 0 else -1.0,
            "target_r_avg": (float(v.get("target_r_sum", 0.0)) / float(trn)) if trn > 0 else -1.0,
            "attack_distance_avg": (float(v.get("distance_sum", 0.0)) / float(dn)) if dn > 0 else -1.0,
            "attack_target_cover_avg": (float(v.get("cover_sum", 0.0)) / float(cn)) if cn > 0 else -1.0,
            "attack_target_los_block_avg": (float(v.get("los_sum", 0.0)) / float(ln)) if ln > 0 else -1.0,
            "latent_top_dims": latent_mode,
            "latent_top_dims_mode_count": float(latent_mode_count),
        }

    by_kind_out = {
        k: _enrich(v)
        for k, v in sorted(by_kind.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))
    }
    by_kind_side_out = {
        k: _enrich(v)
        for k, v in sorted(by_kind_side.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))
    }
    top_actions = [
        _enrich(v)
        for _, v in sorted(by_action_id.items(), key=lambda kv: (-float(kv[1].get("count", 0.0)), kv[0]))[:40]
    ]
    ownership_out: Dict[str, Dict[str, object]] = {}
    total_rows = 0.0
    total_kept = 0.0
    total_overwritten = 0.0
    total_override_signal_rows = 0.0
    total_unknown_override_rows = 0.0
    for side, row in sorted(ownership_by_side.items(), key=lambda kv: kv[0]):
        rows_n = float(row.get("rows", 0.0))
        kept_n = float(row.get("policy_kept", 0.0))
        over_n = float(row.get("overwritten", 0.0))
        override_signal_n = float(row.get("override_signal_rows", 0.0))
        unknown_override_n = float(row.get("unknown_override_rows", 0.0))
        total_rows += rows_n
        total_kept += kept_n
        total_overwritten += over_n
        total_override_signal_rows += override_signal_n
        total_unknown_override_rows += unknown_override_n
        ownership_out[str(side)] = {
            "side": str(side),
            "rows": int(rows_n),
            "policy_kept": int(kept_n),
            "overwritten": int(over_n),
            "override_signal_rows": int(override_signal_n),
            "unknown_override_rows": int(unknown_override_n),
            "policy_kept_rate": (kept_n / rows_n) if rows_n > 0 else 0.0,
            "overwritten_rate": (over_n / rows_n) if rows_n > 0 else 0.0,
        }
    mismatch_out: Dict[str, Dict[str, object]] = {}
    total_mismatch_rows = 0.0
    total_execution_mismatch = 0.0
    total_execution_match = 0.0
    for side, row in sorted(mismatch_by_side.items(), key=lambda kv: kv[0]):
        rows_n = float(row.get("rows", 0.0))
        mismatch_n = float(row.get("execution_mismatch", 0.0))
        match_n = float(row.get("execution_match", 0.0))
        total_mismatch_rows += rows_n
        total_execution_mismatch += mismatch_n
        total_execution_match += match_n
        mismatch_out[str(side)] = {
            "side": str(side),
            "rows": int(rows_n),
            "execution_mismatch": int(mismatch_n),
            "execution_match": int(match_n),
            "execution_mismatch_rate": (mismatch_n / rows_n) if rows_n > 0 else 0.0,
        }

    def _finalize_attack_group(src: Dict[str, float]) -> Dict[str, float]:
        n = float(src.get("count", 0.0))
        if n <= 0.0:
            return {
                "count": 0,
                "empirical_expected_damage": 0.0,
                "damage_variance": 0.0,
                "exchange_win_rate": 0.0,
                "attack_good_rate": 0.0,
                "attack_good_prob_mean": 0.0,
                "attack_good_brier": 0.0,
            }
        mean_d = float(src.get("damage_sum", 0.0)) / n
        ex2 = float(src.get("damage_sq_sum", 0.0)) / n
        var_d = max(0.0, ex2 - (mean_d * mean_d))
        return {
            "count": int(n),
            "empirical_expected_damage": float(mean_d),
            "damage_variance": float(var_d),
            "exchange_win_rate": float(src.get("exchange_win_sum", 0.0)) / n,
            "attack_good_rate": float(src.get("attack_good_label_sum", 0.0)) / n,
            "attack_good_prob_mean": float(src.get("attack_good_prob_sum", 0.0)) / n,
            "attack_good_brier": float(src.get("brier_sum", 0.0)) / n,
        }

    attack_effectiveness = {
        "global": _finalize_attack_group(attack_effectiveness_groups.get("global", {})),
        "by_action_kind": {},
        "by_unit": {},
        "by_distance_bucket": {},
        "by_cover_bucket": {},
        "calibration_bins": {},
    }
    for key, row in attack_effectiveness_groups.items():
        if str(key).startswith("kind::"):
            attack_effectiveness["by_action_kind"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("unit::"):
            attack_effectiveness["by_unit"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("distance::"):
            attack_effectiveness["by_distance_bucket"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
        elif str(key).startswith("cover::"):
            attack_effectiveness["by_cover_bucket"][str(key).split("::", 1)[1]] = _finalize_attack_group(row)
    for bin_key, row in sorted(attack_effectiveness_bins.items(), key=lambda kv: kv[0]):
        n = float(row.get("count", 0.0))
        attack_effectiveness["calibration_bins"][str(bin_key)] = {
            "count": int(n),
            "predicted_prob_mean": (float(row.get("prob_sum", 0.0)) / n) if n > 0.0 else 0.0,
            "empirical_attack_good_rate": (float(row.get("label_sum", 0.0)) / n) if n > 0.0 else 0.0,
            "brier": (float(row.get("brier_sum", 0.0)) / n) if n > 0.0 else 0.0,
        }

    return {
        "total_decisions": int(len(rows)),
        "decision_ownership_by_side": ownership_out,
        "decision_ownership_source": {
            "primary_signal": "policy_overridden_by_mcts",
            "override_signal_rows": int(total_override_signal_rows),
            "unknown_override_rows": int(total_unknown_override_rows),
        },
        "decision_ownership_total": {
            "rows": int(total_rows),
            "policy_kept": int(total_kept),
            "overwritten": int(total_overwritten),
            "override_signal_rows": int(total_override_signal_rows),
            "unknown_override_rows": int(total_unknown_override_rows),
            "policy_kept_rate": (total_kept / total_rows) if total_rows > 0 else 0.0,
            "overwritten_rate": (total_overwritten / total_rows) if total_rows > 0 else 0.0,
        },
        "execution_mismatch_by_side": mismatch_out,
        "execution_mismatch_total": {
            "rows": int(total_mismatch_rows),
            "execution_mismatch": int(total_execution_mismatch),
            "execution_match": int(total_execution_match),
            "execution_mismatch_rate": (
                (total_execution_mismatch / total_mismatch_rows)
                if total_mismatch_rows > 0
                else 0.0
            ),
        },
        "by_action_kind": by_kind_out,
        "by_action_kind_and_side": by_kind_side_out,
        "attack_effectiveness": attack_effectiveness,
    }, top_actions


def safe_percentile(values: List[float], q: float) -> Optional[float]:
    vals = [float(v) for v in list(values or []) if math.isfinite(float(v))]
    if not vals:
        return None
    vals.sort()
    if len(vals) == 1:
        return float(vals[0])
    qq = min(1.0, max(0.0, float(q)))
    pos = qq * float(len(vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(vals[lo])
    w = float(pos - lo)
    return float(vals[lo] * (1.0 - w) + vals[hi] * w)


def turn_bucket(turn: object) -> str:
    try:
        t = int(turn)
    except Exception:
        t = 0
    if t <= 3:
        return "early"
    if t <= 7:
        return "mid"
    return "late"


def compute_decision_diagnostics_kpis(
    trace_rows: List[Dict[str, object]],
) -> Dict[str, object]:
    rows = to_dict_rows(trace_rows)
    rows_by_step = index_rows_by_int_key(rows, key="step")
    eligible_steps = 0
    vp_approach_steps = 0
    regret_deltas: List[float] = []
    candidate_count = 0
    q_sat_count = 0
    step_spreads: List[float] = []
    vp_progress_observed_count = 0
    vp_progress_estimated_count = 0
    vp_progress_available_count = 0
    vp_progress_zero_count = 0
    tie_break_present_count = 0
    tie_break_zero_count = 0
    turn_bins: Dict[str, Dict[str, int]] = {
        "early": {"opportunity_steps": 0, "converted_steps": 0},
        "mid": {"opportunity_steps": 0, "converted_steps": 0},
        "late": {"opportunity_steps": 0, "converted_steps": 0},
    }
    first_immediate_opp_step = None
    first_immediate_capture_step = None
    path_len_episode = None
    q_clip_tol = 1e-3
    for _, row in sorted(rows_by_step.items(), key=lambda kv: kv[0]):
        candidates = [dict(c or {}) for c in list(row.get("mcts_action_candidates", []) or [])]
        chosen_action = str(row.get("action_id", "") or "")
        chosen = next((c for c in candidates if str(c.get("action_id", "")) == chosen_action), None)
        if row.get("vp_progress_observed", None) is not None:
            vp_progress_observed_count += 1
        if row.get("vp_progress_estimated_selected", None) is not None:
            vp_progress_estimated_count += 1
        vp_progress_val = row.get("vp_progress", None)
        if vp_progress_val is not None:
            try:
                vp_num = float(vp_progress_val)
                if math.isfinite(vp_num):
                    vp_progress_available_count += 1
                    if abs(vp_num) <= 1e-12:
                        vp_progress_zero_count += 1
            except Exception:
                pass
        tie_break_val = row.get("tie_break_term", None)
        if tie_break_val is not None:
            try:
                tb_num = float(tie_break_val)
                if math.isfinite(tb_num):
                    tie_break_present_count += 1
                    if abs(tb_num) <= 1e-12:
                        tie_break_zero_count += 1
            except Exception:
                pass
        if chosen is not None:
            eligible_steps += 1
            chosen_vp_delta = float(chosen.get("vp_progress_delta", 0.0) or 0.0)
            if chosen_vp_delta > 0.0:
                vp_approach_steps += 1
            chosen_score = float(chosen.get("real_decision_score", chosen.get("final_score", 0.0)) or 0.0)
            best_score = max(
                (
                    float(c.get("real_decision_score", c.get("final_score", 0.0)) or 0.0)
                    for c in candidates
                ),
                default=chosen_score,
            )
            regret_deltas.append(float(best_score - chosen_score))
        score_values: List[float] = []
        for c in candidates:
            q_val = float(c.get("mcts_q_value", 0.0) or 0.0)
            clip_limit_raw = c.get("q_clip_limit", row.get("mcts_q_guardrail_clip_limit", None))
            clip_limit = None
            try:
                if clip_limit_raw is not None:
                    clip_limit = abs(float(clip_limit_raw))
            except Exception:
                clip_limit = None
            if clip_limit is not None and clip_limit > 0.0:
                candidate_count += 1
                if abs(abs(q_val) - clip_limit) <= q_clip_tol:
                    q_sat_count += 1
            score_values.append(float(c.get("real_decision_score", c.get("final_score", 0.0)) or 0.0))
        p95 = safe_percentile(score_values, 0.95)
        p5 = safe_percentile(score_values, 0.05)
        if p95 is not None and p5 is not None:
            step_spreads.append(float(p95 - p5))
        immediate_opp = int(row.get("legal_capture_options", 0) or 0) > 0
        immediate_taken = bool(
            int(row.get("objective_converted", 0) or 0) > 0
            or bool(row.get("capture_like_taken", False))
        )
        if immediate_opp and first_immediate_opp_step is None:
            first_immediate_opp_step = int(row.get("step", 0) or 0)
        if (
            first_immediate_opp_step is not None
            and first_immediate_capture_step is None
            and immediate_taken
        ):
            first_immediate_capture_step = int(row.get("step", 0) or 0)
        bin_name = turn_bucket(row.get("game_turn", row.get("turn", 0)))
        if immediate_opp:
            turn_bins[bin_name]["opportunity_steps"] += 1
            if immediate_taken:
                turn_bins[bin_name]["converted_steps"] += 1
    if first_immediate_opp_step is not None and first_immediate_capture_step is not None:
        path_len_episode = max(0, int(first_immediate_capture_step - first_immediate_opp_step))
    spread_mean = (
        float(sum(step_spreads) / float(len(step_spreads)))
        if step_spreads
        else None
    )
    rows_count = int(len(rows))
    return {
        "vp_approach_rate_eligible_steps": int(eligible_steps),
        "vp_approach_rate_positive_steps": int(vp_approach_steps),
        "vp_approach_rate": (
            float(vp_approach_steps) / float(eligible_steps)
            if eligible_steps > 0
            else None
        ),
        "vp_regret_delta_count": int(len(regret_deltas)),
        "vp_regret_delta_mean": (
            float(sum(regret_deltas) / float(len(regret_deltas)))
            if regret_deltas
            else None
        ),
        "vp_regret_delta_p95": safe_percentile(regret_deltas, 0.95),
        "q_saturation_candidate_rows": int(candidate_count),
        "q_saturation_hits": int(q_sat_count),
        "q_saturation_rate": (
            float(q_sat_count) / float(candidate_count)
            if candidate_count > 0
            else None
        ),
        "decision_spread_step_count": int(len(step_spreads)),
        "decision_spread_mean": spread_mean,
        "decision_spread_p50": safe_percentile(step_spreads, 0.50),
        "decision_spread_p95": safe_percentile(step_spreads, 0.95),
        "vp_progress_observed_count": int(vp_progress_observed_count),
        "vp_progress_estimated_count": int(vp_progress_estimated_count),
        "vp_progress_available_count": int(vp_progress_available_count),
        "vp_progress_missing_count": int(max(0, rows_count - vp_progress_available_count)),
        "vp_progress_zero_count": int(vp_progress_zero_count),
        "vp_progress_observed_rate": (
            float(vp_progress_observed_count) / float(rows_count) if rows_count > 0 else None
        ),
        "vp_progress_estimated_rate": (
            float(vp_progress_estimated_count) / float(rows_count) if rows_count > 0 else None
        ),
        "vp_progress_available_rate": (
            float(vp_progress_available_count) / float(rows_count) if rows_count > 0 else None
        ),
        "vp_progress_zero_rate": (
            float(vp_progress_zero_count) / float(vp_progress_available_count)
            if vp_progress_available_count > 0
            else None
        ),
        "tie_break_present_count": int(tie_break_present_count),
        "tie_break_zero_count": int(tie_break_zero_count),
        "tie_break_present_rate": (
            float(tie_break_present_count) / float(rows_count) if rows_count > 0 else None
        ),
        "tie_break_zero_rate": (
            float(tie_break_zero_count) / float(tie_break_present_count)
            if tie_break_present_count > 0
            else None
        ),
        "path_to_capture_length_episode": (
            int(path_len_episode) if path_len_episode is not None else None
        ),
        "path_to_capture_length_count": (1 if path_len_episode is not None else 0),
        "path_to_capture_length_mean": (
            float(path_len_episode) if path_len_episode is not None else None
        ),
        "path_to_capture_length_p95": (
            float(path_len_episode) if path_len_episode is not None else None
        ),
        "opportunity_conversion_by_turn": {
            b: {
                "opportunity_steps": int(v["opportunity_steps"]),
                "converted_steps": int(v["converted_steps"]),
                "conversion_rate": (
                    float(v["converted_steps"]) / float(v["opportunity_steps"])
                    if int(v["opportunity_steps"]) > 0
                    else None
                ),
            }
            for b, v in turn_bins.items()
        },
        "opportunity_conversion_early_opportunity_steps": int(
            turn_bins["early"]["opportunity_steps"]
        ),
        "opportunity_conversion_early_converted_steps": int(
            turn_bins["early"]["converted_steps"]
        ),
        "opportunity_conversion_early_rate": (
            float(turn_bins["early"]["converted_steps"])
            / float(turn_bins["early"]["opportunity_steps"])
            if int(turn_bins["early"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_mid_opportunity_steps": int(
            turn_bins["mid"]["opportunity_steps"]
        ),
        "opportunity_conversion_mid_converted_steps": int(
            turn_bins["mid"]["converted_steps"]
        ),
        "opportunity_conversion_mid_rate": (
            float(turn_bins["mid"]["converted_steps"])
            / float(turn_bins["mid"]["opportunity_steps"])
            if int(turn_bins["mid"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_late_opportunity_steps": int(
            turn_bins["late"]["opportunity_steps"]
        ),
        "opportunity_conversion_late_converted_steps": int(
            turn_bins["late"]["converted_steps"]
        ),
        "opportunity_conversion_late_rate": (
            float(turn_bins["late"]["converted_steps"])
            / float(turn_bins["late"]["opportunity_steps"])
            if int(turn_bins["late"]["opportunity_steps"]) > 0
            else None
        ),
        "opportunity_conversion_turn_buckets_definition": "early: turn<=3, mid: turn 4-7, late: turn>=8",
    }
