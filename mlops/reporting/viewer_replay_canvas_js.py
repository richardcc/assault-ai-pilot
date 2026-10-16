from __future__ import annotations


def replay_canvas_helpers_js() -> str:
    return """
    function oddRRaw(q, r) {
      const qn = Number(q || 0);
      const rn = Number(r || 0);
      return {
        // Match assault_ai_ui axialToPixel with HEX_WIDTH=sqrt(3)*HEX_SIZE and HEX_HEIGHT=1.5*HEX_SIZE.
        x: Math.sqrt(3) * (qn + 0.5 * (rn % 2)) + (Math.sqrt(3) / 2),
        y: 1.5 * rn + 1.0,
      };
    }
    function makeProjection(baseCells, w, h, pad) {
      const cells = Array.isArray(baseCells) && baseCells.length
        ? baseCells
        // Defensive guard: never use pixel width/height as cell counts.
        : Array.from({ length: 12 }, (_, rr) =>
            Array.from({ length: 18 }, (_, qq) => ({ q: qq, r: rr }))
          ).flat();
      const raws = cells.map((c) => oddRRaw(Number(c.q || 0), Number(c.r || 0)));
      let minX = Number.POSITIVE_INFINITY;
      let maxX = Number.NEGATIVE_INFINITY;
      let minY = Number.POSITIVE_INFINITY;
      let maxY = Number.NEGATIVE_INFINITY;
      for (const p of raws) {
        minX = Math.min(minX, Number(p.x || 0));
        maxX = Math.max(maxX, Number(p.x || 0));
        minY = Math.min(minY, Number(p.y || 0));
        maxY = Math.max(maxY, Number(p.y || 0));
      }
      const spanX = Math.max(1e-9, maxX - minX);
      const spanY = Math.max(1e-9, maxY - minY);
      // Fit by cell centers + one full hex radius margin on each side.
      const spanXWithMargin = spanX + 2.0;
      const spanYWithMargin = spanY + 2.0;
      const scale = Math.min((w - 2 * pad) / spanXWithMargin, (h - 2 * pad) / spanYWithMargin);
      const offsetX = (w - spanXWithMargin * scale) / 2;
      const offsetY = (h - spanYWithMargin * scale) / 2;
      // Exact sb3-style hex geometry: radius ~= center spacing scale.
      const hexRadius = Math.max(2.0, scale);
      const toPixel = (q, r) => {
        const raw = oddRRaw(q, r);
        return {
          x: offsetX + (raw.x - minX + 1.0) * scale,
          y: offsetY + (raw.y - minY + 1.0) * scale,
        };
      };
      return { toPixel, hexRadius };
    }
    function drawHex(ctx, cx, cy, size, stroke, fill) {
      ctx.beginPath();
      for (let i = 0; i < 6; i += 1) {
        const a = (Math.PI / 180) * (60 * i - 30);
        const x = cx + size * Math.cos(a);
        const y = cy + size * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    function drawHexCoordLabel(ctx, cx, cy, size, q, r) {
      const qn = Math.round(Number(q || 0));
      const rn = Math.round(Number(r || 0));
      ctx.fillStyle = "rgba(148,163,184,0.82)";
      ctx.font = String(Math.max(8, Math.floor(size * 0.28))) + "px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      const labelX = cx - size * 0.62;
      const labelY = cy - size * 0.52;
      ctx.fillText("(" + String(qn) + "," + String(rn) + ")", labelX, labelY);
    }
    function replayActionKindFromId(actionId) {
      return String(actionId || "").split(":")[0].trim().toUpperCase();
    }
    function replayActionUnitFromId(actionId) {
      const parts = String(actionId || "").split(":");
      return String(parts.length > 1 ? parts[1] : "").trim();
    }
    function replayActionHexFromRaw(raw) {
      if (!raw || typeof raw !== "object") return null;
      const qKeys = ["target_q", "to_q", "action_target_q", "hex_q"];
      const rKeys = ["target_r", "to_r", "action_target_r", "hex_r"];
      for (let i = 0; i < Math.min(qKeys.length, rKeys.length); i += 1) {
        const q = Number(raw[qKeys[i]]);
        const r = Number(raw[rKeys[i]]);
        if (Number.isFinite(q) && Number.isFinite(r)) return { q, r };
      }
      const actionId = String(raw.action_id || raw.id || "");
      const parts = actionId.split(":");
      if (parts.length >= 4) {
        const q = Number(parts[2]);
        const r = Number(parts[3]);
        if (Number.isFinite(q) && Number.isFinite(r)) return { q, r };
      }
      return null;
    }
    function replayCollectCanonicalActionCandidates(stepRow) {
      const out = [];
      const pushActionLike = function (raw) {
        if (raw === null || raw === undefined) return;
        if (typeof raw === "string") {
          out.push({ action_id: raw });
          return;
        }
        if (raw && typeof raw === "object") out.push(raw);
      };
      const directLists = [
        stepRow && stepRow.legal_actions,
        stepRow && stepRow.legal_action_ids,
        stepRow && stepRow.legal_actions_decoded_target_qr,
        stepRow && stepRow.acting_unit_action_catalog,
        stepRow && stepRow.mcts_action_candidates,
        stepRow && stepRow.why_action_vs_vp && stepRow.why_action_vs_vp.candidate_actions,
      ];
      for (const src of directLists) {
        if (!Array.isArray(src)) continue;
        for (const item of src) pushActionLike(item);
      }
      return out;
    }
    function replayCandidateActorUnit(cand) {
      if (!cand || typeof cand !== "object") return "";
      const actionId = String((cand && cand.action_id) || cand.id || "");
      const explicitActorUnits = [
        String((cand && cand.unit_id) || "").trim(),
        String((cand && cand.actor_unit_id) || "").trim(),
        String((cand && cand.source_unit_id) || "").trim(),
      ].filter(Boolean);
      const uniqueExplicit = Array.from(new Set(explicitActorUnits));
      if (uniqueExplicit.length > 1) return "";
      const explicitActor = uniqueExplicit.length ? uniqueExplicit[0] : "";
      const derivedActor = String(replayActionUnitFromId(actionId) || "").trim();
      if (derivedActor && explicitActor && derivedActor !== explicitActor) return "";
      return explicitActor || derivedActor;
    }
    function replayCollectUnitHexCandidates(stepRow, hoveredUnitId) {
      const wanted = String(hoveredUnitId || "").trim();
      const empty = { moveHexes: [], attackHexes: [] };
      if (!wanted || !stepRow || typeof stepRow !== "object") return empty;
      const moveMap = {};
      const attackMap = {};
      const addHex = function (bucket, q, r) {
        if (!Number.isFinite(Number(q)) || !Number.isFinite(Number(r))) return;
        const qn = Number(q);
        const rn = Number(r);
        bucket[String(qn) + "," + String(rn)] = { q: qn, r: rn };
      };
      const moveKind = function (kind) {
        const k = String(kind || "").toUpperCase();
        return k === "MOVE" || k === "ADVANCE" || k === "REDEPLOY";
      };
      const attackKind = function (kind) {
        const k = String(kind || "").toUpperCase();
        return k.indexOf("FIRE") >= 0 || k.indexOf("ATTACK") >= 0 || k.indexOf("MELEE") >= 0;
      };
      const actionCandidates = replayCollectCanonicalActionCandidates(stepRow);
      for (const cand of actionCandidates) {
        const actionId = String((cand && cand.action_id) || cand.id || "");
        const kind = String((cand && (cand.action_kind || cand.kind)) || replayActionKindFromId(actionId));
        const actionUnit = replayCandidateActorUnit(cand);
        if (!actionUnit || actionUnit !== wanted) continue;
        const hex = replayActionHexFromRaw(cand);
        if (!hex) continue;
        if (moveKind(kind)) addHex(moveMap, hex.q, hex.r);
        else if (attackKind(kind)) addHex(attackMap, hex.q, hex.r);
      }
      return {
        moveHexes: Object.values(moveMap),
        attackHexes: Object.values(attackMap),
      };
    }
    function replayBindCanvasHoverHandlers(canvas) {
      if (!canvas) return;
      if (replayState.hoverCanvasBound && replayState.hoverCanvasEl === canvas) return;
      canvas.onmousemove = function (ev) {
        const rectLocal = canvas.getBoundingClientRect();
        const mx = Number(ev.clientX || 0) - Number(rectLocal.left || 0);
        const my = Number(ev.clientY || 0) - Number(rectLocal.top || 0);
        const points = Array.isArray(replayState.hoverHitPoints) ? replayState.hoverHitPoints : [];
        const hitRadius = Math.max(6, Number(replayState.hoverHitRadius || 6));
        let hitUnit = "";
        for (const u of points) {
          const dx = Number(u.x || 0) - mx;
          const dy = Number(u.y || 0) - my;
          if ((dx * dx + dy * dy) <= (hitRadius * hitRadius)) {
            hitUnit = String(u.unit_id || "");
            break;
          }
        }
        if (typeof window !== "undefined" && typeof window.setReplayHoveredUnit === "function") {
          window.setReplayHoveredUnit(hitUnit);
        }
      };
      canvas.onmouseleave = function () {
        if (typeof window !== "undefined" && typeof window.setReplayHoveredUnit === "function") {
          window.setReplayHoveredUnit("");
        }
      };
      replayState.hoverCanvasEl = canvas;
      replayState.hoverCanvasBound = true;
    }
    function drawReplayCanvasFrame(ctx, cssW, cssH, stepRow) {
      const allStepUnits = Array.isArray(stepRow && stepRow.units) ? stepRow.units : [];
      const selectedUnitId = String(replayState.unitFilter || "__all__");
      const units = selectedUnitId === "__all__"
        ? allStepUnits
        : allStepUnits.filter(function (u) { return String((u && u.unit_id) || "") === selectedUnitId; });
      const unitCoords = [];
      const qs = [];
      const rs = [];
      for (const u of units) {
        const uq = Number(u && u.q);
        const ur = Number(u && u.r);
        if (!Number.isFinite(uq) || !Number.isFinite(ur)) continue;
        const uc = Object.assign({}, u, { q: Number(u.q || 0), r: Number(u.r || 0) });
        unitCoords.push(uc);
        qs.push(Number(uc.q || 0));
        rs.push(Number(uc.r || 0));
      }
      const hasStepObj = !!stepRow && typeof stepRow === "object";
      const rawTargetQ = hasStepObj ? stepRow.target_q : null;
      const rawTargetR = hasStepObj ? stepRow.target_r : null;
      const tQ = Number.isFinite(Number(rawTargetQ)) ? Number(rawTargetQ) : null;
      const tR = Number.isFinite(Number(rawTargetR)) ? Number(rawTargetR) : null;
      if (tQ !== null && tR !== null) { qs.push(tQ); rs.push(tR); }
      const overlay = (replayState.payload && replayState.payload.scenario_overlay) || {};
      const shape = Array.isArray(overlay.shape) ? overlay.shape : [];
      const vpHexes = Array.isArray(overlay.vp_hexes) ? overlay.vp_hexes : [];
      const mapCellsOverlay = Array.isArray(overlay.map_cells) ? overlay.map_cells : [];
      const minQ = (qs.length ? Math.min(...qs) : 0) - 2;
      const maxQ = (qs.length ? Math.max(...qs) : 8) + 2;
      const minR = (rs.length ? Math.min(...rs) : 0) - 2;
      const maxR = (rs.length ? Math.max(...rs) : 8) + 2;
      const baseCells = [];
      if (mapCellsOverlay.length > 0) {
        for (const c of mapCellsOverlay) {
          const q = Number(c && c.q);
          const r = Number(c && c.r);
          if (Number.isFinite(q) && Number.isFinite(r)) baseCells.push({ q, r });
        }
      }
      if (!baseCells.length && shape.length >= 2 && Number(shape[0]) > 0 && Number(shape[1]) > 0) {
        const wCells = Math.max(1, Number(shape[0]));
        const hCells = Math.max(1, Number(shape[1]));
        for (let r = 0; r < hCells; r += 1) {
          for (let q = 0; q < wCells; q += 1) {
            baseCells.push({ q, r });
          }
        }
      }
      if (!baseCells.length) {
        for (let q = minQ; q <= maxQ; q += 1) {
          for (let r = minR; r <= maxR; r += 1) {
            baseCells.push({ q, r });
          }
        }
      }
      const proj = makeProjection(baseCells, cssW, cssH, 8);
      const size = proj.hexRadius;
      for (const c of baseCells) {
        const p = proj.toPixel(c.q, c.r);
        drawHex(ctx, p.x, p.y, size, "#263244", "rgba(15,23,42,0.35)");
        drawHexCoordLabel(ctx, p.x, p.y, size, c.q, c.r);
      }
      const hoverUnitId = String(replayState.hoveredUnitId || "").trim();
      const selectedUnitIdForOverlay = String(replayState.unitFilter || "__all__").trim();
      const activeUnitId = String((stepRow && stepRow.unit_id) || "").trim();
      const effectiveUnitId = (
        hoverUnitId ||
        (selectedUnitIdForOverlay !== "__all__" ? selectedUnitIdForOverlay : "") ||
        activeUnitId
      );
      const overlayHexes = replayCollectUnitHexCandidates(stepRow, effectiveUnitId);
      const moveHexes = Array.isArray(overlayHexes.moveHexes) ? overlayHexes.moveHexes : [];
      const attackHexes = Array.isArray(overlayHexes.attackHexes) ? overlayHexes.attackHexes : [];
      for (const hx of moveHexes) {
        const q = Number(hx && hx.q);
        const r = Number(hx && hx.r);
        if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
        const p = proj.toPixel(q, r);
        drawHex(ctx, p.x, p.y, size * 1.03, "#22c55e", "rgba(34,197,94,0.24)");
      }
      for (const hx of attackHexes) {
        const q = Number(hx && hx.q);
        const r = Number(hx && hx.r);
        if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
        const p = proj.toPixel(q, r);
        drawHex(ctx, p.x, p.y, size * 1.03, "#ef4444", "rgba(239,68,68,0.20)");
      }
      const points = [];
      for (const u of unitCoords) {
        const px = proj.toPixel(u.q, u.r);
        points.push(Object.assign({}, u, px));
      }
      replayState.hoverHitPoints = points;
      replayState.hoverHitRadius = Math.max(6, size * 0.58);
      for (const p of points) {
        drawHex(ctx, p.x, p.y, size, "#334155", "rgba(15,23,42,0.45)");
      }
      for (const u of points) {
        const isIT = String(u.side || "").toUpperCase() === "IT";
        ctx.beginPath();
        ctx.arc(u.x, u.y, Math.max(4, size * 0.42), 0, Math.PI * 2);
        ctx.fillStyle = isIT ? "#f97316" : "#38bdf8";
        if (!Boolean(u.alive)) ctx.fillStyle = "#64748b";
        ctx.fill();
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 1.2;
        ctx.stroke();
        ctx.fillStyle = "#e2e8f0";
        ctx.font = String(Math.max(9, Math.floor(size * 0.58))) + "px sans-serif";
        ctx.fillText(String(u.unit_id || ""), u.x + size * 0.65, u.y + 3);
      }
      if (
        hasStepObj &&
        Number.isFinite(Number(rawTargetQ)) &&
        Number.isFinite(Number(rawTargetR)) &&
        Number((stepRow.attack_distance_mean === undefined || stepRow.attack_distance_mean === null) ? -1 : stepRow.attack_distance_mean) >= 0
      ) {
        const t = proj.toPixel(Number(rawTargetQ), Number(rawTargetR));
        drawHex(ctx, t.x, t.y, size * 1.08, "#facc15", "rgba(250,204,21,0.10)");
      }
      for (const vp of vpHexes) {
        const q = Number(vp && vp.q);
        const r = Number(vp && vp.r);
        if (!Number.isFinite(q) || !Number.isFinite(r)) continue;
        const p = proj.toPixel(q, r);
        const vpMap = (stepRow && typeof stepRow.vp_map === "object" && stepRow.vp_map) ? stepRow.vp_map : {};
        const keyA = String(Math.trunc(q)) + "," + String(Math.trunc(r));
        const keyB = String(Math.trunc(q)) + "|" + String(Math.trunc(r));
        const keyC = "(" + String(Math.trunc(q)) + "," + String(Math.trunc(r)) + ")";
        const ownerRaw = (vpMap && (vpMap[keyA] ?? vpMap[keyB] ?? vpMap[keyC])) ?? (vp && vp.initial_owner);
        const owner = String(ownerRaw || "").toUpperCase();
        const ownerColor = owner === "IT" ? "#fb923c" : (owner === "US" ? "#38bdf8" : "#facc15");
        drawHex(ctx, p.x, p.y, size * 1.12, "#facc15", "rgba(250,204,21,0.06)");
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(3, size * 0.22), 0, Math.PI * 2);
        ctx.fillStyle = ownerColor;
        ctx.fill();
        ctx.strokeStyle = "#0f172a";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      const legend = document.getElementById("replayHoverLegend");
      if (legend) {
        if (effectiveUnitId) {
          const sourceLabel = hoverUnitId
            ? "hover"
            : (selectedUnitIdForOverlay !== "__all__" ? "selected" : "active");
          legend.title = sourceLabel + " unit=" + effectiveUnitId + " | move=" + String(moveHexes.length) + " | attack=" + String(attackHexes.length);
        } else {
          legend.title = "Hover a unit to preview move/attack hexes";
        }
      }
    }
"""
