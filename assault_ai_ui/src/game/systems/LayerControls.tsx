type Props = {
  showMap: boolean;
  showGrid: boolean;
  onToggleMap: (value: boolean) => void;
  onToggleGrid: (value: boolean) => void;
};

export default function LayerControls({
  showMap,
  showGrid,
  onToggleMap,
  onToggleGrid,
}: Props) {
  return (
    <div
      style={{
        position: "absolute",
        top: 10,
        left: 10,
        background: "#222",
        padding: "8px",
        borderRadius: "4px",
        color: "white",
        fontSize: "14px",
      }}
    >
      <label>
        <input
          type="checkbox"
          checked={showMap}
          onChange={(e) => onToggleMap(e.target.checked)}
        />
        Map
      </label>

      <br />

      <label>
        <input
          type="checkbox"
          checked={showGrid}
          onChange={(e) => onToggleGrid(e.target.checked)}
        />
        Grid
      </label>
    </div>
  );
}