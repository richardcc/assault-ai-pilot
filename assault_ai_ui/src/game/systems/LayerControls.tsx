type Props = {
  showMap: boolean;
  showGrid: boolean;
  showCoords: boolean;

  onToggleMap: (value: boolean) => void;
  onToggleGrid: (value: boolean) => void;
  onToggleCoords: (value: boolean) => void;
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
    <div className="layer-controls-bar">
      <label className={`layer-control-chip ${showMap ? "active" : ""}`} title="Toggle background map imagery">
        <input
          type="checkbox"
          checked={showMap}
          onChange={(e) => onToggleMap(e.target.checked)}
        />
        <span>Map</span>
      </label>

      <label className={`layer-control-chip ${showGrid ? "active" : ""}`} title="Toggle hex grid overlay">
        <input
          type="checkbox"
          checked={showGrid}
          onChange={(e) => onToggleGrid(e.target.checked)}
        />
        <span>Grid</span>
      </label>

      <label className={`layer-control-chip ${showCoords ? "active" : ""}`} title="Toggle hex axial coordinates">
        <input
          type="checkbox"
          checked={showCoords}
          onChange={(e) => onToggleCoords(e.target.checked)}
        />
        <span>Coords</span>
      </label>
    </div>
  );
}
