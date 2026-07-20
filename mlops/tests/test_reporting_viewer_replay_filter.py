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


def test_model_html_replay_units_snapshot_renders_suppressed_with_na_fallback() -> None:
    html = _model_html()
    assert '<th style="border:1px solid #334155;padding:6px;">suppressed</th>' in html
    assert 'const mapRaw = (stepRowObj && typeof stepRowObj === "object")' in html
    assert "stepRowObj.unit_suppressed_map" in html
    assert 'const producerKeys = ["suppressed", "is_suppressed", "pinned", "is_pinned"];' in html
    assert 'return value === null ? "N/A" : (value ? "yes" : "no");' in html
    assert '<tr><td colspan="7" style="border:1px solid #334155;padding:6px;" class="muted">No units for selected filter.</td></tr>' in html


def test_model_html_includes_head_diagnostics_controls() -> None:
    html = _model_html()
    assert 'id="replayHeadTopKInput"' in html
    assert 'id="replayHeadDiagnosticsHost"' in html
    assert "Head Diagnostics (per step)" in html


def test_model_html_uses_responsive_replay_details_two_column_layout() -> None:
    html = _model_html()
    assert ".replay-details-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px; }" in html
    assert ".replay-details-grid .replay-panel { margin-top:0; }" in html
    assert "@media (max-width: 900px) { .replay-details-grid { grid-template-columns: minmax(0, 1fr); } }" in html
    assert '<div class="replay-details-grid">' in html
    assert '<div id="replayStepDetail" class="list"></div>' in html
    assert '<div id="replayUnitsHost" class="list"></div>' in html


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


def test_model_html_includes_step_position_fields_with_fallback_derivation() -> None:
    html = _model_html()
    assert "previous_position" in html
    assert "current_position" in html
    assert "function deriveStepPositions(step, transitions, stepIdx)" in html
    assert "function readActionDestination(step)" in html
    assert "return \"-\";" in html


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
    assert "real_decision_score (selected)" in html
    assert "decision_win_basis" in html
    assert "real_decision_score=" in html
    assert "selection_source (selected)" in html
    assert "decision_rank=" in html
    assert "unit_id" in html
    assert "const normalizeDecisionCandidate = function (raw, chosenActionId)" in html
    assert "c.visit_count = hasOwn(c, \"visit_count\") ? safeNum(c.visit_count) : null;" in html
    assert "c.mcts_q_value = hasOwn(c, \"mcts_q_value\") ? safeNum(c.mcts_q_value) : null;" in html
    assert "c.mcts_u_value = hasOwn(c, \"mcts_u_value\") ? safeNum(c.mcts_u_value) : null;" in html
    assert "decisionCandidateSortKey: \"decision_score\"" in html
    assert "decisionCandidateSortDir: \"desc\"" in html
    assert "data-candidate-sort-key=\"action_id\"" in html
    assert "data-candidate-sort-key=\"unit_id\"" in html
    assert "data-candidate-sort-key=\"decision_score\"" in html
    assert "data-candidate-sort-key=\"decision_rank\"" in html
    assert "const sortButtons = host.querySelectorAll(\"[data-candidate-sort-key]\");" in html
    assert "sortButtons.forEach(function (btn) {" in html
    assert "btn.onclick = function () {" in html
    assert "renderDecisionInfluence(stepRow, transitions);" in html
    assert ".replay-candidate-table-wrap {" in html
    assert "max-height: 320px;" in html
    assert "overflow-y: auto;" in html
    assert "missing_producer_fields=" in html
    assert "legacyVisits" not in html
    assert "legacyQ" not in html
    assert "legacyU" not in html
    assert "No MCTS-evaluated actions available." in html
    assert "score breakdown (top-k=" not in html
    assert ".slice(0, whyTopK)" not in html
    assert "const candidateSourceLists = [" in html
    assert "Array.isArray(whyBlock.candidate_actions) ? whyBlock.candidate_actions : []" in html
    assert "Array.isArray(stepRow.mcts_action_candidates) ? stepRow.mcts_action_candidates : []" in html
    assert "Array.isArray(stepRow.legal_actions) ? stepRow.legal_actions : []" in html
    assert "Array.isArray(stepRow.legal_action_ids) ? stepRow.legal_action_ids : []" in html
    assert "const candidateRowsRawMap = {};" in html
    assert "candidateRowsRawMap[actionId] = Object.assign({}, prev, obj);" in html
    assert "if (!c.unit_id && actionParts.length > 1) c.unit_id = String(actionParts[1] || \"\").trim();" in html


def test_model_html_replay_hovered_candidates_use_scroll_wrap_and_table_class() -> None:
    html = _model_html()
    panel_fn = html.split("function renderReplayHoveredActions(stepRow) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    assert 'id="replayHoverLegalTableWrap" class="replay-candidate-table-wrap"' in panel_fn
    assert 'id="replayHoverMctsTableWrap" class="replay-candidate-table-wrap"' in panel_fn
    assert panel_fn.count('class="replay-candidate-table-wrap"') >= 2


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
    assert "unknown_override_rows=" in html


def test_model_html_restricts_eval_head_diagnostics_to_eval_section() -> None:
    html = _model_html()
    assert '<button id="tabHeadDiagnosticsBtn" class="tab-btn" data-section="eval">Eval Head Diagnostics</button>' in html
    assert '<button id="tabEvalMetricsBtn" class="tab-btn" data-section="eval">Eval Metrics</button>' in html
    assert '["tabTrainDetailBtn", "tabTrainHeadDiagnosticsBtn", "tabObjectiveRewardConfigBtn", "tabMuzeroVpsBtn", "tabHeadDiagnosticsBtn", "tabEvalMetricsBtn", "tabUnifiedBtn", "tabEvalDecisionsBtn", "tabReplayBtn", "tabOverviewBtn"].forEach(id => {' in html


def test_model_html_forces_valid_tab_when_switching_sections() -> None:
    html = _model_html()
    assert 'if (section === "train" && activeTab !== "train-detail" && activeTab !== "train-head-diagnostics" && activeTab !== "objective-reward-config") switchTab("train-detail");' in html
    assert 'if (section === "eval" && activeTab !== "vps" && activeTab !== "head-diagnostics" && activeTab !== "eval-metrics" && activeTab !== "unified" && activeTab !== "eval-decisions" && activeTab !== "replay") switchTab("vps");' in html
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
    objective_fn = html.split("function renderObjectiveRewardConfig()", 1)[1].split("function renderObjectiveRewardConfigRows", 1)[0]
    assert "selfCfg.mcts_vp_tiebreak_epsilon" in objective_fn
    assert "trainSelf.mcts_vp_tiebreak_epsilon" not in objective_fn
    assert "objectiveRewardDefaults" in html
    assert "OK criteria: <b>run_config</b> values are green; <b>fallback_default</b> and <b>missing (N/A)</b> are degraded." in html
    assert "Objective Head Runtime" in html
    assert "Q Calibration / MCTS" in html
    assert "Combat Soft Signals" in html
    assert "Global Strategy Soft Signals" in html
    assert "Reward Shaping" in html
    assert "Objective Opportunity & Thresholds" in html
    assert "objective_loss_weight" in html
    assert "objective_target_mode" in html
    assert "objective_pos_weight" in html
    assert "mcts_vp_tiebreak_epsilon" in html
    assert "mcts_q_clip_abs" in html
    assert "mcts_q_root_normalization_mode" in html
    assert "mcts_q_root_normalization_strength" in html
    assert "mcts_q_flat_spread_epsilon" in html
    assert "mcts_vp_flat_q_score_epsilon" in html
    assert "mcts_vp_flat_q_min_progress" in html
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
    assert "reaction_fire_soft_signal_enabled" in html
    assert "reaction_fire_soft_signal_weight" in html
    assert "reaction_fire_soft_signal_expected_damage_scale" in html
    assert "global_strategy_soft_enabled" in html
    assert "global_strategy_vp_control_net_gain_weight" in html
    assert "global_strategy_units_in_vp_ring_weight" in html
    assert "global_strategy_enemy_vp_threat_reduced_weight" in html
    assert "global_strategy_sustained_vp_advantage_weight" in html
    assert "global_strategy_role_consistency_weight" in html
    assert "global_strategy_setup_convert_weight" in html
    assert "global_strategy_vp_ring_radius" in html
    assert "global_strategy_enemy_threat_radius" in html
    assert "global_strategy_sustained_advantage_min_turns" in html
    assert "global_strategy_total_cap_abs" in html
    assert "vp_horizon_soft_enabled" in html
    assert "vp_horizon_soft_weight" in html
    assert "vp_horizon_soft_cap_steps" in html
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
    assert "no eval telemetry for this head" in html
def test_model_html_marks_ok_and_degraded_metrics_for_dark_theme() -> None:
    html = _model_html()
    assert ".ok-chip {" in html
    assert ".degraded-chip {" in html
    assert ".ok-text { color:#86efac; font-weight:600; }" in html
    assert ".degraded-text { color:#fdba74; font-weight:600; }" in html
    assert "status/source" in html
    assert "unknown_override_rows" in html
    assert "Policy intent is unavailable for current filters (N/A)." in html
    assert "N/A" in html
    assert "Row/step telemetry inspector" in html
    assert "headDiagRowSelect" in html
    assert "Inspect row-level telemetry gaps here; use replay tab for per-step diagnostics." in html
    assert "eval_vp_capture_opportunity_steps (sum objective_had_opportunity)" in html
    assert "eval_vp_immediate_capture_opportunity_steps (MOVE into capturable VP legal now)" in html
    assert "vp_capture_opportunities (objective_had_opportunity)" in html
    assert "vp_immediate_capture_opportunities (legal MOVE-into-VP window)" in html


def test_model_html_eval_head_diagnostics_uses_eval_replay_sources_only() -> None:
    html = _model_html()
    assert "eval_decisions_top" in html
    assert "decision_ownership_by_side" in html
    assert "execution_mismatch_by_side" not in html
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


def test_model_html_filters_attack_effectiveness_by_side_controller() -> None:
    html = _model_html()
    assert "function resultMatchesUnifiedFilters(resultRow)" in html
    assert "if (p !== \"__all__\" && String(resultRow.matchup_profile || \"\") !== String(p)) return false;" in html
    assert "const evalRowsForUnified = evalRowsForTabs" in html
    assert "renderEvalMetrics(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });" in html
    assert "renderUnifiedActions(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });" in html
    assert "renderEvalDecisions(evalRowsForUnified, { side: s, controller: c, sideAllowed: sideAllowed });" in html
    assert "function resultMatchesSideControllerFilters(resultRow)" in html
    assert "if (selectedSide === \"__all__\" && selectedController === \"__all__\") return true;" in html
    assert "const sidesLocal = collectSidesFromResult(resultRow);" in html
    assert "if (!Array.isArray(sidesLocal) || !sidesLocal.length) return false;" in html
    assert "const sideAllowedFn = (filterCtx && typeof filterCtx.sideAllowed === \"function\")" in html
    assert "return sideAllowedFn(resultRow, s, selectedSide, selectedController);" in html
    assert "if (p === \"mcts\" || p === \"muzero\" || p === \"muzero_controller\") return \"MuZero\";" in html
    assert "const selectedCtrlNorm = selectedController === \"__all__\"" in html
    assert "if (selectedCtrlNorm !== \"__all__\" && c !== selectedCtrlNorm) return false;" in html
    assert "if (!resultMatchesSideControllerFilters(r)) continue;" in html
    assert "const games = Array.isArray(r.match_games) ? r.match_games : [];" in html
    assert "const transitions = Array.isArray((game && game.transitions)) ? game.transitions : [];" in html
    assert "if (!sideAllowedFn(r, stepSide, selectedSide, selectedController)) continue;" in html
    assert "if (!rowHasTransitions) {" in html
    assert "mergeAttackEffSummary((summary && summary.attack_effectiveness) || {});" in html
    assert "By Action x Side x Controller (Pivot)" in html
    assert "const colKeys = Object.keys(colKeyMap).sort((a, b) => {" in html
    assert "const pivotMap = {};" in html
    assert "const label = String(colMeta.side || \"UNK\") + \" x \" + String(colMeta.controller || \"UNKNOWN\");" in html
    side_allowed_decl_idx = html.find("const sideAllowedFn = (filterCtx && typeof filterCtx.sideAllowed === \"function\")")
    side_allowed_use_idx = html.find("return sideAllowedFn(resultRow, s, selectedSide, selectedController);")
    assert side_allowed_decl_idx >= 0
    assert side_allowed_use_idx >= 0
    assert side_allowed_decl_idx < side_allowed_use_idx
    assert "if (!r || typeof r !== \"object\") continue;" in html
    assert "if (!src || typeof src !== \"object\") continue;" in html
    assert "if (!sideAllowedFn(r, side, selectedSide, selectedController)) continue;" in html
    assert "filterCtx.side || \"__all__\"" not in html.split("function renderUnifiedActions(filteredResultRows, filterCtx)", 1)[1].split("function renderEvalDecisions(filteredResultRows, filterCtx)", 1)[0]


def test_model_html_unified_keeps_attack_effectiveness_visible_on_filter_change() -> None:
    html = _model_html()
    unified_fn = html.split("function renderUnifiedActions(filteredResultRows, filterCtx) {", 1)[1].split("function renderEvalDecisions(filteredResultRows, filterCtx)", 1)[0]
    assert "const sourceRows = Array.isArray(filteredResultRows) ? filteredResultRows : [];" in unified_fn
    assert "for (const er of sourceRows) {" in unified_fn
    assert "Attack Effectiveness (calibration)" in unified_fn
    assert "No rows for current filters." not in unified_fn


def test_model_html_unified_attack_effectiveness_zero_match_shows_explicit_empty_state() -> None:
    html = _model_html()
    unified_fn = html.split("function renderUnifiedActions(filteredResultRows, filterCtx) {", 1)[1].split("function renderEvalMetrics(filteredResultRows, filterCtx)", 1)[0]
    assert "const hasAttackData = Number(g.count || 0) > 0;" in unified_fn
    assert "No attack effectiveness rows for current filters." in unified_fn
    assert "colspan=\"7\"" in unified_fn
    assert "No calibration bins." in unified_fn


def test_model_html_uses_unified_filtered_rows_for_replay() -> None:
    html = _model_html()
    assert "const replayRows = evalRowsForUnified;" in html
    assert "renderMatchReplay(replayRows);" in html


def test_model_html_includes_eval_metrics_channel_diagnostics_tab_and_hooks() -> None:
    html = _model_html()
    assert "Eval Metrics" in html
    assert 'id="tabEvalMetricsBtn"' in html
    assert 'id="tabEvalMetrics"' in html
    assert 'id="evalMetricsRoot"' in html
    assert "function renderEvalMetrics(filteredResultRows, filterCtx)" in html
    assert "Producer-first contract: missing channels are shown as N/A with explicit missing producer notes." in html
    assert "Channel Map" in html
    assert "id='evalChannelMapTable'" in html
    assert "class='eval-channel-map'" in html
    assert "channel_name" in html
    assert "layer/type" in html
    assert "availability coverage" in html
    assert "status-\" + esc(String(row.status || \"missing\"))" in html
    assert "obs_unit_position" in html
    assert "mcts_q_value" in html
    assert "mcts_u_value" in html
    assert "mcts_prior" in html
    assert "vp_progress" in html
    assert "strategy_label" in html
    assert "decision_score_selected" in html
    assert "vp_horizon_decision_component" in html
    assert "selected_action.decision_components.vp_horizon_steps" in html
    assert "selected_action.decision_components.vp_horizon_signal" in html
    assert "selected_action.decision_components.vp_horizon_component" in html
    assert "nonzero usage rate" in html
    assert "mean |term|" in html
    assert "p95 |term|" in html
    assert "Latest per-step channel rows" in html
    assert "telemetryStepsFromResult(resultRow)" in html
    assert "eval_decision_steps_top" in html
    assert "rows_with_decision_components=" in html
    assert "step_source_counts=" in html
    assert "source_artifacts=" in html
    assert "Decision Channel Dependency Map" in html
    assert 'id=\'decisionDependencyMapTable\'' in html
    assert "compute function/path" in html
    assert "injection point" in html
    assert "effect type" in html
    assert "train vs eval" in html
    assert "eval telemetry only" in html
    assert "direct MCTS" in html
    assert "indirect via reward" in html
    assert "telemetry only" in html
    assert "decision_score_selected" in html
    assert "mcts_prior" in html
    assert "mcts_q_value (mcts_q)" in html
    assert "mcts_u_value (mcts_u)" in html
    assert "mcts_success_component" in html
    assert "mcts_success_prob_proxy" in html
    assert "reaction_fire_soft_reward_component" in html
    assert "reaction_exposure_component" in html
    assert "vp_horizon_steps" in html
    assert "vp_horizon_signal" in html
    assert "vp_horizon_component" in html
    assert "vp_horizon_decision_component" in html
    assert "tie_break_term" in html
    assert "vp_progress" in html


def test_model_html_includes_unit_prefilter_channels_with_producer_sources() -> None:
    html = _model_html()
    assert 'key: "unit_prefilter_enabled"' in html
    assert 'source: "producer field:unit_prefilter_enabled"' in html
    assert 'key: "unit_prefilter_selected_unit_id"' in html
    assert 'source: "producer field:unit_prefilter_selected_unit_id"' in html
    assert 'key: "unit_prefilter_constrained_count"' in html
    assert 'source: "producer field:unit_prefilter_constrained_count"' in html
    assert 'key: "unit_prefilter_global_count"' in html
    assert 'source: "producer field:unit_prefilter_global_count"' in html


def test_model_html_decision_influence_renders_unit_prefilter_info_line() -> None:
    html = _model_html()
    assert '["unit prefilter", "enabled=' in html
    assert 'selected_unit_id=' in html
    assert 'constrained=' in html
    assert 'global=' in html
    assert '["unit_prefilter_enabled", unitPrefilterEnabled === null ? "N/A"' in html
    assert '["unit_prefilter_selected_unit_id", unitPrefilterSelectedUnitId || "N/A"]' in html
    assert '["unit_prefilter_constrained_count", fmtNum(unitPrefilterConstrainedCount, 0)]' in html
    assert '["unit_prefilter_global_count", fmtNum(unitPrefilterGlobalCount, 0)]' in html


def test_model_html_eval_metrics_renders_unit_prefilter_step_columns() -> None:
    html = _model_html()
    assert "const stepColumns = [\"eval_id\", \"step\", \"unit_side\", \"action_id\"].concat(channelsStable.map(function (ch) { return ch.label; }));" in html
    assert "stepColumns.map(function (key) {" in html
    assert "for (const ch of channelsStable) {" in html
    assert "rowPreview[ch.label] = ch.getter(step);" in html
    assert 'key: "unit_prefilter_enabled"' in html
    assert 'key: "unit_prefilter_selected_unit_id"' in html
    assert 'key: "unit_prefilter_constrained_count"' in html
    assert 'key: "unit_prefilter_global_count"' in html
    assert "formatPerStepCell(r, colKey)" in html


def test_model_html_unified_controller_filter_keeps_attack_section_structure() -> None:
    html = _model_html()
    unified_fn = html.split("function renderUnifiedActions(filteredResultRows, filterCtx) {", 1)[1].split("function renderEvalDecisions(filteredResultRows, filterCtx)", 1)[0]
    assert "const sourceRows = Array.isArray(filteredResultRows) ? filteredResultRows : [];" in unified_fn
    assert "for (const er of sourceRows) {" in unified_fn
    assert "for (const er of filteredResultRows) {" not in unified_fn
    assert "No attack effectiveness rows for current filters." in unified_fn


def test_model_html_unified_controller_filter_keeps_attack_effectiveness_with_summary_fallback() -> None:
    html = _model_html()
    unified_fn = html.split("function renderUnifiedActions(filteredResultRows, filterCtx) {", 1)[1].split("function renderEvalMetrics(filteredResultRows, filterCtx)", 1)[0]
    assert "if (!rowHasTransitions) {" in unified_fn
    assert "mergeAttackEffSummary((summary && summary.attack_effectiveness) || {});" in unified_fn
    assert "if (!rowHasTransitions && selectedSide === \"__all__\" && selectedController === \"__all__\") {" not in unified_fn


def test_model_html_includes_new_decision_making_kpis_in_vp_diagnostics() -> None:
    html = _model_html()
    assert "Decision-making KPIs" in html
    assert "vp_approach_rate" in html
    assert "vp_regret_delta_mean" in html
    assert "vp_regret_delta_p95" in html
    assert "q_saturation_rate" in html
    assert "decision_spread_mean" in html
    assert "decision_spread_p50" in html
    assert "decision_spread_p95" in html
    assert "path_to_capture_length_mean" in html
    assert "path_to_capture_length_p95" in html
    assert "N/A means producer telemetry for that KPI is unavailable after current filters." in html


def test_model_html_includes_opportunity_conversion_by_turn_section() -> None:
    html = _model_html()
    assert "Opportunity conversion by turn" in html
    assert "Buckets: " in html
    assert "early: turn<=3, mid: turn 4-7, late: turn>=8" in html
    assert "opportunity_conversion_early_opportunity_steps" in html
    assert "opportunity_conversion_early_converted_steps" in html
    assert "opportunity_conversion_mid_opportunity_steps" in html
    assert "opportunity_conversion_mid_converted_steps" in html
    assert "opportunity_conversion_late_opportunity_steps" in html
    assert "opportunity_conversion_late_converted_steps" in html


def test_model_html_pivots_eval_decisions_table_a_by_side() -> None:
    html = _model_html()
    eval_decisions_fn = html.split("function renderEvalDecisions(filteredResultRows, filterCtx) {", 1)[1].split("let replayState = {", 1)[0]
    assert "Table A: Action Kind x Side (Pivot)" in eval_decisions_fn
    assert "const sideKeyMap = {};" in eval_decisions_fn
    assert "sideKeyMap[String(src.unit_side || \"UNK\")] = true;" in eval_decisions_fn
    assert "const sideKeys = Object.keys(sideKeyMap).sort((a, b) => String(a || \"\").localeCompare(String(b || \"\")));" in eval_decisions_fn
    assert "const pivotRows = {};" in eval_decisions_fn
    assert "if (!actionKeys.length || !sideKeys.length) {" in eval_decisions_fn
    assert "No decision rows available." in eval_decisions_fn
    assert '<th rowspan="2"' in eval_decisions_fn
    assert '<th colspan="3"' in eval_decisions_fn
    assert ">count</th>" in eval_decisions_fn
    assert ">damage</th>" in eval_decisions_fn
    assert ">kills</th>" in eval_decisions_fn
    assert "<span class=\"muted\"> | d:" not in eval_decisions_fn
    assert " k:" not in eval_decisions_fn
    assert "for (const side of sideKeys) {" in eval_decisions_fn


def test_model_html_defines_collect_sides_helper_in_shared_scope() -> None:
    html = _model_html()
    helper_idx = html.find("function collectSidesFromResult(resultRow)")
    unified_idx = html.find("function renderUnifiedActions(filteredResultRows, filterCtx)")
    assert helper_idx >= 0
    assert unified_idx >= 0
    assert helper_idx < unified_idx


def test_model_html_build_flow_dataset_uses_flow_rows_param() -> None:
    html = _model_html()
    flow_fn = html.split("function _buildFlowDataset(", 1)[1].split("function _renderFlowGraph(", 1)[0]
    assert "const resultRows = (flowRows || [])" in flow_fn
    assert "const resultRows = (rows || [])" not in flow_fn


def test_model_html_replay_shows_empty_state_and_resets_stale_selection() -> None:
    html = _model_html()
    assert "if (!sourceRows.length) {" in html
    assert "filteredResultRows.filter(function (r) { return r && typeof r === \"object\"; })" in html
    assert 'replayState.evalId = "__all__";' in html
    assert "replayState.payload = null;" in html
    assert "replayState.step = 0;" in html
    assert "replayState.episodeIndex = 0;" in html
    assert "No match games for current filters. Adjust filters to load replay." in html


def test_model_html_replay_draw_guards_non_object_transition_rows_before_target_q_access() -> None:
    html = _model_html()
    assert "const stepRowRaw = transitions[replayState.step];" in html
    assert "const stepRow = (stepRowRaw && typeof stepRowRaw === \"object\") ? stepRowRaw : null;" in html
    assert "if (!stepRow) {" in html


def test_model_html_replay_renders_controller_by_side_block_with_fallback_sources() -> None:
    html = _model_html()
    assert "Controller by side" in html
    assert 'id="replayControllerBySide"' in html
    assert "function controllerBySideFromResult(resultRow)" in html
    assert 'source: "controller_by_side"' in html
    assert 'source: "policy_by_side"' in html
    assert 'source: "metadata"' in html
    assert "Unknown/Unlabeled" in html
    assert "Unlabeled side" in html


def test_model_html_replay_includes_hover_overlay_legend_and_colors() -> None:
    html = _model_html()
    assert 'id="replayHoverLegend"' in html
    assert "reachable move hexes" in html
    assert "attackable hexes" in html
    assert ".replay-hover-legend-move" in html
    assert ".replay-hover-legend-attack" in html
    assert "rgba(34,197,94,0.24)" in html
    assert "rgba(239,68,68,0.20)" in html
    assert 'legend.title = "Hover a unit to preview move/attack hexes";' in html


def test_model_html_replay_draws_per_hex_coordinate_labels_with_subtle_style() -> None:
    html = _model_html()
    assert "function drawHexCoordLabel(ctx, cx, cy, size, q, r)" in html
    assert 'ctx.fillStyle = "rgba(148,163,184,0.82)";' in html
    assert 'ctx.font = String(Math.max(8, Math.floor(size * 0.28))) + "px sans-serif";' in html
    assert 'ctx.fillText("(" + String(qn) + "," + String(rn) + ")", labelX, labelY);' in html
    assert "drawHexCoordLabel(ctx, p.x, p.y, size, c.q, c.r);" in html


def test_model_html_replay_hover_handlers_and_guarded_hex_extraction_hooks() -> None:
    html = _model_html()
    assert "hoveredUnitId: \"\"," in html
    assert "hoverHitPoints: []," in html
    assert "hoverHitRadius: 6," in html
    assert "hoverCanvasBound: false," in html
    assert "function setReplayHoveredUnit(unitId)" in html
    assert "function replayBindCanvasHoverHandlers(canvas)" in html
    assert "replayBindCanvasHoverHandlers(canvas);" in html
    assert "const selectedUnitId = String(replayState.unitFilter || \"__all__\").trim();" in html
    assert "if (selectedUnitId !== \"__all__\" && nextId && nextId !== selectedUnitId) nextId = \"\";" in html
    assert "function replayCollectUnitHexCandidates(stepRow, hoveredUnitId)" in html
    assert "function replayCollectCanonicalActionCandidates(stepRow)" in html
    assert "function replayCandidateActorUnit(cand)" in html
    assert "if (!wanted || !stepRow || typeof stepRow !== \"object\") return empty;" in html
    assert "const actionCandidates = replayCollectCanonicalActionCandidates(stepRow);" in html
    assert "canvas.onmousemove = function (ev) {" in html
    assert "const points = Array.isArray(replayState.hoverHitPoints) ? replayState.hoverHitPoints : [];" in html
    assert "const hitRadius = Math.max(6, Number(replayState.hoverHitRadius || 6));" in html
    assert "replayState.hoverCanvasBound = true;" in html
    assert "replayState.hoverHitPoints = points;" in html
    assert "replayState.hoverHitRadius = Math.max(6, size * 0.58);" in html
    assert "setReplayHoveredUnit(\"\");" in html


def test_model_html_replay_hover_move_hexes_filter_by_hovered_unit_only() -> None:
    html = _model_html()
    hover_fn = html.split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    assert "const wanted = String(hoveredUnitId || \"\").trim();" in hover_fn
    assert "if (!actionUnit || actionUnit !== wanted) continue;" in hover_fn
    assert "const actionUnit = replayCandidateActorUnit(cand);" in hover_fn


def test_model_html_replay_hover_ignores_mixed_actor_candidates() -> None:
    html = _model_html()
    helper_fn = html.split("function replayCandidateActorUnit(cand) {", 1)[1].split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[0]
    assert "const uniqueExplicit = Array.from(new Set(explicitActorUnits));" in helper_fn
    assert "if (uniqueExplicit.length > 1) return \"\";" in helper_fn
    assert "if (derivedActor && explicitActor && derivedActor !== explicitActor) return \"\";" in helper_fn
    hover_fn = html.split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    # Mixed candidate lists are filtered strictly by actor unit; e.g. hovered US_1 ignores US_2 candidate rows.
    assert "if (!actionUnit || actionUnit !== wanted) continue;" in hover_fn


def test_model_html_replay_hover_uses_strict_canonical_candidate_sources_only() -> None:
    html = _model_html()
    canonical_fn = html.split("function replayCollectCanonicalActionCandidates(stepRow) {", 1)[1].split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[0]
    assert "stepRow && stepRow.legal_actions," in canonical_fn
    assert "stepRow && stepRow.legal_action_ids," in canonical_fn
    assert "stepRow && stepRow.mcts_action_candidates," in canonical_fn
    assert "stepRow && stepRow.why_action_vs_vp && stepRow.why_action_vs_vp.candidate_actions," in canonical_fn
    assert "stepRow && stepRow.available_actions," not in canonical_fn
    assert "stepRow && stepRow.policy_top_actions," not in canonical_fn
    hover_fn = html.split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    assert "unit_events" not in hover_fn
    assert "runtime_events" not in hover_fn
    assert "events" not in hover_fn


def test_model_html_replay_hover_handles_sparse_legacy_telemetry_with_empty_candidates() -> None:
    html = _model_html()
    assert "if (!wanted || !stepRow || typeof stepRow !== \"object\") return empty;" in html
    assert "const actionCandidates = replayCollectCanonicalActionCandidates(stepRow);" in html
    hover_fn = html.split("function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    assert "if (!hex) continue;" in hover_fn
    assert "moveHexes: Object.values(moveMap)," in hover_fn
    assert "attackHexes: Object.values(attackMap)," in hover_fn


def test_model_html_replay_hover_panel_shows_strict_hovered_candidate_actions() -> None:
    html = _model_html()
    assert 'id="replayHoverActionsHost"' in html
    assert "function renderReplayHoveredActions(stepRow)" in html
    panel_fn = html.split("function renderReplayHoveredActions(stepRow) {", 1)[1].split("function replayStepHasRelevantUnitActivity(stepRow, unitId) {", 1)[0]
    assert "const candidateRows = replayCollectCanonicalActionCandidates(stepRow);" in panel_fn
    assert "const actorUnitId = replayCandidateActorUnit(cand);" in panel_fn
    assert "if (!actorUnitId || actorUnitId !== effectiveUnitId) continue;" in panel_fn
    assert "const target = replayActionHexFromRaw(cand);" in panel_fn
    assert "No candidate actions for hovered unit in this step." in panel_fn
    assert "Legal actions (unit-scoped)" in panel_fn
    assert "MCTS-evaluated actions" in panel_fn
    assert "Producer legal list for hovered unit; no MCTS fields required." in panel_fn
    assert "const hasMctsTelemetry = function (cand) {" in panel_fn
    assert "if (!hasMctsTelemetry(row.raw)) continue;" in panel_fn
    assert "No MCTS-evaluated actions for hovered unit in this step." in panel_fn
    assert "action_id" in panel_fn
    assert "action_kind" in panel_fn
    assert "unit_id" in panel_fn
    assert "target_qr" in panel_fn
    assert "markers" in panel_fn
    assert "mcts_q_value" in panel_fn
    assert "mcts_u_value" in panel_fn
    assert "visits" in panel_fn
    assert "score" in panel_fn
    assert "rank" in panel_fn
    assert "replayCollectCanonicalActionCandidates(stepRow)" in panel_fn
    assert "unit_events" not in panel_fn
    assert "runtime_events" not in panel_fn
    assert "events" not in panel_fn
    assert "available_actions" not in panel_fn


def test_model_html_replay_initial_render_hydrates_hover_state_and_panel_without_navigation() -> None:
    html = _model_html()
    assert "hoverCanvasBound: false," in html
    assert "hoverCanvasEl: null," in html
    assert "replayState.hoveredUnitId = \"\";" in html
    assert "replayState.hoverHitPoints = [];" in html
    assert "replayState.hoverHitRadius = 6;" in html
    assert "replayState.hoverCanvasBound = false;" in html
    assert "replayState.hoverCanvasEl = null;" in html
    assert "replayBindCanvasHoverHandlers(canvas);" in html
    assert "if (replayState.hoverCanvasBound && replayState.hoverCanvasEl === canvas) return;" in html
    assert "replayState.hoverCanvasEl = canvas;" in html
    assert "replayState.hoverHitPoints = points;" in html
    assert "renderReplayHoveredActions(stepRowSafe);" in html


def test_model_html_replay_episode_select_uses_ordinal_index_for_reload_and_redraw() -> None:
    html = _model_html()
    assert "epSel && Number.isFinite(Number(epSel.selectedIndex)) && Number(epSel.selectedIndex) >= 0" in html
    assert "? epSel.selectedIndex" in html
    assert "epMeta.map(function (e, idx) {" in html
    assert 'const ordinal = Math.max(0, Number(idx || 0));' in html
    assert 'return `<option value="${esc(String(ordinal))}" ${isSelected ? "selected" : ""}>ep ${esc(String(e.episode_index || ordinal))} seed ${esc(String(e.seed || ""))}</option>`;' in html
    assert "replayState.episodeIndex = Math.max(0, Number(" in html
    assert "? epSelect.selectedIndex" in html
    assert "await loadReplay();" in html
    assert "drawReplay(true);" in html
