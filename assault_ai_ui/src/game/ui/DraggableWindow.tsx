import { ReactNode, useEffect, useRef, useState } from "react";

type DraggableWindowProps = {
  windowId: string;
  title: string;
  initialX: number;
  initialY: number;
  width?: number;
  bodyMaxHeight?: number;
  children: ReactNode;
};

type WindowStateEventDetail = {
  windowId?: string;
  minimized?: boolean;
  visible?: boolean;
};

export function DraggableWindow({
  windowId,
  title,
  initialX,
  initialY,
  width = 360,
  bodyMaxHeight = 420,
  children,
}: DraggableWindowProps) {
  const [x, setX] = useState(initialX);
  const [y, setY] = useState(initialY);
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [visible, setVisible] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const [windowWidth, setWindowWidth] = useState(width);
  const [windowBodyHeight, setWindowBodyHeight] = useState(bodyMaxHeight);
  const dragRef = useRef<{ offsetX: number; offsetY: number } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; startW: number; startH: number } | null>(null);
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
        width?: number;
        bodyHeight?: number;
      };
      if (typeof parsed.x === "number") setX(parsed.x);
      if (typeof parsed.y === "number") setY(parsed.y);
      if (typeof parsed.minimized === "boolean") setMinimized(parsed.minimized);
      if (typeof parsed.visible === "boolean") setVisible(parsed.visible);
      if (typeof parsed.width === "number" && Number.isFinite(parsed.width)) {
        setWindowWidth(Math.max(180, Math.min(window.innerWidth - 16, parsed.width)));
      }
      if (typeof parsed.bodyHeight === "number" && Number.isFinite(parsed.bodyHeight)) {
        setWindowBodyHeight(Math.max(90, Math.min(window.innerHeight - 120, parsed.bodyHeight)));
      }
    } catch {
      // Ignore invalid persisted window state.
    } finally {
      setHydrated(true);
    }
  }, [storageKey]);

  useEffect(() => {
    const onSave = () => {
      if (!hydrated) return;
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            x,
            y,
            minimized,
            visible,
            width: windowWidth,
            bodyHeight: windowBodyHeight,
          })
        );
      } catch {
        // Ignore storage errors.
      }
    };
    window.addEventListener("assault:save-layout", onSave as EventListener);
    return () => {
      window.removeEventListener("assault:save-layout", onSave as EventListener);
    };
  }, [x, y, minimized, visible, windowWidth, windowBodyHeight, storageKey, hydrated]);

  useEffect(() => {
    const onMove = (ev: MouseEvent) => {
      if (resizeRef.current) {
        const dx = ev.clientX - resizeRef.current.startX;
        const dy = ev.clientY - resizeRef.current.startY;
        const maxW = Math.max(260, window.innerWidth - 16);
        const maxH = Math.max(160, window.innerHeight - 120);
        const nextW = Math.max(180, Math.min(maxW, resizeRef.current.startW + dx));
        const nextH = Math.max(90, Math.min(maxH, resizeRef.current.startH + dy));
        setWindowWidth(nextW);
        setWindowBodyHeight(nextH);
        return;
      }
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
      const maxX = Math.max(margin, viewportW - windowWidth - margin);
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
      resizeRef.current = null;
      setDragging(false);
      setResizing(false);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [minimized, windowWidth]);

  useEffect(() => {
    const onState = (ev: Event) => {
      const custom = ev as CustomEvent<WindowStateEventDetail>;
      const detail = custom?.detail || {};
      const targetId = String(detail.windowId || "");
      if (targetId && targetId !== "*" && targetId !== windowId) return;
      if (typeof detail.minimized === "boolean") {
        setMinimized(detail.minimized);
      }
      if (typeof detail.visible === "boolean") {
        setVisible(detail.visible);
      }
    };
    window.addEventListener("assault:set-window-state", onState as EventListener);
    return () => {
      window.removeEventListener("assault:set-window-state", onState as EventListener);
    };
  }, [windowId]);

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

  const startResize = (ev: React.MouseEvent<HTMLDivElement>) => {
    ev.stopPropagation();
    resizeRef.current = {
      startX: ev.clientX,
      startY: ev.clientY,
      startW: windowWidth,
      startH: windowBodyHeight,
    };
    setResizing(true);
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
        width: `${windowWidth}px`,
        zIndex: dragging || resizing ? 60 : 50,
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
      {!minimized && (
        <div className="draggable-window-body" style={{ height: `${windowBodyHeight}px` }}>
          {children}
        </div>
      )}
      {!minimized && (
        <div
          className="draggable-window-resize-handle"
          onMouseDown={startResize}
          title="Redimensionar"
        />
      )}
    </div>
  );
}
