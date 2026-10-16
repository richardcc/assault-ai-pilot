from __future__ import annotations


def head_diagnostics_js() -> str:
    return """
      function renderHeadDiagnostics(evalRowsForTabs) {
        const root = document.getElementById("headDiagnosticsRoot");
        if (!root) return;
        function healthBadge(status, text) {
          const s = String(status || "na").toLowerCase();
          const color = s === "green"
            ? "#22c55e"
            : (s === "yellow" ? "#f59e0b" : (s === "na" ? "#94a3b8" : "#ef4444"));
          return '<span style="display:inline-block;padding:2px 8px;border:1px solid #334155;border-radius:999px;color:' + color + ';font-size:11px;font-weight:700;">' + esc(String(text || s)) + "</span>";
        }
        function healthRow(label, status, value, hint) {
          return "<tr>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(label) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + healthBadge(status, String(status || "na").toUpperCase()) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;'>" + esc(value) + "</td>" +
            "<td style='border:1px solid #334155;padding:6px;' class='muted'>" + esc(hint) + "</td>" +
          "</tr>";
        }
        function healthHint(baseHint, reason) {
          const why = String(reason || "").trim();
          return why ? (String(baseHint || "") + " | source: " + why) : String(baseHint || "");
        }
        function computeModelHealth(rows) {
          const srcRows = Array.isArray(rows) ? rows : [];
          let qSatNum = 0;
          let qSatDen = 0;
          let activeActionsSum = 0;
          let totalVisitsSum = 0;
          let completeCov = 0;
          let covRows = 0;
          let usefulVisitNum = 0;
          let usefulVisitDen = 0;
          let totalStepRows = 0;
          let qSatRowsWithSignal = 0;
          let exploreRowsWithSignal = 0;
          let coverageRowsWithSignal = 0;
          let usefulRowsWithSignal = 0;
          for (const er of srcRows) {
            const results = Array.isArray(er && er.results) ? er.results : [];
            for (const rr of results) {
              const sourceBundle = telemetryStepsFromResult(rr);
              const tops = Array.isArray(sourceBundle && sourceBundle.steps) ? sourceBundle.steps : [];
              for (const step of tops) {
                totalStepRows += 1;
                const qClipped = Number((step && step.mcts_q_clipped_count) || (step && step.mcts_q_guardrail_clipped_count) || 0);
                const qDen = Number((step && step.mcts_q_clip_denominator_count) || (step && step.mcts_total_visits) || 0);
                if (Number.isFinite(qClipped) && Number.isFinite(qDen) && qDen > 0) {
                  qSatNum += qClipped;
                  qSatDen += qDen;
                  qSatRowsWithSignal += 1;
                }
                const active = Number(step && step.mcts_active_actions);
                const visits = Number(step && step.mcts_total_visits);
                if (Number.isFinite(active) && Number.isFinite(visits) && visits > 0) {
                  activeActionsSum += active;
                  totalVisitsSum += visits;
                  exploreRowsWithSignal += 1;
                }
                const cov = String((step && step.telemetry_coverage_status) || "").trim().toLowerCase();
                if (cov) {
                  covRows += 1;
                  if (cov === "complete") completeCov += 1;
                  coverageRowsWithSignal += 1;
                }
                const cands = Array.isArray(step && step.mcts_action_candidates) ? step.mcts_action_candidates : [];
                let rowHasVisitSignal = false;
                for (const c of cands) {
                  const v = Number(c && c.visit_count);
                  if (!Number.isFinite(v)) continue;
                  rowHasVisitSignal = true;
                  usefulVisitDen += 1;
                  if (v >= 2) usefulVisitNum += 1;
                }
                if (rowHasVisitSignal) usefulRowsWithSignal += 1;
              }
            }
          }
          const qSatRate = qSatDen > 0 ? (qSatNum / qSatDen) : null;
          const exploreRate = totalVisitsSum > 0 ? (activeActionsSum / totalVisitsSum) : null;
          const covRate = covRows > 0 ? (completeCov / covRows) : null;
          const usefulRate = usefulVisitDen > 0 ? (usefulVisitNum / usefulVisitDen) : null;
          const consistencyLoss = getHeadMetric("consistency", "train_consistency_loss");
          const reasons = {
            qSatRate: qSatRowsWithSignal > 0
              ? ("producer_step_fields rows=" + String(qSatRowsWithSignal) + "/" + String(totalStepRows))
              : "missing producer fields: mcts_q_clipped_count/mcts_q_guardrail_clipped_count + mcts_q_clip_denominator_count|mcts_total_visits",
            exploreRate: exploreRowsWithSignal > 0
              ? ("producer_step_fields rows=" + String(exploreRowsWithSignal) + "/" + String(totalStepRows))
              : "missing producer fields: mcts_active_actions + mcts_total_visits",
            covRate: coverageRowsWithSignal > 0
              ? ("producer_step_fields rows=" + String(coverageRowsWithSignal) + "/" + String(totalStepRows))
              : "missing producer fields: telemetry_coverage_status",
            usefulRate: usefulRowsWithSignal > 0
              ? ("producer_candidates visit_count rows=" + String(usefulRowsWithSignal) + "/" + String(totalStepRows))
              : "missing producer fields: mcts_action_candidates[].visit_count",
            consistencyLoss: (consistencyLoss !== null && consistencyLoss !== undefined && Number.isFinite(Number(consistencyLoss)))
              ? "producer_head_metrics consistency.train_consistency_loss"
              : "missing producer head metric: consistency.train_consistency_loss",
          };
          return { qSatRate, exploreRate, covRate, usefulRate, consistencyLoss, reasons };
        }
        function modelHealthStatus(v, thresholds) {
          if (v === null || v === undefined || !Number.isFinite(Number(v))) return "na";
          const n = Number(v);
          const t = thresholds || {};
          if (t.lower_is_better) {
            if (n <= Number(t.green)) return "green";
            if (n <= Number(t.yellow)) return "yellow";
            return "red";
          }
          if (n >= Number(t.green)) return "green";
          if (n >= Number(t.yellow)) return "yellow";
          return "red";
        }
        function renderModelHealthPanel(rows) {
          const h = computeModelHealth(rows);
          const qSatStatus = modelHealthStatus(h.qSatRate, { lower_is_better: true, green: 0.10, yellow: 0.25 });
          const exploreStatus = modelHealthStatus(h.exploreRate, { lower_is_better: true, green: 0.35, yellow: 0.20 });
          const covStatus = modelHealthStatus(h.covRate, { green: 0.95, yellow: 0.80 });
          const usefulStatus = modelHealthStatus(h.usefulRate, { green: 0.30, yellow: 0.15 });
          const consistencyStatus = modelHealthStatus(h.consistencyLoss, { lower_is_better: true, green: 0.05, yellow: 0.20 });
          const rowsHtml = [
            healthRow("Q saturation", qSatStatus, fmtEvalPct(h.qSatRate), healthHint("lower is better", (h.reasons || {}).qSatRate)),
            healthRow("Exploration breadth (active_actions/visits)", exploreStatus, fmtEvalPct(h.exploreRate), healthHint("too high often means shallow search", (h.reasons || {}).exploreRate)),
            healthRow("Telemetry complete coverage", covStatus, fmtEvalPct(h.covRate), healthHint("higher is better", (h.reasons || {}).covRate)),
            healthRow("Useful visits (visit_count>=2)", usefulStatus, fmtEvalPct(h.usefulRate), healthHint("higher is better", (h.reasons || {}).usefulRate)),
            healthRow("Train consistency loss", consistencyStatus, fmtEvalNum(h.consistencyLoss, 6), healthHint("lower is better", (h.reasons || {}).consistencyLoss)),
          ].join("");
          return '<div style="margin-bottom:10px;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<h3 style="margin:0 0 6px 0;">Model Health</h3>' +
            '<div class="muted" style="margin-bottom:6px;">Quick sanity board for EfficientZero v2 state/usage/health on current filters.</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;">check</th>' +
            '<th style="border:1px solid #334155;padding:6px;">status</th>' +
            '<th style="border:1px solid #334155;padding:6px;">value</th>' +
            '<th style="border:1px solid #334155;padding:6px;">note</th>' +
            '</tr></thead><tbody>' + rowsHtml + '</tbody></table>' +
            '</div>';
        }
        function isMetricOkValue(v) {
          if (v === null || v === undefined) return false;
          if (typeof v === "string") {
            const t = v.trim();
            if (!t) return false;
            if (t.toUpperCase() === "N/A") return false;
            return true;
          }
          if (typeof v === "number") return Number.isFinite(v);
          return true;
        }
        function metricStatus(v, opts) {
          const o = opts || {};
          if (!isMetricOkValue(v)) return "na";
          if (Array.isArray(o.degradedSources) && o.degradedSources.includes(String(v))) return "degraded";
          return "ok";
        }
        function metricValueHtml(v, opts) {
          const st = metricStatus(v, opts);
          const txt = (v === null || v === undefined || v === "") ? "N/A" : String(v);
          if (st === "ok") return '<span class="ok-text">' + esc(txt) + "</span>";
          if (st === "degraded") return '<span class="degraded-text">' + esc(txt) + "</span>";
          return '<span class="na-text">' + esc(txt) + "</span>";
        }
        const rowsTotal = Array.isArray(evalRowsForTabs) ? evalRowsForTabs.length : 0;
        const headDiag = aggregateHeadDiagnostics(evalRowsForTabs);
        let status = "ok";
        if (rowsTotal === 0 || Number(headDiag.n || 0) <= 0) status = "no data";
        else if (Number(headDiag.n || 0) < rowsTotal) status = "partial";
        function hasFiniteNumber(v) {
          const n = Number(v);
          return Number.isFinite(n);
        }
        function metricAliases(headName, metricKey) {
          const h = String(headName || "");
          const k = String(metricKey || "");
          const base = [k];
          if (h === "mcts") {
            const aliasMap = {
              "eval_decision_steps": ["xai_decision_steps"],
              "eval_policy_confidence_mean": ["xai_policy_confidence_mean"],
              "eval_policy_margin_mean": ["xai_policy_margin_mean"],
              "eval_latent_signal_coverage": ["xai_latent_signal_coverage"],
              "eval_reaction_window_count": ["reaction_window_count"],
              "eval_melee_attempts": ["melee_attempts"],
            };
            return base.concat(aliasMap[k] || []);
          }
          if (h === "objective") {
            const aliasMap = {
              "eval_vp_capture_opportunity_steps": ["xai_vp_capture_opportunity_steps"],
              "eval_vp_capture_taken_steps": ["xai_vp_capture_taken_steps"],
              "eval_vp_immediate_capture_opportunity_steps": ["xai_vp_immediate_capture_opportunity_steps"],
              "eval_vp_immediate_capture_taken_steps": ["xai_vp_immediate_capture_taken_steps"],
              "eval_vp_capture_take_rate": ["xai_vp_capture_take_rate"],
              "eval_vp_immediate_capture_take_rate": ["xai_vp_immediate_capture_take_rate"],
              "eval_vp_conversion_efficiency": ["vp_conversion_efficiency"],
              "eval_vp_immediate_conversion_efficiency": ["vp_immediate_conversion_efficiency"],
            };
            return base.concat(aliasMap[k] || []);
          }
          return base;
        }
        function readMetricFromResultRow(resultRow, headName, metricKey) {
          const aliases = metricAliases(headName, metricKey);
          const kpi = (resultRow && resultRow.phase_2_9_eval_kpis && typeof resultRow.phase_2_9_eval_kpis === "object")
            ? resultRow.phase_2_9_eval_kpis
            : {};
          for (const key of aliases) {
            if (Object.prototype.hasOwnProperty.call(kpi, key) && hasFiniteNumber(kpi[key])) {
              return Number(kpi[key]);
            }
          }
          return null;
        }
        function readMetricFromEvalRow(evalRow, headName, metricKey) {
          const aliases = metricAliases(headName, metricKey);
          const src = (((evalRow || {}).head_diagnostics_eval || {})[headName] || {});
          for (const key of aliases) {
            if (Object.prototype.hasOwnProperty.call(src, key) && hasFiniteNumber(src[key])) {
              return Number(src[key]);
            }
          }
          const trainEval = ((evalRow || {}).phase_2_9_train_eval || {});
          const headBlock = (trainEval && typeof trainEval === "object" && trainEval[headName] && typeof trainEval[headName] === "object")
            ? trainEval[headName]
            : null;
          if (headBlock) {
            for (const key of aliases) {
              if (Object.prototype.hasOwnProperty.call(headBlock, key) && hasFiniteNumber(headBlock[key])) {
                return Number(headBlock[key]);
              }
            }
          }
          const evalBlock = (trainEval && typeof trainEval === "object" && trainEval.eval && typeof trainEval.eval === "object")
            ? trainEval.eval
            : null;
          if (evalBlock) {
            for (const key of aliases) {
              if (Object.prototype.hasOwnProperty.call(evalBlock, key) && hasFiniteNumber(evalBlock[key])) {
                return Number(evalBlock[key]);
              }
            }
          }
          const results = Array.isArray(evalRow && evalRow.results) ? evalRow.results : [];
          let sum = 0;
          let count = 0;
          for (const rr of results) {
            const v = readMetricFromResultRow(rr, headName, metricKey);
            if (v === null) continue;
            sum += Number(v);
            count += 1;
          }
          if (count > 0) return sum / count;
          return null;
        }
        function getHeadMetric(headName, metricKey) {
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          let sum = 0;
          let count = 0;
          for (const row of rows) {
            const v = readMetricFromEvalRow(row, headName, metricKey);
            if (v === null) continue;
            sum += Number(v);
            count += 1;
          }
          if (!count) return null;
          return sum / count;
        }
        function fmtEvalNum(v, digits) {
          if (v === null || v === undefined) return "N/A";
          const n = Number(v);
          if (!Number.isFinite(n)) return "N/A";
          return n.toFixed(digits);
        }
        function fmtEvalPct(v) {
          if (v === null || v === undefined) return "N/A";
          const n = Number(v);
          if (!Number.isFinite(n)) return "N/A";
          return (n * 100).toFixed(1) + "%";
        }
        function coverageForHead(headName, metricKeys) {
          const keys = Array.isArray(metricKeys) ? metricKeys : [];
          const available = keys.filter(function (k) { return getHeadMetric(headName, k) !== null; }).length;
          let cov = "none";
          if (available === keys.length && keys.length > 0) cov = "complete";
          else if (available > 0) cov = "partial";
          let reason = "no eval telemetry for this head";
          if (cov === "complete") reason = String(available) + "/" + String(keys.length) + " metrics present";
          else if (cov === "partial") reason = String(available) + "/" + String(keys.length) + " metrics present";
          return { status: cov, reason: reason, available: available, total: keys.length };
        }
        function coverageBadge(cov) {
          const c = cov || { status: "none", reason: "no eval telemetry for this head" };
          let color = "#ef4444";
          if (c.status === "complete") color = "#22c55e";
          else if (c.status === "partial") color = "#f59e0b";
          return '<span style="display:inline-block;padding:1px 6px;border:1px solid #334155;border-radius:999px;color:' + color + ';font-size:11px;">' +
            esc(String(c.status || "none") + " (" + String(c.reason || "") + ")") +
            '</span>';
        }
        function collectIntentSignals() {
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          const actionMap = {};
          const ownershipBySide = {};
          let overrideSignalRows = 0;
          let unknownOverrideRows = 0;
          let totalTopActionCount = 0;
          for (const evalRow of rows) {
            const results = Array.isArray(evalRow.results) ? evalRow.results : [];
            for (const r of results) {
              const tops = Array.isArray(r.eval_decisions_top) ? r.eval_decisions_top : [];
              for (const t of tops) {
                const aid = String(t.action_id || "UNKNOWN_ACTION");
                if (!actionMap[aid]) {
                  actionMap[aid] = {
                    action_id: aid,
                    action_kind: String(t.action_kind || "N/A"),
                    unit_side: String(t.unit_side || "N/A"),
                    count: 0,
                  };
                }
                const c = Number(t.count || 0);
                actionMap[aid].count += Number.isFinite(c) ? c : 0;
                totalTopActionCount += Number.isFinite(c) ? c : 0;
              }
              const own = ((r || {}).eval_decision_summary || {}).decision_ownership_by_side || {};
              for (const side of Object.keys(own || {})) {
                if (!ownershipBySide[side]) ownershipBySide[side] = { side: side, rows: 0, policy_kept: 0, overwritten: 0, override_signal_rows: 0, unknown_override_rows: 0 };
                const src = own[side] || {};
                ownershipBySide[side].rows += Number(src.rows || 0);
                ownershipBySide[side].policy_kept += Number(src.policy_kept || 0);
                ownershipBySide[side].overwritten += Number(src.overwritten || 0);
                ownershipBySide[side].override_signal_rows += Number(src.override_signal_rows || 0);
                ownershipBySide[side].unknown_override_rows += Number(src.unknown_override_rows || 0);
              }
              const ownSource = ((r || {}).eval_decision_summary || {}).decision_ownership_source || {};
              overrideSignalRows += Number(ownSource.override_signal_rows || 0);
              unknownOverrideRows += Number(ownSource.unknown_override_rows || 0);
            }
          }
          const topPolicyActions = Object.values(actionMap)
            .sort(function (a, b) { return Number(b.count || 0) - Number(a.count || 0); })
            .slice(0, 5)
            .map(function (x) {
              const share = totalTopActionCount > 0 ? (Number(x.count || 0) / totalTopActionCount) : null;
              return [
                String(x.action_id || "N/A"),
                String(x.action_kind || "N/A"),
                String(x.unit_side || "N/A"),
                share === null ? "N/A" : ((share * 100).toFixed(1) + "%"),
              ];
            });
          const mctsOwnershipRows = Object.values(ownershipBySide)
            .sort(function (a, b) { return String(a.side || "").localeCompare(String(b.side || "")); })
            .map(function (x) {
              return [
                String(x.side || "N/A"),
                String(Math.round(Number(x.rows || 0))),
                String(Math.round(Number(x.policy_kept || 0))),
                String(Math.round(Number(x.overwritten || 0))),
                String(Math.round(Number(x.override_signal_rows || 0))),
                String(Math.round(Number(x.unknown_override_rows || 0))),
              ];
            });
          return {
            topPolicyActions: topPolicyActions,
            mctsOwnershipRows: mctsOwnershipRows,
            ownershipSourceSummary: {
              override_signal_rows: Math.round(overrideSignalRows),
              unknown_override_rows: Math.round(unknownOverrideRows),
            },
          };
        }
        function headTable(title, rows) {
          const body = (rows || []).map(function (r) {
            return '<tr>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r[0]) + '</td>' +
              '<td style="border:1px solid #334155;padding:6px;">' + esc(r[1]) + '</td>' +
              '</tr>';
          }).join("");
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<h3 style="margin:0 0 6px 0;">' + esc(title) + '</h3>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            '<th style="border:1px solid #334155;padding:6px;width:40%;">metric</th>' +
            '<th style="border:1px solid #334155;padding:6px;">value</th>' +
            '</tr></thead><tbody>' + body + '</tbody></table></div>';
        }
        function tableRows(rows, columns, emptyMsg) {
          const cols = Array.isArray(columns) ? columns : [];
          if (!Array.isArray(rows) || !rows.length) {
            return '<tr><td colspan="' + esc(String(Math.max(1, cols.length))) + '" style="border:1px solid #334155;padding:6px;" class="muted">' + esc(emptyMsg) + '</td></tr>';
          }
          return rows.map(function (r) {
            const cells = Array.isArray(r) ? r : [];
            return '<tr>' + cells.map(function (c) {
              if (c && typeof c === "object" && c.__html) {
                return '<td style="border:1px solid #334155;padding:6px;">' + String(c.__html) + "</td>";
              }
              return '<td style="border:1px solid #334155;padding:6px;">' + esc(String(c)) + '</td>';
            }).join("") + '</tr>';
          }).join("");
        }
        function intentTable(title, columns, rows, emptyMsg) {
          const cols = Array.isArray(columns) ? columns : [];
          return '<div style="margin-top:8px;">' +
            '<div class="muted" style="margin-bottom:4px;">' + esc(title) + '</div>' +
            '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
            cols.map(function (c) { return '<th style="border:1px solid #334155;padding:6px;">' + esc(c) + '</th>'; }).join("") +
            '</tr></thead><tbody>' + tableRows(rows, cols, emptyMsg) + '</tbody></table>' +
            '</div>';
        }
        function headCard(title, coverage, summary, metricRows, intentHtml) {
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;">' +
              '<h3 style="margin:0;">' + esc(title) + '</h3>' +
              coverageBadge(coverage) +
            '</div>' +
            '<div class="muted" style="margin-bottom:6px;">' + esc(summary) + '</div>' +
            headTable("Metrics", metricRows) +
            intentHtml +
          '</div>';
        }
        const headSpecRows = [
          { key: "policy", label: "Policy", metrics: ["eval_decision_steps", "eval_confidence_mean", "eval_margin_mean", "eval_latent_signal_coverage", "train_policy_loss"] },
          { key: "value", label: "Value", metrics: ["train_value_loss", "eval_win_rate_proxy", "eval_avg_return_proxy"] },
          { key: "reward", label: "Reward", metrics: ["train_reward_loss", "eval_avg_return_proxy", "eval_avg_steps_proxy"] },
          { key: "objective", label: "Objective", metrics: ["train_objective_loss", "eval_vp_capture_opportunity_steps", "eval_vp_capture_taken_steps", "eval_vp_immediate_capture_opportunity_steps", "eval_vp_immediate_capture_taken_steps", "eval_vp_capture_take_rate", "eval_vp_immediate_capture_take_rate", "eval_vp_conversion_efficiency", "eval_vp_immediate_conversion_efficiency"] },
          { key: "consistency", label: "Consistency", metrics: ["train_consistency_loss", "train_consistency_pairs", "train_reanalysis_coverage", "train_reanalysis_target_drift", "train_reanalysis_policy_drift"] },
          { key: "mcts", label: "MCTS", metrics: ["eval_decision_steps", "eval_policy_confidence_mean", "eval_policy_margin_mean", "eval_latent_signal_coverage", "eval_reaction_window_count", "eval_melee_attempts"] },
        ];
        function stateColor(statusName) {
          if (statusName === "complete") return "#22c55e";
          if (statusName === "partial") return "#f59e0b";
          return "#ef4444";
        }
        function summarizeRowCoverage(rowObj) {
          const srcRoot = (rowObj && rowObj.head_diagnostics_eval && typeof rowObj.head_diagnostics_eval === "object") ? rowObj.head_diagnostics_eval : {};
          const perHead = {};
          const reasons = [];
          const counts = { complete: 0, partial: 0, none: 0 };
          for (const spec of headSpecRows) {
            const src = (srcRoot && srcRoot[spec.key] && typeof srcRoot[spec.key] === "object") ? srcRoot[spec.key] : {};
            let available = 0;
            const missing = [];
            for (const mk of spec.metrics) {
              if (Object.prototype.hasOwnProperty.call(src, mk) && hasFiniteNumber(src[mk])) available += 1;
              else missing.push(mk);
            }
            let statusLocal = "none";
            if (available === spec.metrics.length && spec.metrics.length > 0) statusLocal = "complete";
            else if (available > 0) statusLocal = "partial";
            counts[statusLocal] += 1;
            let reason = String(src.telemetry_coverage_reason || src.reason || "").trim();
            if (!reason) {
              if (statusLocal === "complete") reason = "all expected metrics available";
              else if (statusLocal === "partial") reason = "missing metrics: " + missing.slice(0, 2).join(", ");
              else reason = "no eval telemetry for this head";
            }
            perHead[spec.key] = {
              status: statusLocal,
              available: available,
              total: spec.metrics.length,
              reason: reason,
            };
            if (statusLocal !== "complete") reasons.push(reason);
          }
          return {
            perHead: perHead,
            counts: counts,
            missingHeads: Object.keys(perHead).filter(function (k) { return String((perHead[k] || {}).status || "none") !== "complete"; }),
            reasons: reasons,
          };
        }
        function stateBreakdownCard(statusCounts, totalHeads, label) {
          const safeTotal = Math.max(1, Number(totalHeads || 0));
          function line(statusName) {
            const c = Number(statusCounts[statusName] || 0);
            return '<span style="display:inline-block;padding:3px 8px;border:1px solid #334155;border-radius:999px;color:' + stateColor(statusName) + ';margin-right:6px;">' +
              esc(statusName + "=" + String(c) + "/" + String(safeTotal) + " (" + ((c * 100) / safeTotal).toFixed(1) + "%)") +
              '</span>';
          }
          return '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<div style="font-weight:700;margin-bottom:6px;">' + esc(label) + '</div>' +
            line("complete") + line("partial") + line("none") +
            '</div>';
        }
        function topReasonsList(reasons, title) {
          const map = {};
          for (const r of (Array.isArray(reasons) ? reasons : [])) {
            const key = String(r || "").trim() || "unspecified reason";
            map[key] = Number(map[key] || 0) + 1;
          }
          const rows = Object.keys(map).map(function (k) { return [k, map[k]]; })
            .sort(function (a, b) { return Number(b[1] || 0) - Number(a[1] || 0); })
            .slice(0, 5);
          return intentTable(title, ["reason", "count"], rows, "No partial/none reasons.");
        }
        const intents = collectIntentSignals();
        function objectiveHeadMetric(metricName) {
          const v = getHeadMetric("objective", metricName);
          if (v !== null) return v;
          if (metricName === "eval_vp_immediate_capture_opportunity_steps") return getHeadMetric("objective", "eval_vp_capture_opportunity_steps");
          if (metricName === "eval_vp_immediate_capture_taken_steps") return getHeadMetric("objective", "eval_vp_capture_taken_steps");
          if (metricName === "eval_vp_immediate_capture_take_rate") return getHeadMetric("objective", "eval_vp_capture_take_rate");
          if (metricName === "eval_vp_immediate_conversion_efficiency") return getHeadMetric("objective", "eval_vp_conversion_efficiency");
          return v;
        }
        let html = '<div class="muted" style="margin-bottom:8px;">status=' + esc(status) + ' | rows_with_head_diag=' + esc(String(Math.round(Number(headDiag.n || 0)))) + '/' + esc(String(rowsTotal)) + '</div>';
        html += renderModelHealthPanel(evalRowsForTabs);
        if (status === "no data") {
          root.innerHTML = html + '<div class="muted">No eval head diagnostics found for current eval filters.</div>';
          return;
        }
        const overallBreakdownRows = [];
        const overallStateCounts = { complete: 0, partial: 0, none: 0 };
        const overallReasons = [];
        for (const spec of headSpecRows) {
          const cov = coverageForHead(spec.key, spec.metrics);
          overallStateCounts[cov.status] += 1;
          if (cov.status !== "complete") overallReasons.push(String(cov.reason || "unspecified reason"));
          overallBreakdownRows.push([
            spec.label,
            { __html: metricValueHtml(String(cov.status || "none"), { degradedSources: ["partial", "none", "unknown"] }) },
            String(Number(cov.available || 0)) + "/" + String(Number(cov.total || 0)),
            { __html: metricValueHtml(String(cov.reason || ""), { degradedSources: ["no eval telemetry for this head"] }) },
          ]);
        }
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start;margin-bottom:10px;">';
        html += stateBreakdownCard(overallStateCounts, headSpecRows.length, "Coverage state breakdown (heads)");
        html += '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
          '<div style="font-weight:700;margin-bottom:6px;">Coverage breakdown by head</div>' +
          '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
          '<th style="border:1px solid #334155;padding:6px;">head</th>' +
          '<th style="border:1px solid #334155;padding:6px;">status</th>' +
          '<th style="border:1px solid #334155;padding:6px;">metrics</th>' +
          '<th style="border:1px solid #334155;padding:6px;">reason</th>' +
          '</tr></thead><tbody>' + tableRows(overallBreakdownRows, ["head", "status", "metrics", "reason"], "No head diagnostics available.") + '</tbody></table>' +
          '</div>';
        html += topReasonsList(overallReasons, "Frequent partial/none reasons");
        html += '<div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
          '<div style="font-weight:700;margin-bottom:6px;">Decision Influence quick access</div>' +
          '<div class="muted" style="margin-bottom:6px;">Use replay for step-level influence; ownership uses policy_overridden_by_mcts from current telemetry.</div>' +
          '<div class="muted" style="margin-bottom:6px;">Ownership source coverage: override_signal_rows=' + esc(String(intents.ownershipSourceSummary.override_signal_rows || 0)) + ', unknown_override_rows=' + esc(String(intents.ownershipSourceSummary.unknown_override_rows || 0)) + '</div>' +
          '<button id="headDiagOpenReplayBtn" style="padding:4px 8px;font-size:12px;">Open Match Replay (Decision Influence)</button>' +
          intentTable(
            "MCTS decision ownership by side",
            ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "unknown_override_rows"],
            intents.mctsOwnershipRows,
            "No MCTS ownership signals in eval diagnostics."
          ) +
          '</div>';
        html += '</div>';
        if (rowsTotal > 1) {
          const rowOptions = evalRowsForTabs.map(function (r, idx) {
            const evalId = String((r && r.eval_id) || "n/a");
            const scenario = String((r && r.scenario_id) || "n/a");
            return '<option value="' + esc(String(idx)) + '">' + esc("row " + String(idx + 1) + " | eval " + evalId + " | " + scenario) + '</option>';
          }).join("");
          html += '<details open style="margin-bottom:10px;background:#0f172a;border:1px solid #334155;border-radius:8px;padding:8px;">' +
            '<summary style="cursor:pointer;font-weight:700;">Row/step telemetry inspector</summary>' +
            '<div class="muted" style="margin-top:6px;">Inspect row-level telemetry gaps here; use replay tab for per-step diagnostics.</div>' +
            '<label class="muted" style="display:block;margin-top:6px;">Row <select id="headDiagRowSelect" style="margin-left:6px;">' + rowOptions + '</select></label>' +
            '<div id="headDiagRowInspectorHost" style="margin-top:8px;"></div>' +
            '</details>';
        }
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start;">';
        const policyMetrics = [
          ["eval_decision_steps", fmtEvalNum(getHeadMetric("policy", "eval_decision_steps"), 1)],
          ["eval_confidence_mean", fmtEvalNum(getHeadMetric("policy", "eval_confidence_mean"), 4)],
          ["eval_margin_mean", fmtEvalNum(getHeadMetric("policy", "eval_margin_mean"), 4)],
          ["eval_latent_signal_coverage", fmtEvalPct(getHeadMetric("policy", "eval_latent_signal_coverage"))],
          ["train_policy_loss", fmtEvalNum(getHeadMetric("policy", "train_policy_loss"), 4)],
        ];
        const policyCoverage = coverageForHead("policy", headSpecRows[0].metrics);
        const policyIntentHtml = intentTable(
          "Top-k policy actions (eval_decisions_top)",
          ["action_id", "action_kind", "side", "share"],
          intents.topPolicyActions,
          "No top-k policy actions in eval/replay sources."
        );
        const policyConf = getHeadMetric("policy", "eval_confidence_mean");
        const policySummary = (policyConf === null)
          ? "Policy intent is unavailable for current filters (N/A)."
          : (policyConf >= 0.6
            ? "Policy focuses on dominant actions with high confidence."
            : "Policy explores multiple candidate actions.");
        html += headCard("Policy Head", policyCoverage, policySummary, policyMetrics, policyIntentHtml);

        const valueMetrics = [
          ["train_value_loss", fmtEvalNum(getHeadMetric("value", "train_value_loss"), 4)],
          ["eval_win_rate_proxy", fmtEvalPct(getHeadMetric("value", "eval_win_rate_proxy"))],
          ["eval_avg_return_proxy", fmtEvalNum(getHeadMetric("value", "eval_avg_return_proxy"), 4)],
        ];
        const valueCoverage = coverageForHead("value", headSpecRows[1].metrics);
        html += headCard("Value Head", valueCoverage, "Value estimates expected outcome for the active side.", valueMetrics, "");

        const rewardMetrics = [
          ["train_reward_loss", fmtEvalNum(getHeadMetric("reward", "train_reward_loss"), 4)],
          ["eval_avg_return_proxy", fmtEvalNum(getHeadMetric("reward", "eval_avg_return_proxy"), 4)],
          ["eval_avg_steps_proxy", fmtEvalNum(getHeadMetric("reward", "eval_avg_steps_proxy"), 2)],
        ];
        const rewardCoverage = coverageForHead("reward", headSpecRows[2].metrics);
        html += headCard("Reward Head", rewardCoverage, "Reward head estimates immediate gain/cost tendencies.", rewardMetrics, "");

        const objectiveMetrics = [
          ["train_objective_loss", fmtEvalNum(getHeadMetric("objective", "train_objective_loss"), 4)],
          ["eval_vp_capture_opportunity_steps (sum objective_had_opportunity)", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_opportunity_steps"), 1)],
          ["eval_vp_immediate_capture_opportunity_steps (MOVE into capturable VP legal now)", fmtEvalNum(objectiveHeadMetric("eval_vp_immediate_capture_opportunity_steps"), 1)],
          ["eval_vp_capture_taken_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_taken_steps"), 1)],
          ["eval_vp_immediate_capture_taken_steps", fmtEvalNum(objectiveHeadMetric("eval_vp_immediate_capture_taken_steps"), 1)],
          ["eval_vp_capture_take_rate", fmtEvalPct(getHeadMetric("objective", "eval_vp_capture_take_rate"))],
          ["eval_vp_immediate_capture_take_rate", fmtEvalPct(objectiveHeadMetric("eval_vp_immediate_capture_take_rate"))],
          ["eval_vp_conversion_efficiency", fmtEvalPct(getHeadMetric("objective", "eval_vp_conversion_efficiency"))],
          ["eval_vp_immediate_conversion_efficiency", fmtEvalPct(objectiveHeadMetric("eval_vp_immediate_conversion_efficiency"))],
          ["take_rate_denominator_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_capture_take_rate_denominator_steps"), 1)],
          ["conversion_efficiency_denominator_steps", fmtEvalNum(getHeadMetric("objective", "eval_vp_conversion_efficiency_denominator_steps"), 1)],
        ];
        const objectiveCoverage = coverageForHead("objective", headSpecRows[3].metrics);
        const objOpp = getHeadMetric("objective", "eval_vp_capture_opportunity_steps");
        const objTaken = getHeadMetric("objective", "eval_vp_capture_taken_steps");
        const objImmediateOpp = objectiveHeadMetric("eval_vp_immediate_capture_opportunity_steps");
        const objImmediateTaken = objectiveHeadMetric("eval_vp_immediate_capture_taken_steps");
        const objTakeRate = getHeadMetric("objective", "eval_vp_capture_take_rate");
        const objImmediateTakeRate = objectiveHeadMetric("eval_vp_immediate_capture_take_rate");
        const objTakeRateDen = getHeadMetric("objective", "eval_vp_capture_take_rate_denominator_steps");
        const objConvEffDen = getHeadMetric("objective", "eval_vp_conversion_efficiency_denominator_steps");
        function fmtObjectiveCount(v) {
          if (v === null || v === undefined) return "N/A";
          const n = Number(v);
          if (!Number.isFinite(n)) return "N/A";
          const rounded = Math.round(n);
          if (Math.abs(n - rounded) <= 1e-6) return String(rounded);
          return n.toFixed(1);
        }
        function fmtRateWithFraction(rate, num, den) {
          const rateTxt = fmtEvalPct(rate);
          const numTxt = fmtObjectiveCount(num);
          const denTxt = fmtObjectiveCount(den);
          if (rateTxt === "N/A") return "N/A";
          if (numTxt === "N/A" || denTxt === "N/A") return rateTxt + " (num/den unavailable)";
          return rateTxt + " (" + numTxt + " / " + denTxt + ")";
        }
        const objectiveIntentHtml = intentTable(
          "Objective intent signals",
          ["signal", "value", "aggregation/source"],
          [
            ["vp_capture_opportunities (objective_had_opportunity)", fmtObjectiveCount(objOpp), "mean across filtered result rows"],
            ["vp_immediate_capture_opportunities (legal MOVE-into-VP window)", fmtObjectiveCount(objImmediateOpp), "mean across filtered result rows"],
            ["vp_capture_taken", fmtObjectiveCount(objTaken), "mean across filtered result rows"],
            ["vp_immediate_capture_taken", fmtObjectiveCount(objImmediateTaken), "mean across filtered result rows"],
            ["vp_take_rate", fmtRateWithFraction(objTakeRate, objTaken, objOpp), "rate + displayed numerator/denominator"],
            ["vp_immediate_take_rate", fmtRateWithFraction(objImmediateTakeRate, objImmediateTaken, objImmediateOpp), "rate + displayed numerator/denominator"],
            ["vp_capture_take_rate_denominator_steps", fmtObjectiveCount(objTakeRateDen), "mean across filtered result rows"],
            ["vp_conversion_efficiency_denominator", fmtObjectiveCount(objConvEffDen), "mean across filtered result rows"],
          ],
          "No objective intent signals in eval telemetry."
        );
        const objectiveSummary = (objOpp === null || objTaken === null)
          ? "Objective intent is unavailable for current filters (N/A)."
          : (objOpp > 0 && objTaken > 0
            ? "Objective head identifies and converts VP opportunities."
            : "Objective head sees VP opportunities but conversion is limited.");
        html += headCard("Objective Head", objectiveCoverage, objectiveSummary, objectiveMetrics, objectiveIntentHtml);

        const consistencyMetrics = [
          ["train_consistency_loss", fmtEvalNum(getHeadMetric("consistency", "train_consistency_loss"), 4)],
          ["train_consistency_pairs", fmtEvalNum(getHeadMetric("consistency", "train_consistency_pairs"), 1)],
          ["train_reanalysis_coverage", fmtEvalPct(getHeadMetric("consistency", "train_reanalysis_coverage"))],
          ["train_reanalysis_target_drift", fmtEvalNum(getHeadMetric("consistency", "train_reanalysis_target_drift"), 4)],
          ["train_reanalysis_policy_drift", fmtEvalNum(getHeadMetric("consistency", "train_reanalysis_policy_drift"), 4)],
        ];
        const consistencyCoverage = coverageForHead("consistency", headSpecRows[4].metrics);
        html += headCard("Consistency Head", consistencyCoverage, "Consistency tracks latent stability under reanalysis.", consistencyMetrics, "");

        const mctsMetrics = [
          ["eval_decision_steps", fmtEvalNum(getHeadMetric("mcts", "eval_decision_steps"), 1)],
          ["eval_policy_confidence_mean", fmtEvalNum(getHeadMetric("mcts", "eval_policy_confidence_mean"), 4)],
          ["eval_policy_margin_mean", fmtEvalNum(getHeadMetric("mcts", "eval_policy_margin_mean"), 4)],
          ["eval_latent_signal_coverage", fmtEvalPct(getHeadMetric("mcts", "eval_latent_signal_coverage"))],
          ["eval_reaction_window_count", fmtEvalNum(getHeadMetric("mcts", "eval_reaction_window_count"), 1)],
          ["eval_melee_attempts", fmtEvalNum(getHeadMetric("mcts", "eval_melee_attempts"), 1)],
        ];
        const mctsCoverage = coverageForHead("mcts", headSpecRows[5].metrics);
        const mctsIntentHtml = intentTable(
          "MCTS decision ownership by side",
          ["side", "rows", "policy_kept", "overwritten", "override_signal_rows", "unknown_override_rows"],
          intents.mctsOwnershipRows,
          "No MCTS ownership signals in eval diagnostics."
        );
        const mctsMargin = getHeadMetric("mcts", "eval_policy_margin_mean");
        const mctsSummary = (mctsMargin === null)
          ? "MCTS intent is unavailable for current filters (N/A)."
          : (mctsMargin >= 0.25
            ? "MCTS converges on a dominant line."
            : "MCTS keeps meaningful alternatives open.");
        html += headCard("MCTS Diagnostics", mctsCoverage, mctsSummary, mctsMetrics, mctsIntentHtml);
        html += '</div>';
        root.innerHTML = html;
        const openReplayBtn = document.getElementById("headDiagOpenReplayBtn");
        if (openReplayBtn) {
          openReplayBtn.onclick = function () {
            switchTab("replay");
          };
        }
        function renderSelectedRowCoverage(rowIndexRaw) {
          const inspectorHost = document.getElementById("headDiagRowInspectorHost");
          if (!inspectorHost) return;
          const rows = Array.isArray(evalRowsForTabs) ? evalRowsForTabs : [];
          if (!rows.length) {
            inspectorHost.innerHTML = '<div class="muted">No rows to inspect.</div>';
            return;
          }
          const rowIndex = Math.max(0, Math.min(rows.length - 1, Number(rowIndexRaw || 0)));
          const rowObj = rows[rowIndex] || {};
          const rowSummary = summarizeRowCoverage(rowObj);
          const breakdownRows = headSpecRows.map(function (spec) {
            const c = rowSummary.perHead[spec.key] || { status: "none", available: 0, total: spec.metrics.length, reason: "no eval telemetry for this head" };
            return [spec.label, c.status, String(Number(c.available || 0)) + "/" + String(Number(c.total || 0)), c.reason];
          });
          const missingTxt = rowSummary.missingHeads.length
            ? rowSummary.missingHeads.map(function (k) { return String(k || "").toUpperCase(); }).join(", ")
            : "none";
          inspectorHost.innerHTML =
            stateBreakdownCard(rowSummary.counts, headSpecRows.length, "Selected row coverage states") +
            '<div style="margin-top:8px;">' +
              '<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>' +
                '<th style="border:1px solid #334155;padding:6px;">head</th>' +
                '<th style="border:1px solid #334155;padding:6px;">status</th>' +
                '<th style="border:1px solid #334155;padding:6px;">metrics</th>' +
                '<th style="border:1px solid #334155;padding:6px;">reason</th>' +
              '</tr></thead><tbody>' + tableRows(breakdownRows, ["head", "status", "metrics", "reason"], "No row telemetry.") + '</tbody></table>' +
            '</div>' +
            '<div class="muted" style="margin-top:6px;">Missing/partial heads: ' + esc(missingTxt) + '</div>' +
            topReasonsList(rowSummary.reasons, "Frequent reasons in selected row");
        }
        const rowSelect = document.getElementById("headDiagRowSelect");
        if (rowSelect) {
          rowSelect.onchange = function () {
            renderSelectedRowCoverage(Number(rowSelect.value || 0));
          };
          renderSelectedRowCoverage(Number(rowSelect.value || 0));
        }
      }
"""
