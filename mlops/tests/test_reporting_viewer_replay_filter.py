from mlops.reporting.viewer import _model_html


def _step_has_relevant_unit_activity(step_row: dict, unit_id: str) -> bool:
    wanted = str(unit_id or "").strip()
    if not wanted or wanted == "__all__":
        return True
    if not isinstance(step_row, dict):
        return False

    def unit_matches(value: object) -> bool:
        return str(value or "").strip() == wanted

    def contains_wanted(value: object) -> bool:
        if not value:
            return False
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    if (
                        unit_matches(item.get("unit_id"))
                        or unit_matches(item.get("id"))
                        or unit_matches(item.get("actor_unit_id"))
                        or unit_matches(item.get("target_unit_id"))
                    ):
                        return True
                elif unit_matches(item):
                    return True
            return False
        if isinstance(value, dict):
            return (
                unit_matches(value.get("unit_id"))
                or unit_matches(value.get("id"))
                or unit_matches(value.get("actor_unit_id"))
                or unit_matches(value.get("target_unit_id"))
            )
        return unit_matches(value)

    action_id = str(step_row.get("action_id") or "").strip()
    if action_id and f":{wanted}:" in action_id:
        return True
    if unit_matches(step_row.get("unit_id")):
        return True
    if unit_matches(step_row.get("actor_unit_id")):
        return True
    if unit_matches(step_row.get("target_unit_id")):
        return True
    if contains_wanted(step_row.get("unit_event")):
        return True
    if contains_wanted(step_row.get("unit_events")):
        return True
    if contains_wanted(step_row.get("events")):
        return True
    if contains_wanted(step_row.get("runtime_events")):
        return True
    if contains_wanted(step_row.get("event_unit_ids")):
        return True
    if contains_wanted(step_row.get("affected_unit_ids")):
        return True
    # Intentional: board-state presence ("units") must not count as activity.
    return False


def _resolve_replay_step_delta(transitions: list[dict], current_step: int, delta: int, unit_filter: str) -> int:
    if not transitions:
        return 0
    max_step = max(0, len(transitions) - 1)
    current = max(0, min(max_step, int(current_step)))
    direction = 1 if int(delta) >= 0 else -1
    if str(unit_filter or "__all__") == "__all__":
        return max(0, min(max_step, current + direction))

    idx = current + direction
    while 0 <= idx <= max_step:
        if _step_has_relevant_unit_activity(transitions[idx], unit_filter):
            return idx
        idx += direction
    return current


def test_model_html_includes_replay_unit_filter_controls() -> None:
    html = _model_html()
    assert 'id="replayUnitFilterHost"' in html
    assert 'id="replayUnitFilterClearBtn"' in html
    assert "Reset Unit" in html


def test_model_html_tracks_replay_unit_filter_state() -> None:
    html = _model_html()
    assert "unitFilter: \"__all__\"" in html
    assert "knownUnits: []" in html
    assert "renderReplayUnitFilter(unitOptions);" in html


def test_model_html_includes_head_diagnostics_controls() -> None:
    html = _model_html()
    assert 'id="replayHeadTopKInput"' in html
    assert 'id="replayHeadDiagnosticsHost"' in html
    assert "Head Diagnostics (per step)" in html


def test_model_html_includes_step_navigation_controls() -> None:
    html = _model_html()
    assert 'id="replayPrevStepBtn"' in html
    assert 'id="replayNextStepBtn"' in html
    assert "Prev Step" in html
    assert "Next Step" in html
    assert 'id="replayStepNavFeedback"' in html


def test_model_html_replay_next_prev_uses_regular_navigation_without_filter() -> None:
    html = _model_html()
    assert 'if (String(replayState.unitFilter || "__all__") === "__all__") {' in html
    assert "const nextStep = Math.max(0, Math.min(maxStep, current + direction));" in html
    assert "return { targetStep: nextStep, moved: nextStep !== current };" in html


def test_model_html_replay_next_prev_uses_unit_aware_navigation_with_filter() -> None:
    html = _model_html()
    assert "function replayStepHasRelevantUnitActivity(stepRow, unitId)" in html
    assert 'if (actionId && actionId.indexOf(":" + wanted + ":") >= 0) return true;' in html
    assert "if (actionUnit && actionUnit === wanted) return true;" in html
    assert "if (actionActorUnit && actionActorUnit === wanted) return true;" in html
    assert "if (actionTargetUnit && actionTargetUnit === wanted) return true;" in html
    assert "if (containsWantedUnit(stepRow.unit_events)) return true;" in html
    assert "if (containsWantedUnit(stepRow.events)) return true;" in html
    assert "if (containsWantedUnit(stepRow.runtime_events)) return true;" in html
    assert "if (containsWantedUnit(stepRow.event_unit_ids)) return true;" in html
    assert "if (containsWantedUnit(stepRow.affected_unit_ids)) return true;" in html
    assert "while (idx >= 0 && idx <= maxStep) {" in html
    assert "idx += direction;" in html
    assert "return false;" in html
    assert "No next step for selected unit." in html
    assert "No previous step for selected unit." in html


def test_model_html_replay_play_and_keyboard_reuse_unit_aware_step_navigation() -> None:
    html = _model_html()
    assert "if (prevStepBtn) prevStepBtn.onclick = () => moveReplayStep(-1);" in html
    assert "if (nextStepBtn) nextStepBtn.onclick = () => moveReplayStep(1);" in html
    assert "const moved = moveReplayStep(1);" in html
    assert 'if (ev.key === "ArrowRight") {' in html
    assert "moveReplayStep(1);" in html
    assert 'else if (ev.key === "ArrowLeft") {' in html
    assert "moveReplayStep(-1);" in html


def test_non_contiguous_unit_steps_expected_navigation_fixture() -> None:
    transitions = [
        {"step": 0, "unit_id": ""},
        {"step": 1, "unit_id": "u-red-1"},
        {"step": 2, "unit_id": ""},
        {"step": 3, "unit_id": ""},
        {"step": 4, "unit_id": "u-red-1"},
        {"step": 5, "unit_id": ""},
        {"step": 6, "unit_id": "u-red-1"},
    ]
    relevant = [idx for idx, row in enumerate(transitions) if row.get("unit_id") == "u-red-1"]
    assert relevant == [1, 4, 6]
    # From a non-relevant current step, navigation should jump directly to the next relevant step.
    assert min(idx for idx in relevant if idx > 2) == 4
    # Previous should jump back to the latest relevant step before current.
    assert max(idx for idx in relevant if idx < 5) == 4


def test_replay_step_resolution_skips_non_relevant_steps_for_selected_unit() -> None:
    transitions = [
        {"step": 0, "action_id": "MOVE:US_1:4:4", "unit_id": "US_1", "units": [{"unit_id": "IT_1"}]},
        {"step": 1, "action_id": "MOVE:IT_1:5:4", "unit_id": "IT_1", "units": [{"unit_id": "IT_1"}]},
        {"step": 2, "action_id": "MOVE:US_2:3:4", "unit_id": "US_2", "units": [{"unit_id": "IT_1"}]},
        {"step": 3, "action_id": "FIRE:US_3:IT_1", "target_unit_id": "IT_1", "units": [{"unit_id": "IT_1"}]},
        {"step": 4, "action_id": "MOVE:US_4:6:1", "unit_id": "US_4", "units": [{"unit_id": "IT_1"}]},
        {"step": 5, "action_id": "MOVE:IT_1:6:4", "unit_id": "IT_1", "units": [{"unit_id": "IT_1"}]},
    ]
    # Start in a non-relevant step for IT_1; Next should jump to step 3, not step 2.
    assert _resolve_replay_step_delta(transitions, current_step=1, delta=1, unit_filter="IT_1") == 3
    # From another non-relevant step, Prev should jump back to step 3.
    assert _resolve_replay_step_delta(transitions, current_step=4, delta=-1, unit_filter="IT_1") == 3
    # Unfiltered navigation remains contiguous.
    assert _resolve_replay_step_delta(transitions, current_step=1, delta=1, unit_filter="__all__") == 2


def test_model_html_tracks_head_diagnostics_state_and_render() -> None:
    html = _model_html()
    assert "headTopK: 5" in html
    assert "function renderReplayHeadDiagnostics(stepRow)" in html
    assert "headSummaryPolicy(stepRow)" in html
    assert "telemetry_coverage_status" in html
    assert "coverageBadge(stepRow, headName)" in html


def test_model_html_includes_decision_influence_panel_and_renderer() -> None:
    html = _model_html()
    assert "Decision Influence" in html
    assert 'id="replayDecisionInfluenceHost"' in html
    assert "function renderDecisionInfluence(stepRow, transitions)" in html
    assert "step_coverage=" in html
    assert "Episode aggregation" in html
    assert "mcts override rate" in html
    assert "policy-dominant" in html
    assert "objective-dominant" in html
    assert "mcts-dominant" in html
    assert "objective_min_dist_before" in html
    assert "objective_min_dist_after" in html
    assert "Why this action vs VP" in html
    assert "delta_score (chosen - vp_best)" in html
    assert "No candidate breakdown available (legacy run or missing telemetry)." in html


def test_model_html_separates_train_and_eval_head_diagnostics_panels() -> None:
    html = _model_html()
    assert "Train Head Diagnostics" in html
    assert "Eval Head Diagnostics" in html
    assert "Train Detail" in html
    assert 'id="trainHeadDiagnosticsRoot"' in html
    assert 'id="headDiagnosticsRoot"' in html
    assert 'id="tabTrainDetailBtn"' in html
    assert 'id="tabTrainHeadDiagnosticsBtn"' in html


def test_model_html_binds_head_diagnostics_to_distinct_sources() -> None:
    html = _model_html()
    assert "function renderTrainHeadDiagnostics()" in html
    assert "const m = (selectedTrainSummary && typeof selectedTrainSummary === \"object\") ? selectedTrainSummary : {};" in html
    assert "const h = (r && r.head_diagnostics_eval) || {};" in html
    assert "status=' + esc(status) + ' | rows_with_head_diag=" in html
    assert "Coverage breakdown by head" in html
    assert "Coverage state breakdown (heads)" in html
    assert "Frequent partial/none reasons" in html
    assert "Decision Influence quick access" in html
    assert "headDiagOpenReplayBtn" in html
    assert "Ownership source coverage: override_signal_rows=" in html


def test_model_html_restricts_eval_head_diagnostics_to_eval_section() -> None:
    html = _model_html()
    assert '<button id="tabHeadDiagnosticsBtn" class="tab-btn" data-section="eval">Eval Head Diagnostics</button>' in html
    assert '["tabTrainDetailBtn", "tabTrainHeadDiagnosticsBtn", "tabObjectiveRewardConfigBtn", "tabMuzeroVpsBtn", "tabHeadDiagnosticsBtn", "tabUnifiedBtn", "tabEvalDecisionsBtn", "tabReplayBtn", "tabOverviewBtn"].forEach(id => {' in html


def test_model_html_forces_valid_tab_when_switching_sections() -> None:
    html = _model_html()
    assert 'if (section === "train" && activeTab !== "train-detail" && activeTab !== "train-head-diagnostics" && activeTab !== "objective-reward-config") switchTab("train-detail");' in html
    assert 'if (section === "eval" && activeTab !== "vps" && activeTab !== "head-diagnostics" && activeTab !== "unified" && activeTab !== "eval-decisions" && activeTab !== "replay") switchTab("vps");' in html
    assert 'if (section === "meta" && activeTab !== "overview") switchTab("overview");' in html


def test_model_html_uses_neutral_eval_labels_and_default_tab() -> None:
    html = _model_html()
    assert "VP Summary" in html
    assert "Match Replay" in html
    assert "MuZero Match Replay" not in html
    assert "MuZero VPs" not in html
    assert 'switchTab("vps");' in html


def test_catalog_html_prefers_efficientzero_v2_engine_by_default() -> None:
    from mlops.reporting.viewer import _catalog_html

    html = _catalog_html()
    assert 'const preferred = engines.find(e => String((e && e.engine) || "") === "efficientzero_v2");' in html


def test_model_html_includes_objective_reward_config_tab_and_panel() -> None:
    html = _model_html()
    assert 'id="tabObjectiveRewardConfigBtn"' in html
    assert "Objective/Reward Config" in html
    assert 'id="tabObjectiveRewardConfig"' in html
    assert 'id="objectiveRewardConfigRoot"' in html


def test_model_html_renders_objective_reward_config_with_source_precedence() -> None:
    html = _model_html()
    assert "function renderObjectiveRewardConfig()" in html
    assert "objectiveRewardDefaults" in html
    assert "Source precedence: <b>run_config</b> -> <b>fallback_default</b> -> <b>legacy_missing (N/A)</b>." in html
    assert "Objective Head Runtime" in html
    assert "Reward Shaping" in html
    assert "Objective Opportunity & Thresholds" in html
    assert "objective_loss_weight" in html
    assert "objective_target_mode" in html
    assert "objective_pos_weight" in html
    assert "objective_opportunity_max_dist" in html
    assert "objective_opportunity_near_vp_max_dist" in html
    assert "objective_progress_positive_threshold" in html
    assert "objective_progress_bonus_per_hex" in html
    assert "objective_no_progress_penalty" in html
    assert "objective_no_progress_attack_penalty" in html
    assert "terminal_scale" in html
    assert "damage_weight" in html
    assert "kill_weight" in html
    assert "vp_action_bonus" in html
    assert "capture_bonus" in html
    assert "vp_capture_bonus_per_hex" in html
    assert "vp_net_gain_bonus" in html
    assert "vp_net_loss_penalty" in html
    assert "reaction_fire_miss_penalty" in html
    assert "idle_penalty" in html
    assert "idle_with_options_multiplier" in html
    assert "terminal_win_bonus" in html
    assert "terminal_draw_bonus" in html
    assert "terminal_loss_penalty" in html
    assert "assault_advantage_legal_count_threshold" in html
    assert "decision_flip_legal_count_tolerance" in html
    assert "objective_reward_config" in html
    assert "Config preflight warnings:" in html


def test_model_html_uses_responsive_two_column_objective_reward_layout() -> None:
    html = _model_html()
    assert ".objective-reward-grid {" in html
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in html
    assert "grid-auto-flow:dense;" in html
    assert ".objective-reward-section--wide {" in html
    assert "grid-column: 1 / -1;" in html
    assert "@media (max-width: 1100px) {" in html
    assert ".objective-reward-grid { grid-template-columns: minmax(0, 1fr); }" in html
    assert ".objective-reward-section--wide { grid-column:auto; }" in html
    assert "class='objective-reward-grid'" in html
    assert "objective-reward-section objective-reward-section--wide" in html
    assert "class='objective-reward-table-wrap'" in html
    assert "overflow-x:auto;" in html


def test_viewer_server_train_summary_reads_runs_roots_with_legacy_fallback() -> None:
    from pathlib import Path

    source = Path("mlops/reporting/viewer.py").read_text(encoding="utf-8")
    assert 'catalog_payload.get("runs_roots", [])' in source
    assert 'catalog_payload.get("runs_root", "runs_curriculum")' in source


def test_model_html_eval_head_diagnostics_shows_interpretable_intentions_and_coverage() -> None:
    html = _model_html()
    assert "Top-k policy actions (eval_decisions_top)" in html
    assert "MCTS decision ownership by side" in html
    assert "Execution mismatch by side (legacy compatibility metric)" in html
    assert "no eval telemetry for this head" in html
    assert "Policy intent is unavailable for current filters (N/A)." in html
    assert "N/A" in html
    assert "Row/step telemetry inspector" in html
    assert "headDiagRowSelect" in html
    assert "Inspect row-level telemetry gaps here; use replay tab for per-step diagnostics." in html
    assert "eval_vp_capture_opportunity_steps (sum objective_had_opportunity)" in html
    assert "eval_vp_immediate_capture_opportunity_steps (capture legal now)" in html
    assert "vp_capture_opportunities (objective_had_opportunity)" in html
    assert "vp_immediate_capture_opportunities (legal capture window)" in html


def test_model_html_eval_head_diagnostics_uses_eval_replay_sources_only() -> None:
    html = _model_html()
    assert "eval_decisions_top" in html
    assert "decision_ownership_by_side" in html
    assert "execution_mismatch_by_side" in html
    assert "const tops = Array.isArray(r.eval_decisions_top) ? r.eval_decisions_top : [];" in html


def test_model_html_does_not_embed_legacy_objective_distance_gap_reason() -> None:
    html = _model_html()
    assert "objective_distance_not_in_eval_pipeline" not in html


def test_model_html_head_diagnostics_heuristics_are_in_english() -> None:
    html = _model_html()
    assert "high exploration / open decision" in html
    assert "high risk for the active side" in html
    assert "no clear VP objective opportunity" in html
    assert "strong latent state change" in html
    assert "MCTS prioritizes a dominant line" in html
    assert "exploración alta / decisión abierta" not in html
    assert "riesgo alto para el bando activo" not in html
    assert "sin oportunidad clara de objetivo VP" not in html
    assert "cambio fuerte de estado latente" not in html
    assert "MCTS prioriza una línea dominante" not in html
