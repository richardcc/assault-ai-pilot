from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlops.reporting.catalog_duckdb import load_catalog_summary_from_duckdb
from mlops.reporting.catalog_runtime import (
    load_catalog_payload as _load_catalog_payload_runtime,
)


def _model_id_aliases(model_id: str, engine: str = "") -> list[str]:
    m = str(model_id or "").strip()
    if not m:
        return []
    eng = str(engine or "").strip()
    out = {m}
    engines = [eng] if eng and eng != "__all__" else ["efficientzero_v2"]
    for e in engines:
        out.add(f"{e}_{m}")
        out.add(f"{e}_{e}_{m}")
        if m.startswith(f"{e}_"):
            stripped = m[len(e) + 1 :]
            out.add(stripped)
            if stripped.startswith(f"{e}_"):
                out.add(stripped[len(e) + 1 :])
        clean = m.replace(f"{e}_", "")
        if clean:
            out.add(clean)
            out.add(f"{e}_{clean}")
            out.add(f"{e}_{e}_{clean}")
    return sorted(out)


def _compact_eval_results(results_raw: Any) -> list[dict[str, Any]]:
    """Shrink eval payload for /api/v2/model to avoid giant JSON responses.

    Keep fields used by analytics tabs, drop heavy replay bodies (match_games)
    and heavy spatial grid observation maps inside decision steps.
    Replay data is loaded via dedicated replay endpoints from source_path.
    """
    if not isinstance(results_raw, list):
        return []
    out: list[dict[str, Any]] = []
    allowed_step_keys = {
        "mcts_q_clipped_count", "mcts_q_guardrail_clipped_count",
        "mcts_q_clip_denominator_count", "mcts_total_visits",
        "mcts_active_actions", "telemetry_coverage_status",
        "step", "game_turn", "action_id", "action_kind", "unit_side"
    }
    for item in results_raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if "match_games" in row:
            row.pop("match_games", None)

        steps = row.get("eval_decision_steps_top")
        if isinstance(steps, list):
            compact_steps = []
            for s in steps[:64]:
                if not isinstance(s, dict):
                    continue
                s_copy = {k: v for k, v in s.items() if k in allowed_step_keys}
                cands = s.get("mcts_action_candidates")
                if isinstance(cands, list):
                    s_copy["mcts_action_candidates"] = [
                        {
                            "visit_count": c.get("visit_count", 0),
                        }
                        for c in cands
                        if isinstance(c, dict)
                    ]
                compact_steps.append(s_copy)
            row["eval_decision_steps_top"] = compact_steps

        out.append(row)
    return out


_EVAL_FILE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TRACEABILITY_CACHE: tuple[float, dict[str, dict[str, Any]]] = (0.0, {})
_PARQUET_ROWS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_TRAIN_MANIFEST_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TRAIN_PAGE_CACHE: dict[tuple[str, float, str, str, int, int], dict[str, Any]] = {}
_SCHEMA_COLUMNS_CACHE: dict[str, set[str]] = {}


def _get_traceability_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    global _TRACEABILITY_CACHE
    trace_path = (repo_root / "runs_curriculum/experiments/reporting/curriculum_phase_traceability.jsonl").resolve()
    if not trace_path.exists():
        return {}
    try:
        mtime = trace_path.stat().st_mtime
        if _TRACEABILITY_CACHE[0] == mtime and _TRACEABILITY_CACHE[1]:
            return _TRACEABILITY_CACHE[1]

        index: dict[str, dict[str, Any]] = {}
        from datetime import datetime

        with trace_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                tid = str(d.get("train_run_id") or "").strip()
                eid = str(d.get("eval_run_id") or "").strip()
                s = str(d.get("phase_started_at") or "").strip()
                e = str(d.get("phase_finished_at") or "").strip()
                dur = None
                if s and e:
                    try:
                        t0 = datetime.fromisoformat(s.replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(e.replace("Z", "+00:00"))
                        dur = max(0.0, (t1 - t0).total_seconds())
                    except Exception:
                        pass
                entry = {
                    "phase_name": str(d.get("phase_name") or ""),
                    "phase_started_at": s,
                    "phase_finished_at": e,
                    "duration_seconds": dur,
                    "curriculum_name": str(d.get("curriculum_name") or ""),
                    "promotion_decision": str(d.get("promotion_decision") or ""),
                    "gate_result_status": str(d.get("gate_result_status") or ""),
                }
                if tid:
                    index[tid] = entry
                if eid:
                    index[eid] = entry
        _TRACEABILITY_CACHE = (mtime, index)
        return index
    except Exception:
        return {}


def _get_eval_file_payload(source_path: Path) -> dict[str, Any]:
    if not source_path.exists():
        return {}
    try:
        mtime = source_path.stat().st_mtime
        key = str(source_path.resolve())
        cached = _EVAL_FILE_CACHE.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        loaded = json.loads(source_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            _EVAL_FILE_CACHE[key] = (mtime, loaded)
            return loaded
    except Exception:
        pass
    return {}


def load_eval_history_page_from_parquet(
    *,
    repo_root: Path,
    engine: str,
    model_id: str,
    offset: int,
    limit: int,
    train_run_id: str = "",
    scenario_id: str = "__all__",
    include_payload: bool = False,
    parquet_rel_path: str = "runs_curriculum/experiments/reporting/indexes/catalog_evals.parquet",
) -> dict[str, Any]:
    pq_path = (repo_root / str(parquet_rel_path)).resolve()
    rows: list[dict[str, Any]] = []
    if not pq_path.exists():
        alt_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / "catalog_evals.parquet").resolve()
        if alt_path.exists():
            pq_path = alt_path

    if pq_path.exists():
        try:
            mtime = pq_path.stat().st_mtime
            key = str(pq_path)
            cached_pq = _PARQUET_ROWS_CACHE.get(key)
            if cached_pq and cached_pq[0] == mtime:
                rows = cached_pq[1]
            else:
                import pyarrow.parquet as pq  # type: ignore

                table = pq.read_table(pq_path)
                rows = [dict(r or {}) for r in (table.to_pylist() or [])]
                _PARQUET_ROWS_CACHE[key] = (mtime, rows)
        except Exception:
            rows = []

    if not rows:
        # Fallback to DuckDB catalog_evals if parquet is unavailable or empty
        db_path = (repo_root / "runs_curriculum" / "experiments" / "reporting" / "reporting.duckdb").resolve()
        if db_path.exists():
            try:
                import duckdb  # type: ignore
                con = duckdb.connect(str(db_path), read_only=True)
                aliases = _model_id_aliases(model_id, engine)
                m_clause = f"AND model_id IN ({', '.join(['?'] * len(aliases))})" if aliases else "AND model_id = ?"
                m_params = [str(engine or "")] + (aliases if aliases else [str(model_id or "")])
                t_clause = ""
                if str(train_run_id or "").strip():
                    t_clause = "AND train_run_id = ?"
                    m_params.append(str(train_run_id or "").strip())
                df = con.execute(f"SELECT * FROM catalog_evals WHERE engine = ? {m_clause} {t_clause}", m_params).df()
                con.close()
                rows = [dict(r or {}) for r in df.to_dict(orient="records")]
            except Exception:
                rows = []

    wanted_engine = str(engine or "")
    model_aliases = set(_model_id_aliases(model_id, engine))
    filtered = [
        r
        for r in rows
        if str(r.get("engine", "") or "") == wanted_engine
        and (str(r.get("model_id", "") or "") in model_aliases if model_aliases else True)
    ]
    wanted_train = str(train_run_id or "").strip()
    wanted_scenario = str(scenario_id or "__all__").strip() or "__all__"
    if wanted_train:
        filtered = [
            r for r in filtered
            if str(r.get("train_run_id", "") or "").strip() == wanted_train
        ]
    def _row_has_results(row: dict[str, Any]) -> bool:
        rc = row.get("results_count", None)
        if rc is not None:
            try:
                return int(rc) > 0
            except Exception:
                return True
        # No results_count column/value: keep row to avoid false negatives and
        # avoid expensive per-row source file reads.
        return True

    filtered = [r for r in filtered if _row_has_results(r)]
    if not filtered and wanted_train:
        for runs_root in ["runs_curriculum", "runs"]:
            xai_dir = repo_root / runs_root / wanted_train / "xai"
            if xai_dir.exists():
                for p in sorted(xai_dir.glob("bench_eval_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                    try:
                        p_data = json.loads(p.read_text(encoding="utf-8"))
                        p_res = list(p_data.get("results", []) or [])
                        p_hd = dict(p_data.get("head_diagnostics_eval", {}) or {})
                        p_diag = dict(p_data.get("diagnostics_summary_eval", {}) or {})
                        p_gate = dict(p_data.get("phase_2_9_promotion_gate", {}) or {})
                        eval_obj = {
                            "schema_version": "reporting_v2_strict",
                            "engine": wanted_engine or "efficientzero_v2",
                            "model_id": model_id,
                            "eval_id": p.stem.replace("bench_eval_", ""),
                            "train_run_id": wanted_train,
                            "scenario_id": str(p_data.get("scenario_id", "") or ""),
                            "created_at_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
                            "source_path": str(p),
                            "curriculum_phase": "",
                            "results_count": len(p_res),
                            "has_results": len(p_res) > 0,
                            "head_diagnostics_json": json.dumps(p_hd),
                            "diagnostics_summary_json": json.dumps(p_diag),
                            "phase_gate_json": json.dumps(p_gate),
                            "scenario_ids_json": json.dumps(list(dict.fromkeys([
                                str(sg.get("scenario_id", "")).strip()
                                for r in p_res for sg in list(r.get("seed_games", []) or [])
                                if str(sg.get("scenario_id", "")).strip()
                            ]))),
                            "compact_results_json": json.dumps(p_res),
                        }
                        filtered.append(eval_obj)
                    except Exception:
                        pass
                if filtered:
                    break
    filtered.sort(key=lambda r: str(r.get("created_at_utc", "") or ""), reverse=True)
    total = int(len(filtered))
    start = max(0, min(int(offset), total))
    end = max(start, min(total, start + int(limit)))
    page_rows = list(filtered[start:end])
    if not bool(include_payload):
        return {"rows": page_rows, "total": total}
    hydrated: list[dict[str, Any]] = []
    def _scenario_ids_from_results(results_rows: list[dict[str, Any]]) -> list[str]:
        out: set[str] = set()
        for rr in list(results_rows or []):
            seed_games = list(dict(rr or {}).get("seed_games", []) or [])
            for sg in seed_games:
                sid = str(dict(sg or {}).get("scenario_id", "") or "").strip()
                if sid:
                    out.add(sid)
        return sorted(out)

    def _result_matches_scenario(result_row: dict[str, Any], scenario_target: str) -> bool:
        target = str(scenario_target or "__all__").strip()
        if target == "__all__":
            return True
        seed_games = list(dict(result_row or {}).get("seed_games", []) or [])
        for sg in seed_games:
            sid = str(dict(sg or {}).get("scenario_id", "") or "").strip()
            if sid == target:
                return True
        row_sid = str(dict(result_row or {}).get("scenario_id", "") or "").strip()
        return bool(row_sid and row_sid == target and not row_sid.startswith("multi:"))
    for ev in page_rows:
        head_diag_raw = ev.get("head_diagnostics_json")
        compact_results_raw = ev.get("compact_results_json")
        parsed_payload: dict[str, Any] = {}
        source_path = Path(str(ev.get("source_path", "") or "")).expanduser()

        if head_diag_raw or compact_results_raw:
            # FAST PATH: Read directly from Parquet / DuckDB!
            try:
                head_diag = json.loads(str(head_diag_raw)) if head_diag_raw else {}
            except Exception:
                head_diag = {}
            try:
                diag_summary = json.loads(str(ev.get("diagnostics_summary_json", "{}"))) if ev.get("diagnostics_summary_json") else {}
            except Exception:
                diag_summary = {}
            try:
                phase_gate = json.loads(str(ev.get("phase_gate_json", "{}"))) if ev.get("phase_gate_json") else {}
            except Exception:
                phase_gate = {}
            try:
                results_all = json.loads(str(compact_results_raw)) if compact_results_raw else []
            except Exception:
                results_all = []
        else:
            # FALLBACK PATH: Read from disk with memory cache
            parsed_payload = _get_eval_file_payload(source_path)
            phase_gate = parsed_payload.get("phase_2_9_promotion_gate", ev.get("phase_2_9_promotion_gate", {}))
            head_diag = parsed_payload.get("head_diagnostics_eval", ev.get("head_diagnostics_eval", {}))
            diag_summary = parsed_payload.get("diagnostics_summary_eval", ev.get("diagnostics_summary_eval", {}))
            results_raw = parsed_payload.get("results", ev.get("results", []))
            results_all = _compact_eval_results(results_raw)

        results = [
            r for r in results_all
            if _result_matches_scenario(dict(r or {}), wanted_scenario)
        ]
        if wanted_scenario != "__all__" and not results:
            continue
        scenario_ids = _scenario_ids_from_results(results)
        scenario_id = str(ev.get("scenario_id", "") or parsed_payload.get("scenario_id", "") or "")
        if wanted_scenario != "__all__":
            scenario_id = wanted_scenario
        if not scenario_ids and scenario_id and not scenario_id.startswith("multi:"):
            scenario_ids = [scenario_id]
        hydrated.append(
            {
                "eval_id": str(ev.get("eval_id", "") or ""),
                "engine": str(ev.get("engine", "") or engine or ""),
                "train_run_id": str(
                    ev.get("train_run_id", "")
                    or parsed_payload.get("train_run_id", "")
                    or parsed_payload.get("run_id", "")
                    or ""
                ),
                "scenario_id": scenario_id,
                "scenario_ids": scenario_ids,
                "created_at_utc": str(ev.get("created_at_utc", "") or parsed_payload.get("created_at_utc", "") or ""),
                "source_path": str(ev.get("source_path", "") or ""),
                "phase_2_9_promotion_gate": dict(phase_gate or {}) if isinstance(phase_gate, dict) else {},
                "head_diagnostics_eval": dict(head_diag or {}) if isinstance(head_diag, dict) else {},
                "diagnostics_summary_eval": dict(diag_summary or {}) if isinstance(diag_summary, dict) else {},
                "results": list(results),
                "controller_unknown_label_rows": int(ev.get("controller_unknown_label_rows", 0) or 0),
            }
        )
    return {"rows": hydrated, "total": total}


def load_train_history_page_from_duckdb(
    *,
    repo_root: Path,
    engine: str,
    model_id: str,
    offset: int,
    limit: int,
    duckdb_rel_path: str = "runs_curriculum/experiments/reporting/reporting.duckdb",
) -> dict[str, Any]:
    db_path = (repo_root / str(duckdb_rel_path)).resolve()
    if not db_path.exists():
        return {"rows": [], "total": 0, "error": f"duckdb catalog not found: {db_path}"}
    mtime = db_path.stat().st_mtime
    cache_key = (str(db_path), mtime, str(engine or ""), str(model_id or ""), int(offset), int(limit))
    cached_trains = _TRAIN_PAGE_CACHE.get(cache_key)
    if cached_trains is not None:
        return cached_trains
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return {"rows": [], "total": 0, "error": f"duckdb import failed: {exc}"}
    import time
    con = None
    last_exc = None
    for attempt in range(6):
        try:
            con = duckdb.connect(str(db_path), read_only=True)
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 5:
                time.sleep(0.15 * (attempt + 1))
    if con is None:
        return {"rows": [], "total": 0, "error": f"duckdb temporarily busy: {last_exc}"}
    try:
        aliases = _model_id_aliases(model_id, engine)
        if aliases:
            placeholders = ", ".join(["?"] * len(aliases))
            model_clause = f"AND model_id IN ({placeholders})"
            model_params = aliases
        else:
            model_clause = "AND model_id = ?"
            model_params = [str(model_id or "")]

        total = int(
            con.execute(
                f"""
                SELECT COUNT(*) FROM catalog_trains
                WHERE engine = ? {model_clause}
                """,
                [str(engine or "")] + model_params,
            ).fetchone()[0]
        )
        start = max(0, min(int(offset), total))
        model_clause_t = model_clause.replace("model_id", "t.model_id")
        rows = con.execute(
            f"""
            SELECT
                t.run_id, t.scenario_id, t.created_at_utc, t.git_commit,
                t.is_retrain, t.parent_run_id, t.latest_checkpoint,
                COUNT(e.eval_id) AS evals_count
            FROM catalog_trains t
            LEFT JOIN catalog_evals e ON t.run_id = e.train_run_id
            WHERE t.engine = ? {model_clause_t}
            GROUP BY t.run_id, t.scenario_id, t.created_at_utc, t.git_commit, t.is_retrain, t.parent_run_id, t.latest_checkpoint
            ORDER BY t.created_at_utc DESC
            LIMIT ? OFFSET ?
            """,
            [str(engine or "")] + model_params + [int(limit), int(start)],
        ).fetchall()
        out_rows = []
        runs_roots = ["runs_curriculum", "runs"]
        trace_index = _get_traceability_index(repo_root)
        for r in rows:
            run_id = str(r[0] or "")
            scenario_id = str(r[1] or "")
            trace_entry = trace_index.get(run_id, {})
            row_obj: dict[str, Any] = {
                "run_id": run_id,
                "scenario_id": scenario_id,
                "created_at_utc": str(r[2] or ""),
                "git_commit": str(r[3] or ""),
                "is_retrain": bool(r[4]),
                "parent_run_id": str(r[5] or ""),
                "latest_checkpoint": str(r[6] or ""),
                "evals_count": int(r[7] or 0),
                "curriculum_phase": str(trace_entry.get("phase_name") or ""),
                "phase_started_at": str(trace_entry.get("phase_started_at") or ""),
                "phase_finished_at": str(trace_entry.get("phase_finished_at") or ""),
                "duration_seconds": trace_entry.get("duration_seconds"),
            }
            manifest = _load_train_manifest_by_run_id(
                repo_root=repo_root, runs_roots=runs_roots, run_id=run_id
            )
            cfg = dict((manifest or {}).get("config", {}) or {})
            row_obj["config"] = cfg
            scenario_mix = dict(cfg.get("scenario_mix", {}) or {})
            scenario_cfg = dict(cfg.get("scenario", {}) or {})
            mix_ids = list(
                scenario_cfg.get("ids", scenario_mix.get("ids", [])) or []
            )
            mix_weights = list(
                scenario_cfg.get("weights", scenario_mix.get("weights", [])) or []
            )
            scenario_mix_ids = [str(x).strip() for x in mix_ids if str(x or "").strip()]
            row_obj["scenario_mix_ids"] = scenario_mix_ids
            if scenario_mix_ids:
                row_obj["scenario_ids"] = list(dict.fromkeys(scenario_mix_ids))
            else:
                sid_clean = str(scenario_id or "").strip()
                row_obj["scenario_ids"] = [sid_clean] if sid_clean and not sid_clean.startswith("multi:") else []
            parsed_weights: list[float] = []
            for w in mix_weights:
                try:
                    parsed_weights.append(float(w))
                except Exception:
                    continue
            row_obj["scenario_mix_weights"] = parsed_weights
            out_rows.append(row_obj)
        res = {"rows": out_rows, "total": total}
        _TRAIN_PAGE_CACHE[cache_key] = res
        return res
    except Exception as exc:
        return {"rows": [], "total": 0, "error": f"duckdb train query failed: {exc}"}
    finally:
        con.close()


def load_elo_rows_from_duckdb(
    *,
    repo_root: Path,
    engine: str,
    model_id: str,
    side: str = "__all__",
    controller: str = "__all__",
    scenario_id: str = "__all__",
    matchup_profile: str = "__all__",
    eval_id_like: str = "",
    created_at_like: str = "",
    duckdb_rel_path: str = "runs_curriculum/experiments/reporting/reporting.duckdb",
    limit: int = 20000,
) -> dict[str, Any]:
    db_path = (repo_root / str(duckdb_rel_path)).resolve()
    if not db_path.exists():
        return {"rows": [], "total": 0, "error": f"duckdb catalog not found: {db_path}"}
    try:
        import duckdb  # type: ignore
    except Exception as exc:
        return {"rows": [], "total": 0, "error": f"duckdb import failed: {exc}"}
    import time
    con = None
    last_exc = None
    for attempt in range(6):
        try:
            con = duckdb.connect(str(db_path), read_only=True)
            break
        except Exception as exc:
            last_exc = exc
            if attempt < 5:
                time.sleep(0.15 * (attempt + 1))
    if con is None:
        return {"rows": [], "total": 0, "error": f"duckdb temporarily busy: {last_exc}"}
    try:
        required_cols = {
            "model_id",
            "created_at_utc",
            "eval_id",
            "scenario_id",
            "curriculum_phase",
            "matchup_profile",
            "side",
            "controller",
            "opponent_controller",
            "seed",
            "episodes",
            "win_rate",
            "draw_rate",
            "loss_rate",
            "total_victory_rate",
            "victory_rate",
            "defeat_rate",
            "total_defeat_rate",
            "avg_return",
            "tracked_captured_avg",
            "vp_net_avg_side",
            "winner_rate_side",
            "units_alive_final",
            "units_lost",
            "enemy_units_eliminated",
            "damage_dealt",
        }
        available_cols = _SCHEMA_COLUMNS_CACHE.get("catalog_eval_result_sides")
        if available_cols is None:
            schema_rows = con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'catalog_eval_result_sides'"
            ).fetchall()
            available_cols = {str(r[0] or "").strip() for r in schema_rows}
            _SCHEMA_COLUMNS_CACHE["catalog_eval_result_sides"] = available_cols
        missing_cols = sorted([c for c in required_cols if c not in available_cols])
        if missing_cols:
            return {
                "rows": [],
                "total": 0,
                "error": (
                    "duckdb schema invalid: catalog_eval_result_sides missing required columns: "
                    + ", ".join(missing_cols)
                    + ". Rebuild catalog/duckdb with current publisher."
                ),
            }
        where: list[str] = []
        params: list[Any] = []
        engine_s = str(engine or "").strip()
        if engine_s and engine_s != "__all__":
            where.append("engine = ?")
            params.append(engine_s)
        model_s = str(model_id or "").strip()
        if model_s and model_s != "__all__":
            aliases = _model_id_aliases(model_s, engine_s)
            if aliases:
                placeholders = ", ".join(["?"] * len(aliases))
                where.append(f"model_id IN ({placeholders})")
                params.extend(aliases)
            else:
                where.append("model_id = ?")
                params.append(model_s)
        side_s = str(side or "").strip()
        if side_s and side_s != "__all__":
            where.append("side = ?")
            params.append(side_s)
        controller_s = str(controller or "").strip()
        if controller_s and controller_s != "__all__":
            where.append("controller = ?")
            params.append(controller_s)
        scenario_s = str(scenario_id or "").strip()
        if scenario_s and scenario_s != "__all__":
            where.append("scenario_id = ?")
            params.append(scenario_s)
        profile_s = str(matchup_profile or "").strip()
        if profile_s and profile_s != "__all__":
            where.append("matchup_profile = ?")
            params.append(profile_s)
        eval_like = str(eval_id_like or "").strip()
        if eval_like:
            where.append("LOWER(eval_id) LIKE ?")
            params.append(f"%{eval_like.lower()}%")
        created_like = str(created_at_like or "").strip()
        if created_like:
            where.append("LOWER(created_at_utc) LIKE ?")
            params.append(f"%{created_like.lower()}%")
        where_sql = " AND ".join(where) if where else "TRUE"

        def _query_rows(query_where_sql: str, query_params: list[Any]):
            total_local = int(
                con.execute(
                    f"SELECT COUNT(*) FROM catalog_eval_result_sides WHERE {query_where_sql}",
                    query_params,
                ).fetchone()[0]
            )
            rows_local = con.execute(
                f"""
                SELECT
                    model_id, created_at_utc, eval_id, scenario_id, matchup_profile,
                    curriculum_phase, side, controller, opponent_controller, seed, episodes, win_rate, draw_rate, loss_rate,
                    total_victory_rate, victory_rate, defeat_rate, total_defeat_rate,
                    avg_return, tracked_captured_avg, vp_net_avg_side, winner_rate_side,
                    units_alive_final, units_lost, enemy_units_eliminated, damage_dealt
                FROM catalog_eval_result_sides
                WHERE {query_where_sql}
                ORDER BY created_at_utc DESC, eval_id DESC, model_id ASC, matchup_profile ASC, side ASC
                LIMIT ?
                """,
                [*query_params, int(max(1, min(int(limit), 50000)))],
            ).fetchall()
            return total_local, rows_local

        total, rows = _query_rows(where_sql, params)
        warning = ""
        if total <= 0 and engine_s:
            # Recovery path for inconsistent/legacy engine tags in index rows.
            fallback_where = " AND ".join([w for w in where if w != "engine = ?"]) or "TRUE"
            fallback_params = params[1:] if params else []
            total_fb, rows_fb = _query_rows(fallback_where, fallback_params)
            if total_fb > 0:
                total, rows = total_fb, rows_fb
                warning = f"engine filter '{engine_s}' returned no rows; used fallback without engine filter"
        out_rows = []
        for r in rows:
            seed_val = None if r[9] is None else int(r[9])
            episodes = int(r[10] or 0)
            if episodes <= 0:
                episodes = 1
            win_rate = float(r[11] or 0.0)
            draw_rate = float(r[12] or 0.0)
            loss_rate = float(r[13] or 0.0)
            total_victory_rate = float(r[14] or 0.0)
            victory_rate = float(r[15] or 0.0)
            defeat_rate = float(r[16] or 0.0)
            total_defeat_rate = float(r[17] or 0.0)
            wins = int(round(win_rate * episodes))
            draws = int(round(draw_rate * episodes))
            losses = int(max(0, episodes - wins - draws))
            # Keep score continuous from rates; avoid quantization drift from rounded counts.
            score = float(win_rate + (0.5 * draw_rate))
            row_obj = {
                "model_id": str(r[0] or ""),
                "created_at_utc": str(r[1] or ""),
                "eval_id": str(r[2] or ""),
                "scenario_id": str(r[3] or ""),
                "matchup_profile": str(r[4] or ""),
                "curriculum_phase": str(r[5] or ""),
                "side": str(r[6] or ""),
                "controller": str(r[7] or ""),
                "opponent_controller": str(r[8] or ""),
                "seed": seed_val,
                "episodes": int(episodes),
                "wins": int(wins),
                "draws": int(draws),
                "losses": int(losses),
                "win_rate": float(win_rate),
                "draw_rate": float(draw_rate),
                "loss_rate": float(loss_rate),
                "score": float(score),
                "total_victory_rate": float(total_victory_rate),
                "victory_rate": float(victory_rate),
                "defeat_rate": float(defeat_rate),
                "total_defeat_rate": float(total_defeat_rate),
                "avg_return": float(r[18] or 0.0),
                "tracked_captured_avg": float(r[19] or 0.0),
                "vp_net_avg_side": (None if r[20] is None else float(r[20])),
                "winner_rate_side": (None if r[21] is None else float(r[21])),
                "units_alive_final": (None if r[22] is None else float(r[22])),
                "units_lost": (None if r[23] is None else float(r[23])),
                "enemy_units_eliminated": (None if r[24] is None else float(r[24])),
                "damage_dealt": (None if r[25] is None else float(r[25])),
            }
            out_rows.append(row_obj)
        out = {"rows": out_rows, "total": len(out_rows)}
        if warning:
            out["warning"] = warning
        return out
    except Exception as exc:
        return {"rows": [], "total": 0, "error": f"duckdb elo query failed: {exc}"}
    finally:
        con.close()


def _load_train_manifest_by_run_id(
    repo_root: Path, runs_roots: list[str], run_id: str
) -> dict[str, Any]:
    rid = str(run_id or "").strip()
    if not rid:
        return {}
    for root_rel in runs_roots:
        p = (repo_root / str(root_rel) / rid / "run_manifest.json").resolve()
        if not p.exists():
            continue
        try:
            mtime = p.stat().st_mtime
            key = str(p)
            cached = _TRAIN_MANIFEST_CACHE.get(key)
            if cached and cached[0] == mtime:
                return cached[1]
            payload = json.loads(p.read_text(encoding="utf-8"))
            res = payload if isinstance(payload, dict) else {}
            _TRAIN_MANIFEST_CACHE[key] = (mtime, res)
            return res
        except Exception:
            return {}
    return {}


def load_model_detail_index_first(
    *,
    repo_root: Path,
    catalog_rel_path: str,
    engine: str,
    model_id: str,
    train_limit: int = 64,
    eval_limit: int = 64,
) -> dict[str, Any]:
    runs_roots = ["runs_curriculum/experiments", "runs_curriculum", "runs"]
    summary = load_catalog_summary_from_duckdb(repo_root=repo_root)
    if str((summary or {}).get("error", "") or "").strip():
        return {"error": str(summary.get("error", ""))}
    aliases = set(_model_id_aliases(model_id, engine))
    engines = list(summary.get("engines", []) or [])
    engine_row = next((e for e in engines if str(e.get("engine", "")) == str(engine or "")), {})
    model_row = next(
        (m for m in list(engine_row.get("models", []) or []) if (str(m.get("model_id", "")) in aliases if aliases else str(m.get("model_id", "")) == str(model_id or ""))),
        {},
    )
    if not isinstance(model_row, dict) or not model_row:
        return {
            "schema_version": "reporting_v2_strict",
            "engine": str(engine or ""),
            "model_id": str(model_id or ""),
            "algorithm": str(engine or ""),
            "train_history": [],
            "eval_history": [],
            "scenarios_seen": [],
            "scenario_train_counts": {},
            "scenario_eval_counts": {},
        }
    out = dict(model_row)
    canonical_model_id = str(model_row.get("model_id", "") or model_id or "")
    train_page = load_train_history_page_from_duckdb(
        repo_root=repo_root,
        engine=str(engine or ""),
        model_id=canonical_model_id,
        offset=0,
        limit=max(1, int(train_limit)),
    )
    train_rows = list(train_page.get("rows", []) or [])
    total_trains = int(train_page.get("total", len(train_rows)) or len(train_rows))
    for tr in train_rows:
        cfg = dict(tr.get("config", {}) or {})
        if not cfg:
            manifest = _load_train_manifest_by_run_id(
                repo_root=repo_root, runs_roots=runs_roots, run_id=str(tr.get("run_id", ""))
            )
            cfg = dict(manifest.get("config", {}) or {})
            tr["config"] = cfg
        obj_sig = dict(cfg.get("objective_signal", {}) or {})
        obj_head = dict(cfg.get("objective_head", {}) or {})
        obj_rep = dict(cfg.get("objective_reporting", {}) or {})
        rw_shaping = dict(dict(cfg.get("selfplay", {}) or {}).get("reward_shaping", {}) or {})
        raw_warn = list(cfg.get("config_preflight_warnings", []) or [])
        clean_warn = [
            w for w in raw_warn
            if not (w == "missing.train.objective_signal" and bool(obj_sig))
            and not (w == "missing.train.objective_head" and bool(obj_head))
            and not (w == "missing.train.objective_reporting" and bool(obj_rep))
            and not (w == "missing.selfplay.reward_shaping" and bool(rw_shaping))
        ]
        tr["objective_reward_config"] = {
            "objective_signal": obj_sig,
            "objective_head": obj_head,
            "objective_reporting": obj_rep,
            "reward_shaping": rw_shaping,
            "preflight_warnings": clean_warn,
        }
    initial_train_run_id = ""
    for tr in train_rows:
        if int(tr.get("evals_count", 0) or 0) > 0:
            initial_train_run_id = str(tr.get("run_id", "") or "")
            break
    if not initial_train_run_id and train_rows:
        initial_train_run_id = str(train_rows[0].get("run_id", "") or "")
    eval_page = load_eval_history_page_from_parquet(
        repo_root=repo_root,
        engine=str(engine or ""),
        model_id=canonical_model_id,
        offset=0,
        limit=max(1, int(eval_limit)),
        train_run_id=initial_train_run_id,
        include_payload=True,
    )
    if not eval_page.get("rows"):
        eval_page = load_eval_history_page_from_parquet(
            repo_root=repo_root,
            engine=str(engine or ""),
            model_id=canonical_model_id,
            offset=0,
            limit=max(1, int(eval_limit)),
            train_run_id="",
            include_payload=True,
        )
        if eval_page.get("rows"):
            first_row_train = str((eval_page["rows"][0].get("train_run_id", "") or "")).strip()
            if first_row_train:
                initial_train_run_id = first_row_train
    all_eval_page = load_eval_history_page_from_parquet(
        repo_root=repo_root,
        engine=str(engine or ""),
        model_id=canonical_model_id,
        offset=0,
        limit=1,
        include_payload=False,
    )
    total_model_evals = int(all_eval_page.get("total", 0) or 0)
    eval_rows = list(eval_page.get("rows", []) or [])
    total_initial_evals = int(eval_page.get("total", len(eval_rows)) or len(eval_rows))
    eval_out: list[dict[str, Any]] = [dict(x or {}) for x in eval_rows]
    out["train_history"] = train_rows
    out["eval_history"] = eval_out
    out["train_history_total_count"] = int(total_trains)
    out["train_history_visible_count"] = int(len(train_rows))
    out["train_history_truncated"] = bool(len(train_rows) < total_trains)
    out["eval_history_total_count"] = int(total_model_evals)
    out["eval_history_visible_count"] = int(len(eval_out))
    out["eval_history_truncated"] = bool(len(eval_out) < total_initial_evals)
    out["initial_train_run_id"] = initial_train_run_id
    scenario_train_counts: dict[str, int] = {}
    scenario_eval_counts: dict[str, int] = {}
    for tr in train_rows:
        sids = [str(x).strip() for x in list(tr.get("scenario_ids", []) or []) if str(x).strip()]
        for sid in sids:
            scenario_train_counts[sid] = scenario_train_counts.get(sid, 0) + 1
    for ev in eval_out:
        sids = [str(x).strip() for x in list(ev.get("scenario_ids", []) or []) if str(x).strip()]
        for sid in sids:
            scenario_eval_counts[sid] = scenario_eval_counts.get(sid, 0) + 1
    out["scenario_train_counts"] = scenario_train_counts
    out["scenario_eval_counts"] = scenario_eval_counts
    out["scenarios_seen"] = sorted(
        set(list(scenario_train_counts.keys()) + list(scenario_eval_counts.keys()))
    )
    out["schema_version"] = "reporting_v2_strict"
    return out


def load_scenario_overlay(repo_root: Path, scenario_id: str) -> dict:
    sid = str(scenario_id or "").strip()
    if not sid:
        return {}
    if sid.startswith("multi:"):
        sub_sids = [s.strip() for s in sid[len("multi:") :].split("|") if s.strip()]
        if sub_sids:
            sid = sub_sids[0]
    scenarios_dir = (repo_root / "assault_sim" / "assets" / "scenarios").resolve()
    if not scenarios_dir.exists():
        return {}
    catalogs_dir = (repo_root / "assault_sim" / "assets" / "catalogs").resolve()
    map_piece_catalog_path = catalogs_dir / "map_piece_catalog.json"
    map_piece_catalog: dict = {}
    if map_piece_catalog_path.exists():
        try:
            map_piece_catalog = json.loads(map_piece_catalog_path.read_text(encoding="utf-8"))
        except Exception:
            map_piece_catalog = {}

    def _rot_quarters(deg: int) -> int:
        if deg % 90 != 0:
            return 0
        return (deg // 90) % 4

    def _rotate_local(q: int, r: int, width: int, height: int, qturns: int) -> tuple[int, int]:
        if qturns == 0:
            return q, r
        if qturns == 1:
            return (height - 1 - r), q
        if qturns == 2:
            return (width - 1 - q), (height - 1 - r)
        return r, (width - 1 - q)

    def _build_map_cells(raw_scenario: dict) -> list[dict]:
        pieces = list((raw_scenario.get("map", {}) or {}).get("pieces", []) or [])
        cat_pieces = dict((map_piece_catalog.get("pieces", {}) or {}))
        cells: dict[tuple[int, int], str] = {}
        for entry in pieces:
            if not isinstance(entry, dict):
                continue
            piece_id = str(entry.get("id", "") or "")
            piece = dict(cat_pieces.get(piece_id, {}) or {})
            shape = list(piece.get("shape", []) or [])
            if len(shape) < 2:
                continue
            width = int(shape[0] or 0)
            height = int(shape[1] or 0)
            if width <= 0 or height <= 0:
                continue
            origin_raw = entry.get("origin", entry)
            if isinstance(origin_raw, dict):
                oq = int(origin_raw.get("q", 0) or 0)
                orr = int(origin_raw.get("r", 0) or 0)
            elif isinstance(origin_raw, (list, tuple)) and len(origin_raw) >= 2:
                oq = int(origin_raw[0] or 0)
                orr = int(origin_raw[1] or 0)
            else:
                oq = int(entry.get("q", 0) or 0)
                orr = int(entry.get("r", 0) or 0)
            qturns = _rot_quarters(int(entry.get("rotation", 0) or 0))

            hex_terrain_map: dict[tuple[int, int], str] = {}
            for h in list(piece.get("hexes", []) or []):
                if isinstance(h, dict) and "q" in h and "r" in h:
                    hex_terrain_map[(int(h["q"]), int(h["r"]))] = str(h.get("terrain", "clear") or "clear")

            for lq in range(width):
                for lr in range(height):
                    rq, rr = _rotate_local(lq, lr, width, height, qturns)
                    t = hex_terrain_map.get((lq, lr), "clear")
                    cells[(int(rq + oq), int(rr + orr))] = t
        return [{"q": int(q), "r": int(r), "terrain": t} for (q, r), t in sorted(cells.items(), key=lambda x: (x[0][1], x[0][0]))]

    def _enrich_pieces(pieces: list) -> list[dict]:
        cat_pieces = dict((map_piece_catalog.get("pieces", {}) or {}))
        out = []
        for pentry in pieces:
            if not isinstance(pentry, dict):
                continue
            pid = str(pentry.get("id", "") or "")
            cat_p = dict(cat_pieces.get(pid, {}) or {})
            shape = list(pentry.get("shape", cat_p.get("shape", [])) or cat_p.get("shape", []) or [9, 4])
            origin_raw = pentry.get("origin", pentry)
            if isinstance(origin_raw, dict):
                oq = int(origin_raw.get("q", 0) or 0)
                orr = int(origin_raw.get("r", 0) or 0)
            elif isinstance(origin_raw, (list, tuple)) and len(origin_raw) >= 2:
                oq = int(origin_raw[0] or 0)
                orr = int(origin_raw[1] or 0)
            else:
                oq = int(pentry.get("q", 0) or 0)
                orr = int(pentry.get("r", 0) or 0)
            out.append({
                "id": pid,
                "origin": [oq, orr],
                "q": oq,
                "r": orr,
                "rotation": int(pentry.get("rotation", 0) or 0),
                "shape": shape,
            })
        return out

    def _enrich_units(raw_units: list) -> list[dict]:
        out_u = []
        for u in raw_units:
            if not isinstance(u, dict):
                continue
            row = dict(u)
            pos = u.get("position", u)
            if isinstance(pos, dict):
                uq = int(pos.get("q", 0) or 0)
                ur = int(pos.get("r", 0) or 0)
            elif isinstance(pos, (list, tuple)) and len(pos) >= 2:
                uq = int(pos[0] or 0)
                ur = int(pos[1] or 0)
            else:
                uq = int(u.get("q", 0) or 0)
                ur = int(u.get("r", 0) or 0)
            row["q"] = uq
            row["r"] = ur
            row["position"] = {"q": uq, "r": ur}
            out_u.append(row)
        return out_u

    candidates = [scenarios_dir / f"{sid}.json"]
    for c in candidates:
        if c.exists():
            try:
                raw = json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            vp = dict(raw.get("vp", {}) or {})
            hexes = list(vp.get("hexes", []) or [])
            shape = list(raw.get("shape", []) or [])
            map_cells = _build_map_cells(raw)
            forts = list((raw.get("map", {}) or {}).get("fortifications", []) or [])
            pieces_list = _enrich_pieces(list((raw.get("map", {}) or {}).get("pieces", []) or []))
            return {
                "path": str(c),
                "scenario_id": sid,
                "shape": shape if len(shape) >= 2 else [],
                "max_turns": int(raw.get("max_turns", 0) or 0),
                "map_cells": map_cells,
                "fortifications": forts,
                "pieces": pieces_list,
                "scenario_units": _enrich_units(list(raw.get("units", []) or [])),
                "vp_hexes": [
                    {
                        "q": int(h.get("q", 0) or 0),
                        "r": int(h.get("r", 0) or 0),
                        "initial_owner": str(h.get("initial_owner", "") or ""),
                        "value": float(h.get("value", vp.get("value_per_hex", 1)) or 1),
                    }
                    for h in hexes
                    if isinstance(h, dict)
                ],
            }
    for p in list(scenarios_dir.glob("*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        internal_id = str(raw.get("id", "") or "").strip()
        if internal_id != sid:
            continue
        vp = dict(raw.get("vp", {}) or {})
        hexes = list(vp.get("hexes", []) or [])
        shape = list(raw.get("shape", []) or [])
        map_cells = _build_map_cells(raw)
        forts = list((raw.get("map", {}) or {}).get("fortifications", []) or [])
        pieces_list = _enrich_pieces(list((raw.get("map", {}) or {}).get("pieces", []) or []))
        return {
            "path": str(p),
            "scenario_id": sid,
            "shape": shape if len(shape) >= 2 else [],
            "max_turns": int(raw.get("max_turns", 0) or 0),
            "map_cells": map_cells,
            "fortifications": forts,
            "pieces": pieces_list,
            "scenario_units": _enrich_units(list(raw.get("units", []) or [])),
            "vp_hexes": [
                {
                    "q": int(h.get("q", 0) or 0),
                    "r": int(h.get("r", 0) or 0),
                    "initial_owner": str(h.get("initial_owner", "") or ""),
                    "value": float(h.get("value", vp.get("value_per_hex", 1)) or 1),
                }
                for h in hexes
                if isinstance(h, dict)
            ],
        }
    return {}


def load_scenario_detail(repo_root: Path, scenario_id: str) -> dict[str, Any]:
    """Load scenario configuration and enrich victory outcomes table with canonical outcome classes and duals."""
    from assault_model.core.victory_outcomes import OutcomeClass

    sid = str(scenario_id or "").strip()
    if sid.startswith("multi:"):
        parts = sid[len("multi:"):].split("|")
        sid = parts[0].strip() if parts else sid

    scenarios_dir = (repo_root / "assault_sim" / "assets" / "scenarios").resolve()
    if not scenarios_dir.exists():
        return {"ok": False, "error": "scenarios_dir_not_found"}

    target_path: Path | None = None
    if sid:
        cand = scenarios_dir / f"{sid}.json"
        if cand.exists():
            target_path = cand
        else:
            for p in sorted(scenarios_dir.glob("*.json")):
                if p.stem == sid:
                    target_path = p
                    break
                try:
                    raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                    if str(raw.get("id", "")).strip() == sid:
                        target_path = p
                        break
                except Exception:
                    continue

    if not target_path:
        all_scens = sorted(scenarios_dir.glob("*.json"))
        if sid:
            for p in all_scens:
                if sid in p.stem or p.stem in sid:
                    target_path = p
                    break
        if not target_path and all_scens:
            target_path = all_scens[0]

    if not target_path or not target_path.exists():
        return {"ok": False, "error": "scenario_not_found", "scenario_id": sid}

    try:
        data = json.loads(target_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"ok": False, "error": "invalid_scenario_json", "message": str(exc)}

    vo = dict(data.get("victory_outcomes", {}) or {})
    tracked_side = str(vo.get("tracked_side", "US")).strip().upper()
    metric = str(vo.get("metric", "objectives_captured")).strip()
    timing = str(vo.get("timing", "end_of_last_turn")).strip()
    table = list(vo.get("table", []) or [])

    units = list(data.get("units", []) or [])
    sides = sorted(list({str(u.get("side", "")).strip().upper() for u in units if str(u.get("side", "")).strip()}))
    opponent_side = ""
    for s in sides:
        if s != tracked_side:
            opponent_side = s
            break

    enriched_table = []
    for row in table:
        r = dict(row or {})
        res = str(r.get("result", "") or "")
        oc = str(r.get("outcome_class", "") or "")
        cls = OutcomeClass.from_str(oc or res)
        dual_cls = cls.dual
        r["canonical_class"] = cls.value
        r["canonical_score"] = cls.score
        r["dual_class"] = dual_cls.value
        r["dual_score"] = dual_cls.score
        enriched_table.append(r)

    vp = dict(data.get("vp", {}) or {})
    hexes = list(vp.get("hexes", []) or [])

    # Calculate initial ownership of objectives
    initial_objectives_by_side: dict[str, int] = {}
    for h in hexes:
        owner = str(h.get("initial_owner", "") or "").strip().upper()
        if owner:
            initial_objectives_by_side[owner] = initial_objectives_by_side.get(owner, 0) + 1

    return {
        "ok": True,
        "scenario_id": str(data.get("id", target_path.stem)),
        "filename": target_path.name,
        "max_turns": data.get("max_turns"),
        "shape": data.get("shape"),
        "sides": sides,
        "tracked_side": tracked_side,
        "opponent_side": opponent_side,
        "initial_objectives_by_side": initial_objectives_by_side,
        "vp": {
            "value_per_hex": vp.get("value_per_hex", 1),
            "hexes": hexes,
            "total_objectives": len(hexes),
        },
        "victory_outcomes": {
            "tracked_side": tracked_side,
            "metric": metric,
            "timing": timing,
            "table": enriched_table,
        },
    }

