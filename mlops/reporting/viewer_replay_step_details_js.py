from __future__ import annotations


def replay_step_details_helpers_js() -> str:
    return """
    function replayResolveEpisodePathFromState() {
      try {
        if (typeof replayState !== "object" || !replayState) return "";
        const metas = Array.isArray(replayState.v2EpisodesMeta) ? replayState.v2EpisodesMeta : [];
        const idx = Math.max(0, Number(replayState.episodeIndex || 0));
        const hit = metas.find(function (m) { return Number((m && m.episode_index) || -1) === idx; }) || null;
        return String((hit && hit.episode_path) || "");
      } catch (_) {
        return "";
      }
    }

    function fmtQrPair(q, r) {
      if (!Number.isFinite(Number(q)) || !Number.isFinite(Number(r))) return "-";
      return String(Number(q)) + "," + String(Number(r));
    }

    function readQrFromObject(obj, keysQ, keysR) {
      if (!obj || typeof obj !== "object") return null;
      const qKeys = Array.isArray(keysQ) ? keysQ : [];
      const rKeys = Array.isArray(keysR) ? keysR : [];
      for (let i = 0; i < Math.min(qKeys.length, rKeys.length); i += 1) {
        const q = obj[qKeys[i]];
        const r = obj[rKeys[i]];
        if (Number.isFinite(Number(q)) && Number.isFinite(Number(r))) {
          return { q: Number(q), r: Number(r) };
        }
      }
      return null;
    }

    function readUnitQrFromCollection(collection, unitId) {
      if (!Array.isArray(collection) || !unitId) return null;
      const wanted = String(unitId || "");
      const unit = collection.find(function (u) { return String((u && u.unit_id) || "") === wanted; });
      if (!unit || typeof unit !== "object") return null;
      return readQrFromObject(unit, ["q", "hex_q", "target_q", "to_q", "current_q"], ["r", "hex_r", "target_r", "to_r", "current_r"]);
    }

    function readActionDestination(step) {
      if (!step || typeof step !== "object") return null;
      const direct = readQrFromObject(step, ["target_q", "to_q", "action_target_q"], ["target_r", "to_r", "action_target_r"]);
      if (direct) return direct;
      const parts = String(step.action_id || "").split(":");
      if (parts.length < 4) return null;
      const q = Number(parts[2]);
      const r = Number(parts[3]);
      if (!Number.isFinite(q) || !Number.isFinite(r)) return null;
      return { q, r };
    }

    function deriveStepPositions(step, transitions, stepIdx) {
      const unitId = String((step && step.unit_id) || "");
      const currentCandidates = [
        readActionDestination(step),
        readQrFromObject(step, ["current_q", "to_q", "q"], ["current_r", "to_r", "r"]),
        readUnitQrFromCollection(step && step.units, unitId),
      ];
      const current = currentCandidates.find(Boolean) || null;
      const previousCandidates = [
        readQrFromObject(step, ["previous_q", "from_q", "pre_q"], ["previous_r", "from_r", "pre_r"]),
        readQrFromObject(step && step.unit_before, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
        readQrFromObject(step && step.pre_step_unit, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
        readQrFromObject(step && step.unit_snapshot_before, ["q", "hex_q", "current_q"], ["r", "hex_r", "current_r"]),
      ];
      const prevRow = (Array.isArray(transitions) && Number.isFinite(Number(stepIdx)) && Number(stepIdx) > 0)
        ? transitions[Number(stepIdx) - 1]
        : null;
      previousCandidates.push(readUnitQrFromCollection(prevRow && prevRow.units, unitId));
      previousCandidates.push(readQrFromObject(prevRow, ["target_q", "current_q", "to_q"], ["target_r", "current_r", "to_r"]));
      const previous = previousCandidates.find(Boolean) || null;
      return {
        previousPosition: fmtQrPair(previous && previous.q, previous && previous.r),
        currentPosition: fmtQrPair(current && current.q, current && current.r),
      };
    }

    function resolveTargetVpIdFromStepRow(stepRowObj) {
      if (!stepRowObj || typeof stepRowObj !== "object") return "N/A";
      const targetVp = String(stepRowObj.target_vp || "").trim();
      return targetVp || "N/A";
    }

    function buildReplayStepDetailsHtml(stepRow, transitions, stepIdx) {
      const tq = (stepRow.target_q === undefined || stepRow.target_q === null) ? "-" : String(stepRow.target_q);
      const tr = (stepRow.target_r === undefined || stepRow.target_r === null) ? "-" : String(stepRow.target_r);
      const targetQr = tq + "," + tr;
      const targetVp = resolveTargetVpIdFromStepRow(stepRow);
      const targetVpWhy = String((stepRow && stepRow.target_vp_why) || "").trim() || "N/A";
      const positions = deriveStepPositions(stepRow, transitions, stepIdx);
      const dmgKills = Number(stepRow.damage_dealt || 0).toFixed(3) + " / " + Number(stepRow.kills_dealt || 0).toFixed(0);
      const mctsTotalVisits = Number.isFinite(Number(stepRow.mcts_total_visits))
        ? String(Math.round(Number(stepRow.mcts_total_visits)))
        : "N/A";
      const mctsActiveActions = Number.isFinite(Number(stepRow.mcts_active_actions))
        ? String(Math.round(Number(stepRow.mcts_active_actions)))
        : "N/A";
      const mctsRootActionsCount = Number.isFinite(Number(stepRow.mcts_root_actions_count))
        ? String(Math.round(Number(stepRow.mcts_root_actions_count)))
        : "N/A";
      const coverageTxt = String(stepRow.telemetry_coverage_status || "unknown")
        + (String(stepRow.telemetry_coverage_reason || "").trim() ? (" (" + String(stepRow.telemetry_coverage_reason || "").trim() + ")") : "");
      const benchId = (typeof replayState === "object" && replayState && replayState.payload)
        ? String((replayState.payload && replayState.payload.bench_id) || "")
        : "";
      const runId = (typeof replayState === "object" && replayState && replayState.payload)
        ? String((replayState.payload && replayState.payload.run_id) || "")
        : "";
      const evalId = (typeof replayState === "object" && replayState)
        ? String(replayState.evalId || "")
        : "";
      const episodeIndex = (typeof replayState === "object" && replayState)
        ? Math.max(0, Number(replayState.episodeIndex || 0))
        : 0;
      const episodePath = replayResolveEpisodePathFromState();
      const locator = "run_id=" + runId
        + " | bench_id=" + benchId
        + " | eval_id=" + evalId
        + " | episode_index=" + String(episodeIndex)
        + " | step=" + String(Math.max(0, Number(stepIdx || 0)))
        + " | unit_id=" + String(stepRow.unit_id || "");
      return '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
        '<tbody>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">json_locator</td><td style="border:1px solid #334155;padding:6px;font-family:monospace;">' + esc(locator) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">episode_path</td><td style="border:1px solid #334155;padding:6px;font-family:monospace;">' + esc(episodePath || "N/A") + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">to_play</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.to_play) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">action_id</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.action_id) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">unit_id</td><td style="border:1px solid #334155;padding:6px;">' + esc(stepRow.unit_id) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">target_vp</td><td style="border:1px solid #334155;padding:6px;">' + esc(targetVp) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">target_vp_why</td><td style="border:1px solid #334155;padding:6px;">' + esc(targetVpWhy) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">target_qr</td><td style="border:1px solid #334155;padding:6px;">' + esc(targetQr) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">previous_position</td><td style="border:1px solid #334155;padding:6px;">' + esc(positions.previousPosition) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">current_position</td><td style="border:1px solid #334155;padding:6px;">' + esc(positions.currentPosition) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">reward</td><td style="border:1px solid #334155;padding:6px;">' + esc(Number(stepRow.reward || 0).toFixed(4)) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">damage / kills</td><td style="border:1px solid #334155;padding:6px;">' + esc(dmgKills) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">mcts_total_visits</td><td style="border:1px solid #334155;padding:6px;">' + esc(mctsTotalVisits) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">mcts_root_actions_count</td><td style="border:1px solid #334155;padding:6px;">' + esc(mctsRootActionsCount) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">mcts_active_actions</td><td style="border:1px solid #334155;padding:6px;">' + esc(mctsActiveActions) + '</td></tr>' +
          '<tr><td style="border:1px solid #334155;padding:6px;">telemetry_coverage</td><td style="border:1px solid #334155;padding:6px;">' + esc(coverageTxt) + '</td></tr>' +
        '</tbody>' +
      '</table>';
    }
"""
