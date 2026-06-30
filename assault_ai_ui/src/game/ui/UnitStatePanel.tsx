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

                  {/* HP + compact action display */}
                  <div className="trooper-card-hp-row">
                    <div className="trooper-card-hp">
                      {dead ? (
                        <span style={{ color: "#ff3838", fontWeight: 700 }}>DEAD</span>
                      ) : u.hp != null ? (
                        Array.from({ length: u.hp }).map((_, i) => (
                          <span key={i} style={{ color: "#ff3838" }}>❤️</span>
                        ))
                      ) : (
                        "-"
                      )}
                    </div>
                    {/* Keep marker-only visualization for consumed actions;
                        avoid forcing WAIT text for all normal markers. */}
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
