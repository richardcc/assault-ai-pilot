from __future__ import annotations


def replay_units_snapshot_helpers_js() -> str:
    return """
    function parseSuppressedValue(raw) {
      if (raw === null || raw === undefined || raw === "") return null;
      if (typeof raw === "boolean") return raw;
      if (typeof raw === "number") return Number.isFinite(raw) ? (raw !== 0) : null;
      const txt = String(raw).trim().toLowerCase();
      if (!txt) return null;
      if (txt === "1" || txt === "true" || txt === "yes" || txt === "y" || txt === "on") return true;
      if (txt === "0" || txt === "false" || txt === "no" || txt === "n" || txt === "off") return false;
      return null;
    }

    function formatSuppressedLabel(value) {
      return value === null ? "N/A" : (value ? "true" : "false");
    }

    function suppressedValueForUnit(stepRowObj, unitObj) {
      const unitId = String((unitObj && unitObj.unit_id) || "").trim();
      const mapRaw = (stepRowObj && typeof stepRowObj === "object")
        ? stepRowObj.unit_suppressed_map
        : null;
      if (mapRaw && typeof mapRaw === "object" && unitId && Object.prototype.hasOwnProperty.call(mapRaw, unitId)) {
        const mapped = parseSuppressedValue(mapRaw[unitId]);
        if (mapped !== null) return mapped;
      }
      if (!unitObj || typeof unitObj !== "object") return null;
      const producerKeys = ["suppressed", "is_suppressed", "pinned", "is_pinned"];
      for (const key of producerKeys) {
        if (!Object.prototype.hasOwnProperty.call(unitObj, key)) continue;
        const parsed = parseSuppressedValue(unitObj[key]);
        if (parsed !== null) return parsed;
      }
      return null;
    }

    function buildReplayUnitsSnapshotHtml(stepRowObj, selectedUnitId) {
      const allStepUnits = Array.isArray(stepRowObj && stepRowObj.units) ? stepRowObj.units : [];
      const unitFilter = String(selectedUnitId || "__all__");
      const units = unitFilter === "__all__"
        ? allStepUnits
        : allStepUnits.filter(function (u) { return String((u && u.unit_id) || "") === unitFilter; });

      let unitsHtml = '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
        '<thead><tr>' +
        '<th style="border:1px solid #334155;padding:6px;">side</th>' +
        '<th style="border:1px solid #334155;padding:6px;">unit_id</th>' +
        '<th style="border:1px solid #334155;padding:6px;">unit</th>' +
        '<th style="border:1px solid #334155;padding:6px;">hex</th>' +
        '<th style="border:1px solid #334155;padding:6px;">hp</th>' +
        '<th style="border:1px solid #334155;padding:6px;">alive</th>' +
        '<th style="border:1px solid #334155;padding:6px;">suppressed</th>' +
        '</tr></thead><tbody>';
      if (!units.length) {
        unitsHtml += '<tr><td colspan="7" style="border:1px solid #334155;padding:6px;" class="muted">No units for selected filter.</td></tr>';
      } else {
        for (const u of units) {
          const hex = String(u.q) + "," + String(u.r);
          const unitWithId = String(u.unit_id || "") + " - " + String(u.unit_label || u.unit_key || "");
          const suppressedLabel = formatSuppressedLabel(suppressedValueForUnit(stepRowObj, u));
          unitsHtml += '<tr>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(u.side) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(u.unit_id) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(unitWithId) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(hex) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Number(u.hp || 0).toFixed(1)) + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(Boolean(u.alive) ? "yes" : "no") + '</td>' +
            '<td style="border:1px solid #334155;padding:6px;">' + esc(suppressedLabel) + '</td>' +
            '</tr>';
        }
      }
      unitsHtml += '</tbody></table>';
      return unitsHtml;
    }
"""
