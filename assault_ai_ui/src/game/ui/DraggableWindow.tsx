import { ReactNode, useEffect, useRef, useState } from "react";

type DraggableWindowProps = {
  windowId: string;
  title: string;
  initialX: number;
  initialY: number;
  width?: number;
  children: ReactNode;
};

export function DraggableWindow({
  windowId,
  title,
  initialX,
  initialY,
  width = 360,
  children,
}: DraggableWindowProps) {
  const [x, setX] = useState(initialX);
  const [y, setY] = useState(initialY);
  const [dragging, setDragging] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [visible, setVisible] = useState(true);
  const dragRef = useRef<{ offsetX: number; offsetY: number } | null>(null);
  const storageKey = `assault.window.${windowId}`;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        x?: number;
        y?: number;
        minimized?: boolean;
        visible?: boolean;
      };
      if (typeof parsed.x === "number") setX(parsed.x);
      if (typeof parsed.y === "number") setY(parsed.y);
      if (typeof parsed.minimized === "boolean") setMinimized(parsed.minimized);
      if (typeof parsed.visible === "boolean") setVisible(parsed.visible);
    } catch {
      // Ignore invalid persisted window state.
    }
  }, [storageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ x, y, minimized, visible })
      );
    } catch {
      // Ignore storage errors.
    }
  }, [x, y, minimized, visible, storageKey]);

  useEffect(() => {
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      setX(ev.clientX - dragRef.current.offsetX);
      setY(ev.clientY - dragRef.current.offsetY);
    };

    const onUp = () => {
      const snapThreshold = 18;
      const margin = 8;
      const viewportW = window.innerWidth;
      const viewportH = window.innerHeight;
      const windowH = minimized ? 32 : 460;
      const maxX = Math.max(margin, viewportW - width - margin);
      const maxY = Math.max(margin, viewportH - windowH - margin);
      setX((prev) => {
        let next = Math.max(margin, Math.min(prev, maxX));
        if (Math.abs(next - margin) <= snapThreshold) next = margin;
        if (Math.abs(next - maxX) <= snapThreshold) next = maxX;
        return next;
      });
      setY((prev) => {
        let next = Math.max(margin, Math.min(prev, maxY));
        if (Math.abs(next - margin) <= snapThreshold) next = margin;
        if (Math.abs(next - maxY) <= snapThreshold) next = maxY;
        return next;
      });
      dragRef.current = null;
      setDragging(false);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const startDrag = (ev: React.MouseEvent<HTMLDivElement>) => {
    const target = ev.currentTarget.parentElement;
    if (!target) return;
    const rect = target.getBoundingClientRect();
    dragRef.current = {
      offsetX: ev.clientX - rect.left,
      offsetY: ev.clientY - rect.top,
    };
    setDragging(true);
  };

  if (!visible) {
    return (
      <button
        className="draggable-window-restore"
        style={{ left: `${x}px`, top: `${y}px`, zIndex: 55 }}
        onClick={() => setVisible(true)}
      >
        Abrir {title}
      </button>
    );
  }

  return (
    <div
      className="draggable-window"
      style={{
        left: `${x}px`,
        top: `${y}px`,
        width: `${width}px`,
        zIndex: dragging ? 60 : 50,
      }}
    >
      <div className="draggable-window-header" onMouseDown={startDrag}>
        <span>{title}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            className="draggable-window-btn"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => setMinimized((v) => !v)}
            title={minimized ? "Expandir" : "Minimizar"}
          >
            {minimized ? "▢" : "—"}
          </button>
          <button
            className="draggable-window-btn"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => setVisible(false)}
            title="Ocultar"
          >
            ✕
          </button>
          <span className="draggable-window-hint">drag</span>
        </div>
      </div>
      {!minimized && <div className="draggable-window-body">{children}</div>}
    </div>
  );
}
