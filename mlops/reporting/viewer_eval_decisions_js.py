from __future__ import annotations


def eval_decisions_js() -> str:
    return """
    function renderEvalDecisions(filteredResultRows, filterCtx) {
      const host = document.getElementById("evalDecisionsRoot");
      if (!host) return;
      if (!Array.isArray(filteredResultRows) || !filteredResultRows.length) {
        host.innerHTML = '<h3 style="margin:8px 0;">Table A: Action Kind x Side</h3><div class="muted">No rows for current filters.</div>';
        return;
      }
      const rowMap = {};
      const sideKeyMap = {};
      const topActions = {};
      const ownership = {};
      for (const er of filteredResultRows) {
        const results = Array.isArray(er.results) ? er.results : [];
        for (const r of results) {
          const summary = (r && r.eval_decision_summary) || {};
          const by = summary.by_action_kind_and_side || {};
          for (const key of Object.keys(by || {})) {
            const src = by[key] || {};
            const srcSide = String(src.unit_side || "UNK");
            if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, srcSide, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
            const k = String(src.action_kind || "UNKNOWN") + "|" + String(src.unit_side || "UNK");
            if (!rowMap[k]) rowMap[k] = { action_kind: String(src.action_kind || "UNKNOWN"), side: String(src.unit_side || "UNK"), count: 0, damage: 0, kills: 0 };
            rowMap[k].count += Number(src.count || 0);
            rowMap[k].damage += Number(src.damage_sum || 0);
            rowMap[k].kills += Number(src.kills_sum || 0);
            sideKeyMap[String(src.unit_side || "UNK")] = true;
          }
          const tops = Array.isArray(r.eval_decisions_top) ? r.eval_decisions_top : [];
          for (const t of tops) {
            const tSide = String(t.unit_side || "UNK");
            if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, tSide, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
            const aid = String(t.action_id || "UNKNOWN_ACTION");
            if (!topActions[aid]) topActions[aid] = { action_id: aid, action_kind: String(t.action_kind || ""), side: String(t.unit_side || ""), count: 0, damage: 0, kills: 0 };
            topActions[aid].count += Number(t.count || 0);
            topActions[aid].damage += Number(t.damage_sum || 0);
            topActions[aid].kills += Number(t.kills_sum || 0);
          }
          const own = summary.decision_ownership_by_side || {};
          for (const s of Object.keys(own || {})) {
            if (filterCtx && typeof filterCtx.sideAllowed === "function" && !filterCtx.sideAllowed(r, s, filterCtx.side || "__all__", filterCtx.controller || "__all__")) continue;
            const o = own[s] || {};
            if (!ownership[s]) ownership[s] = { side: s, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, unknown_override_rows: 0 };
            ownership[s].rows += Number(o.rows || 0);
            ownership[s].policy_kept += Number(o.policy_kept || 0);
            ownership[s].overwritten += Number(o.overwritten || 0);
            ownership[s].override_signal_rows += Number(o.override_signal_rows || 0);
            ownership[s].unknown_override_rows += Number(o.unknown_override_rows || 0);
          }
        }
      }
      const rows = Object.values(rowMap).sort((a, b) => Number(b.count || 0) - Number(a.count || 0));
      const sideKeys = Object.keys(sideKeyMap).sort((a, b) => String(a || "").localeCompare(String(b || "")));
      const pivotRows = {};
      for (const row of rows) {
        const action = String(row.action_kind || "UNKNOWN");
        const side = String(row.side || "UNK");
        if (!pivotRows[action]) pivotRows[action] = {};
        pivotRows[action][side] = row;
      }
      const totalsBySide = {};
      for (const side of sideKeys) {
        totalsBySide[side] = { count: 0, damage: 0, kills: 0 };
      }
      for (const row of rows) {
        const side = String(row.side || "UNK");
        if (!totalsBySide[side]) totalsBySide[side] = { count: 0, damage: 0, kills: 0 };
        totalsBySide[side].count += Number(row.count || 0);
        totalsBySide[side].damage += Number(row.damage || 0);
        totalsBySide[side].kills += Number(row.kills || 0);
      }
      function pctPart(value, total) {
        const v = Number(value || 0);
        const t = Number(total || 0);
        if (!Number.isFinite(v) || !Number.isFinite(t) || t <= 0) return "N/A";
        return (100.0 * v / t).toFixed(1) + "%";
      }
      const actionKeys = Object.keys(pivotRows).sort((a, b) => {
        let sumA = 0;
        const aRow = pivotRows[a] || {};
        for (const s of sideKeys) sumA += Number(((aRow[s] || {}).count) || 0);
        let sumB = 0;
        const bRow = pivotRows[b] || {};
        for (const s of sideKeys) sumB += Number(((bRow[s] || {}).count) || 0);
        return sumB - sumA;
      });
      const topRows = Object.values(topActions).sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 20);
      const ownRows = Object.values(ownership).sort((a, b) => String(a.side).localeCompare(String(b.side)));
      let html = '<h3 style="margin:8px 0;">Table A: Action Kind x Side (Pivot)</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
        '<th rowspan="2" style="border:1px solid #334155;padding:6px;">action_kind</th>';
      for (const side of sideKeys) {
        html += '<th colspan="6" style="border:1px solid #334155;padding:6px;white-space:nowrap;">' + esc(String(side || "UNK")) + '</th>';
      }
      html += '</tr><tr>';
      for (const _side of sideKeys) {
        html += '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">count</th>' +
          '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">count %</th>' +
          '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">damage</th>' +
          '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">damage %</th>' +
          '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">kills</th>' +
          '<th style="border:1px solid #334155;padding:6px;white-space:nowrap;">kills %</th>';
      }
      html += '</tr></thead><tbody>';
      if (!actionKeys.length || !sideKeys.length) {
        html += '<tr><td colspan="' + String(1 + sideKeys.length * 6) + '" style="border:1px solid #334155;padding:6px;" class="muted">No decision rows available.</td></tr>';
      } else {
        for (const action of actionKeys) {
          html += '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(action) + '</td>';
          for (const side of sideKeys) {
            const cell = ((pivotRows[action] || {})[side]) || null;
            if (!cell) {
              html += '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>' +
                '<td style="border:1px solid #334155;padding:6px;" class="muted">-</td>';
            } else {
              const totals = totalsBySide[side] || { count: 0, damage: 0, kills: 0 };
              html += '<td style="border:1px solid #334155;padding:6px;">' + esc(String(cell.count || 0)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(pctPart(cell.count, totals.count)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(cell.damage || 0).toFixed(3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(pctPart(cell.damage, totals.damage)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(cell.kills || 0).toFixed(3)) + '</td>' +
                '<td style="border:1px solid #334155;padding:6px;">' + esc(pctPart(cell.kills, totals.kills)) + '</td>';
            }
          }
          html += '</tr>';
        }
      }
      html += '</tbody></table>';
      html += '<h3 style="margin:12px 0 8px 0;">Table B: Decision Ownership by Side</h3>' +
        '<div class="muted" style="margin:0 0 6px 0;">Source: policy_overridden_by_mcts (canonical ownership telemetry).</div>' +
        '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
        '<th style="border:1px solid #334155;padding:6px;">side</th>' +
        '<th style="border:1px solid #334155;padding:6px;">rows</th>' +
        '<th style="border:1px solid #334155;padding:6px;">policy_kept</th>' +
        '<th style="border:1px solid #334155;padding:6px;">overwritten</th>' +
        '<th style="border:1px solid #334155;padding:6px;">override_signal_rows</th>' +
        '<th style="border:1px solid #334155;padding:6px;">unknown_override_rows</th>' +
        '</tr></thead><tbody>';
      if (!ownRows.length) {
        html += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No ownership rows available.</td></tr>';
      } else {
        for (const r of ownRows) {
          html += '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.rows || 0)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.policy_kept || 0)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.overwritten || 0)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.override_signal_rows || 0)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.unknown_override_rows || 0)) + '</td>' +
            '</tr>';
        }
      }
      html += '</tbody></table>';
      html += '<h3 style="margin:12px 0 8px 0;">Top Actions</h3><table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
        '<th style="border:1px solid #334155;padding:6px;">action_id</th>' +
        '<th style="border:1px solid #334155;padding:6px;">action_kind</th>' +
        '<th style="border:1px solid #334155;padding:6px;">side</th>' +
        '<th style="border:1px solid #334155;padding:6px;">count</th>' +
        '<th style="border:1px solid #334155;padding:6px;">damage</th>' +
        '<th style="border:1px solid #334155;padding:6px;">kills</th>' +
        '</tr></thead><tbody>';
      if (!topRows.length) {
        html += '<tr><td colspan="6" style="border:1px solid #334155;padding:6px;" class="muted">No top actions available.</td></tr>';
      } else {
        for (const r of topRows) {
          html += '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action_id || "")) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.action_kind || "")) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.side || "")) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(String(r.count || 0)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.damage || 0).toFixed(3)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(r.kills || 0).toFixed(3)) + '</td>' +
            '</tr>';
        }
      }
      html += '</tbody></table>';
      host.innerHTML = html;
    }
"""
