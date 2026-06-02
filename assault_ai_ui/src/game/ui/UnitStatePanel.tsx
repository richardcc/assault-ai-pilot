import { useState } from "react";
import { unitImages } from "../config/unitImages";
import { UnitCardTooltip } from "./UnitCardTooltip";
import { sides } from "../config/sides";
import { formatCoords } from "../render/hexGridRenderer";

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
  onSelectUnit?: (unit: Unit) => void;
};

export function UnitStatePanel({
  units,
  activeSide,
  activatedUnits = [],
  selectedUnitId,
  onSelectUnit
}: Props) {

  const [cardPreview, setCardPreview] = useState<{
    unit: Unit;
    x: number;
    y: number;
  } | null>(null);

  const unitsBySide: Record<string, Unit[]> = {};

  for (const u of units) {
    if (!unitsBySide[u.side]) {
      unitsBySide[u.side] = [];
    }
    unitsBySide[u.side].push(u);
  }

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

    <div className="roster-container">
      {Object.entries(unitsBySide).map(([side, list]) => (
        <div key={side} className="roster-side-group">
          {/* HEADER */}
          <div className="roster-side-header">
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

          {/* UNITS */}
          <div className="roster-list">
            {list.map((u) => {
              const def = unitImages[u.unit_key as keyof typeof unitImages];
              const dead =
                u.alive === false || (u.hp != null && u.hp <= 0);
              const isOwn = u.side === activeSide;
              const isAvailable = isOwn && !activatedUnits.includes(u.id) && !dead;
              const isSelected = u.id === selectedUnitId;
              const deadMarker = dead ? sides[u.side]?.dead_marker : undefined;

              // Compute CSS class names based on unit status
              let cardClass = "trooper-card";
              if (isSelected) {
                cardClass += " selected";
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

                  {/* HP DISPLAY */}
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
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  </>
  );
}
