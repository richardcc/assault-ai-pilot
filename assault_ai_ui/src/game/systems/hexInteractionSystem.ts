import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";
import { animateMove } from "../animation/animateMove";
import { Ticker } from "pixi.js";

export async function handleHexClick(
  q: number,
  r: number,
  selectedUnitId: string | null,
  availableMoves: any[],
  unitLayerRef: any,
  appRef: any,
  fxLayerRef: any,
  setAvailableMoves: (moves: any[]) => void,
  setSelectedUnitId: (id: string | null) => void
) {
  if (!selectedUnitId) return;

  console.log("CLICK HEX", { q, r });

  const move = availableMoves.find(
    (m: any) => m.q === q && m.r === r
  );

  if (!move) {
    console.log("❌ no move found");
    return;
  }

  const actionId = move.action_id;

  // ✅ get real container
  const unitContainer = unitLayerRef.current?.container?.children.find(
    (c: any) => c.__unitId === selectedUnitId
  );

  if (!unitContainer) return;

  // 💣 ✅ FIX CLAVE: bloquear doble animación
  if (unitContainer.__isMoving) {
    console.warn("⛔ MOVE BLOCKED: already moving", selectedUnitId);
    return;
  }

  // ✅ HEX → PIXEL
  const { x, y } = axialToPixel(q, r);

  const to = {
    x: Math.round(x),
    y: Math.round(y + HEX_SIZE)
  };

  console.log("👉 BEFORE ANIMATE", {
    id: selectedUnitId,
    from: { x: unitContainer.x, y: unitContainer.y },
    to
  });

  // ✅ animación (espera realista)
  await new Promise<void>((resolve) => {

    animateMove(
      unitContainer,
      to,
      Ticker.shared,
      300
    );

    // 💣 IMPORTANTE: más largo que la animación real
    setTimeout(resolve, 350);
  });

  console.log("🎬 ANIMATION COMPLETE", selectedUnitId);

  // ✅ backend AFTER animation
  await fetch("http://127.0.0.1:8000/api/game/step", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      action_id: actionId
    })
  });

  const res = await fetch("http://127.0.0.1:8000/api/game/state");
  const newState = await res.json();

  setSelectedUnitId(null);
  (window as any).__setGameState?.(newState);

  // opcional limpiar UI
  setAvailableMoves([]);
}
