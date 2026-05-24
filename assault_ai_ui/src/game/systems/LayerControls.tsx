type Props = {
  showMap: boolean;
  showGrid: boolean;
  showCoords: boolean; // ✅ NUEVO

  onToggleMap: (value: boolean) => void;
  onToggleGrid: (value: boolean) => void;
  onToggleCoords: (value: boolean) => void; // ✅ NUEVO
};

export default function LayerControls({
  showMap,
  showGrid,
  showCoords,
  onToggleMap,
  onToggleGrid,
  onToggleCoords,
}: Props) {
  return (
    <div
      style={{
        position: "absolute",
        top: 10,
        left: 10,
        background: "#222",
        padding: "10px",
        borderRadius: "6px",
        color: "white",
        fontSize: "14px",

        display: "flex",
        flexDirection: "column",
        gap: "8px",

        zIndex: 1000,
      }}
    >
      {/* ✅ MAP */}
      <label style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        <input
          type="checkbox"
          checked={showMap}
          onChange={(e) => onToggleMap(e.target.checked)}
        />
        Map
      </label>

      {/* ✅ GRID */}
      <label style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        <input
          type="checkbox"
          checked={showGrid}
          onChange={(e) => onToggleGrid(e.target.checked)}
        />
        Grid
      </label>

      {/* ✅ 🔥 NEW: COORDS */}
      <label style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        <input
          type="checkbox"
          checked={showCoords}
          onChange={(e) => onToggleCoords(e.target.checked)}
        />
        Coords
      </label>
    </div>
  );
}