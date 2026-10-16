from __future__ import annotations


def replay_controller_helpers_js() -> str:
    return """
    function resolveReplayResultRow(evalRow) {
      const rowObj = (evalRow && typeof evalRow === "object") ? evalRow : {};
      const results = Array.isArray(rowObj.results) ? rowObj.results : [];
      if (results.length > 0) {
        // Prefer first concrete result row; eval wrapper rows often
        // do not carry side/controller metadata directly.
        return results[0];
      }
      return rowObj;
    }

    function renderReplayControllerBySide(evalRows, activeRow, replayStateObj) {
      const replayControllerBySide = document.getElementById("replayControllerBySide");
      if (!replayControllerBySide) return;
      const evalSel = document.getElementById("replayEvalSelect");
      const evalId = String((((evalSel || {}).value) || (replayStateObj && replayStateObj.evalId) || ""));
      const sourceRows = Array.isArray(evalRows) ? evalRows : [];
      const replayEvalRow = sourceRows.find(function (r) { return String((r && r.eval_id) || "") === String(evalId); }) || activeRow || {};
      const replayResultRow = resolveReplayResultRow(replayEvalRow);
      const matchLabel = String(replayResultRow.matchup_profile || replayResultRow.agent_name || "Unknown match");
      const controllerRows = controllerBySideFromResult(replayResultRow);
      const episodeLabel = "ep " + String(Number((replayStateObj && replayStateObj.episodeIndex) || 0));
      let bySideHtml = '<div class="muted" style="margin-bottom:4px;">match=' + esc(matchLabel) + ' | ' + esc(episodeLabel) + '</div>' +
        '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
        '<th style="border:1px solid #334155;padding:6px;">side</th>' +
        '<th style="border:1px solid #334155;padding:6px;">controller</th>' +
        '<th style="border:1px solid #334155;padding:6px;">source</th>' +
        '</tr></thead><tbody>';
      for (const item of controllerRows) {
        bySideHtml += '<tr>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.side || "Unknown side")) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.controller || "Unknown")) + '</td>' +
          '<td style="border:1px solid #334155;padding:6px;">' + esc(String(item.source || "missing_controller_data")) + '</td>' +
          '</tr>';
      }
      bySideHtml += '</tbody></table>';
      replayControllerBySide.innerHTML = bySideHtml;
    }
"""
