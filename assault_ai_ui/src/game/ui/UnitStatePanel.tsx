import { useEffect, useState } from "react";
import { unitImages } from "../config/unitImages";
import { UnitCardTooltip } from "./UnitCardTooltip";
import { sides } from "../config/sides";
import { formatCoords } from "../render/hexGridRenderer";
import { actionMarkerImages, getUnitActionMarker } from "../state/actionMarkers";

type Unit = {
  id: string;
  unit_key: string;
  side: string;
  hp?: number;
  max_hp?: number;
  health_pct?: number;
  tactical_role?: string;
  has_indirect_fire?: boolean;
  is_suppression_mg?: boolean;
  is_assault_squad?: boolean;
  alive?: boolean;
  q: number;
  r: number;
};

type Props = {
  units: Unit[];
  activeSide?: string;
  activatedUnits?: string[];
  selectedUnitId?: string | null;
  targetUnitId?: string | null;
  onSelectUnit?: (unit: Unit) => void;
};

export function UnitStatePanel({
  units,
  activeSide,
  activatedUnits = [],
  selectedUnitId,
  targetUnitId,
  onSelectUnit
}: Props) {
  const [layoutMode, setLayoutMode] = useState<"row1" | "row2" | "v1" | "v2">(() => {
    try {
      const raw = localStorage.getItem("assault.units.layoutMode");
      if (raw === "row1" || raw === "row2" || raw === "v1" || raw === "v2") {
        return raw;
      }
    } catch {
      // ignore storage read errors
    }
    return "row1";
  });

  const [cardPreview, setCardPreview] = useState<{
    unit: Unit;
    x: number;
    y: number;
  } | null>(null);

  useEffect(() => {
    const onSave = () => {
      try {
        localStorage.setItem("assault.units.layoutMode", layoutMode);
      } catch {
        // ignore storage write errors
      }
    };
    window.addEventListener("assault:save-layout", onSave as EventListener);
    return () => {
      window.removeEventListener("assault:save-layout", onSave as EventListener);
    };
  }, [layoutMode]);

  const unitsBySide: Record<string, Unit[]> = {};

  for (const u of units) {
    if (!unitsBySide[u.side]) {
      unitsBySide[u.side] = [];
    }
    unitsBySide[u.side].push(u);
  }
  const sideEntries = Object.entries(unitsBySide).sort(([a], [b]) => a.localeCompare(b));

  // Handle clicking a trooper card
  const handleCardClick = (u: Unit) => {
    const dead = u.hp != null && u.hp <= 0;

    if (typeof (window as any).focusUnit === "function") {
      (window as any).focusUnit(u.id);
    }

    if (dead) {
      return;
    }

    if (onSelectUnit) {
      onSelectUnit(u);
    } else if (typeof (window as any).onUnitClick === "function") {
      (window as any).onUnitClick(u);
    }
  };

  return (
  <>
    {cardPreview && (
      <UnitCardTooltip
        key={cardPreview.unit.id}
        unitKey={cardPreview.unit.unit_key}
        hp={cardPreview.unit.hp}
        anchorX={cardPreview.x}
        anchorY={cardPreview.y}
      />
    )}

    <div className="roster-layout-toolbar">
      <button
        className={`btn-tactical roster-layout-btn ${layoutMode === "row1" ? "active" : ""}`}
        onClick={() => setLayoutMode("row1")}
        title="Una fila horizontal"
      >
        1 fila
      </button>
      <button
        className={`btn-tactical roster-layout-btn ${layoutMode === "row2" ? "active" : ""}`}
        onClick={() => setLayoutMode("row2")}
        title="Dos filas horizontales"
      >
        2 filas
      </button>
      <button
        className={`btn-tactical roster-layout-btn ${layoutMode === "v1" ? "active" : ""}`}
        onClick={() => setLayoutMode("v1")}
        title="Vertical una columna"
      >
        Vertical 1 col
      </button>
      <button
        className={`btn-tactical roster-layout-btn ${layoutMode === "v2" ? "active" : ""}`}
        onClick={() => setLayoutMode("v2")}
        title="Vertical dos columnas"
      >
        Vertical 2 col
      </button>
    </div>
    <div className={`roster-container roster-layout-${layoutMode}`}>
      {sideEntries.map(([side, list]) => (
        <div key={side} className="roster-side-group">
          {/* FLAG + UNITS IN SAME ROW */}
          <div className="roster-list">
            <div className="roster-side-badge" title={sides[side]?.short_label || side}>
              {sides[side]?.marker && (
                <img
                  src={encodeURI(sides[side].marker)}
                  className="roster-side-flag"
                  alt={side}
                />
              )}
              <div className="roster-side-name">
                {sides[side]?.short_label || side}
              </div>
            </div>
            <div className="roster-side-units">
            {list.map((u) => {
              const def = unitImages[u.unit_key as keyof typeof unitImages];
              const dead =
                u.alive === false || (u.hp != null && u.hp <= 0);
              const isOwn = u.side === activeSide;
              const isAvailable = isOwn && !activatedUnits.includes(u.id) && !dead;
              const isSelected = u.id === selectedUnitId;
              const isTarget = targetUnitId != null && u.id === targetUnitId;
              const deadMarker = dead ? sides[u.side]?.dead_marker : undefined;
              const actionMarker = getUnitActionMarker(u.id);

              // Compute CSS class names based on unit status
              let cardClass = "trooper-card";
              if (isSelected) {
                cardClass += " selected";
              }
              if (isTarget) {
                cardClass += " target-highlight";
              }
              
              if (dead) {
                cardClass += " dead";
              } else if (!isOwn) {
                cardClass += " enemy";
              } else if (!isAvailable) {
                cardClass += " ally-used";
              } else {
                cardClass += " ally-available";
                if (activeSide === "GE") {
                  cardClass += " active-GE";
                }
              }

              return (
                <div
                  key={u.id}
                  onMouseEnter={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    setCardPreview({
                      unit: u,
                      x: rect.left + rect.width / 2,
                      y: rect.top,
                    });
                    if (typeof (window as any).highlightUnit === "function") {
                      (window as any).highlightUnit(u.id);
                    }
                  }}
                  onMouseLeave={() => {
                    setCardPreview(null);
                    if (typeof (window as any).highlightUnit === "function") {
                      (window as any).highlightUnit(null);
                    }
                  }}
                  onClick={() => handleCardClick(u)}
                  className={cardClass}
                  title={`Coords: ${formatCoords(u.q, u.r)}`}
                >
                  {/* IMAGE */}
                  {def?.full && (
                    <div className="trooper-card-img-wrapper">
                      <img
                        src={encodeURI(def.full)}
                        className={`trooper-card-img${dead ? " dead" : ""}`}
                        alt={def?.label || u.unit_key}
                      />
                      {deadMarker && (
                        <img
                          src={encodeURI(deadMarker)}
                          className="trooper-card-dead-marker"
                          alt="Dead marker"
                        />
                      )}
                      {!dead && actionMarker && (
                        <img
                          src={encodeURI(actionMarkerImages[actionMarker])}
                          className="trooper-card-action-marker"
                          alt={`Action marker ${actionMarker}`}
                        />
                      )}
                    </div>
                  )}

                  {/* LABEL */}
                  <div className="trooper-card-label">
                    {def?.label || u.unit_key}
                  </div>

                  {/* ID */}
                  <div className="trooper-card-id">
                    {u.id}
                  </div>

                  {/* TACTICAL ROLE BADGES */}
                  <div style={{ display: "flex", gap: 3, margin: "2px 0", flexWrap: "wrap", justifyContent: "center" }}>
                    {(u.has_indirect_fire || u.tactical_role === "indirect_mortar") && (
                      <span
                        style={{ fontSize: 9, background: "#7c2d12", color: "#fdba74", padding: "1px 4px", borderRadius: 3, fontWeight: "bold" }}
                        title="Fuego Indirecto: Sin LOS requerida / Mortero"
                      >
                        💥 MORTERO
                      </span>
                    )}
                    {(u.is_suppression_mg || u.tactical_role === "suppression_mg") && (
                      <span
                        style={{ fontSize: 9, background: "#1e3a8a", color: "#93c5fd", padding: "1px 4px", borderRadius: 3, fontWeight: "bold" }}
                        title="Fuego de Supresión: HMG alcance > 6"
                      >
                        🛡️ HMG
                      </span>
                    )}
                    {(u.is_assault_squad || u.tactical_role === "assault_squad") && (
                      <span
                        style={{ fontSize: 9, background: "#14532d", color: "#86efac", padding: "1px 4px", borderRadius: 3, fontWeight: "bold" }}
                        title="Escuadra de Asalto y Brecha"
                      >
                        ⚔️ ASALTO
                      </span>
                    )}
                  </div>

                  {/* HP + NORMALIZED TACTICAL HEALTH BAR */}
                  <div className="trooper-card-hp-row" style={{ flexDirection: "column", gap: 2 }}>
                    <div className="trooper-card-hp" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                      {dead ? (
                        <span style={{ color: "#ff3838", fontWeight: 700 }}>DEAD (0%)</span>
                      ) : u.hp != null ? (
                        <>
                          <span>
                            {Array.from({ length: u.hp }).map((_, i) => (
                              <span key={i} style={{ color: "#ff3838" }}>❤️</span>
                            ))}
                          </span>
                          <span style={{ fontSize: 10, color: (u.health_pct ?? 1.0) < 0.5 ? "#f87171" : "#94a3b8", fontWeight: "bold" }}>
                            {u.health_pct != null ? `${Math.round(u.health_pct * 100)}%` : ""}
                          </span>
                        </>
                      ) : (
                        "-"
                      )}
                    </div>
                    {!dead && u.health_pct != null && (
                      <div style={{ width: "100%", height: 3, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${Math.round(u.health_pct * 100)}%`,
                            height: "100%",
                            background: u.health_pct > 0.6 ? "#22c55e" : (u.health_pct > 0.35 ? "#eab308" : "#ef4444"),
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            </div>
          </div>
        </div>
      ))}
    </div>
  </>
  );
}
