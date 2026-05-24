import React from "react";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";

type Unit = {
  id: string;
  unit_key: string;
  side: string;
  hp?: number;
  q: number;
  r: number;
};

type Props = {
  units: Unit[];
  activeSide?: string;
  activatedUnits?: string[];
};

export function UnitStatePanel({
  units,
  activeSide,
  activatedUnits = []
}: Props) {

  const unitsBySide: Record<string, Unit[]> = {};

  for (const u of units) {
    if (!unitsBySide[u.side]) {
      unitsBySide[u.side] = [];
    }
    unitsBySide[u.side].push(u);
  }

  return (
    <div
      style={{
        width: "100%",
        background: "#222",
        color: "#fff",
        borderTop: "2px solid #444",
        padding: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          overflowX: "auto",
        }}
      >
        {Object.entries(unitsBySide).map(([side, list]) => (
          <div
            key={side}
            style={{
              minWidth: 200,
              marginRight: 20,
            }}
          >
            {/* HEADER */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 6,
                borderBottom: "1px solid #555",
                paddingBottom: 2,
              }}
            >
              {sides[side]?.marker && (
                <img
                  src={encodeURI(sides[side].marker)}
                  style={{
                    width: 18,
                    height: 18,
                    objectFit: "contain",
                  }}
                />
              )}

              <div
                style={{
                  fontWeight: "bold",
                  fontSize: 14,
                }}
              >
                {sides[side]?.short_label || side}
              </div>
            </div>

            {/* UNITS */}
            <div style={{ display: "flex", flexWrap: "wrap" }}>
              {list.map((u) => {

                const def = unitImages[u.unit_key];

                const isOwn = u.side === activeSide;
                const isAvailable =
                  isOwn && !activatedUnits.includes(u.id);

                let border = "#555";
                let background = "#333";
                let opacity = 1;

                if (!isOwn) {
                  opacity = 0.6; // enemigo
                } else if (!isAvailable) {
                  opacity = 0.8; // usada
                } else {
                  border = "#00ff00"; // ✅ disponible
                  background = "#263826";
                }

                return (
                  <div
                    key={u.id}
                    onMouseEnter={() =>
                      (window as any).highlightUnit?.(u.id)
                    }
                    onMouseLeave={() =>
                      (window as any).highlightUnit?.(null)
                    }
                    onClick={() =>
                      (window as any).focusUnit?.(u.id)
                    }
                    style={{
                      width: 80,
                      height: 90,
                      margin: 4,
                      padding: 4,
                      background,
                      border: `1px solid ${border}`,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 1,
                      cursor: "pointer",
                      opacity,
                      transition: "all 0.15s ease",
                    }}
                  >
                    {/* IMAGE */}
                    {def?.full && (
                      <img
                        src={encodeURI(def.full)}
                        style={{
                          width: 45,
                          height: 45,
                          objectFit: "contain",
                          marginBottom: 2,
                        }}
                      />
                    )}

                    {/* LABEL */}
                    <div
                      style={{
                        fontSize: 7,
                        textAlign: "center",
                        lineHeight: "8px",
                      }}
                    >
                      {def?.label || u.unit_key}
                    </div>

                    {/* ID */}
                    <div
                      style={{
                        fontSize: 9,
                        fontWeight: "bold",
                        lineHeight: "10px",
                      }}
                    >
                      {u.id}
                    </div>

                    {/* HP */}
                    <div
                      style={{
                        fontSize: 10,
                      }}
                    >
                      {u.hp != null
                        ? Array.from({ length: u.hp }).map((_, i) => (
                            <span key={i}>❤️</span>
                          ))
                        : "-"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
