import { useEffect, useState } from "react";
import { formatCoords } from "../render/hexGridRenderer";
import { gameController } from "../gameControllerInstance";

type Order = {
  type?: string;
  kind?: string;
  unit_id?: string;
  target_q?: number;
  target_r?: number;
  target_id?: string;
};

type DispatchedOrdersPanelProps = {
  availableMoves?: Order[];
  selectedUnitId?: string | null;
  isHumanTurn?: boolean;
  onHoverOrder?: (order: Order) => void;
  onLeaveOrder?: () => void;
};

function isCombatAction(order: Order, actionType: string): boolean {
  if (order.kind === "attack") return true;
  if (actionType !== "MOVE" && /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/i.test(actionType)) {
    return true;
  }
  const actionClass = ((order as any).action || "").toString().toUpperCase();
  return /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/.test(actionClass);
}

export function DispatchedOrdersPanel({
  availableMoves = [],
  selectedUnitId,
  isHumanTurn = false,
  onHoverOrder,
  onLeaveOrder
}: DispatchedOrdersPanelProps) {

  const [aiOrders, setAiOrders] = useState<Order[]>([]);

  useEffect(() => {

    // 🔥 escuchar órdenes del GameController
    (window as any).onAIOrders = (steps: Order[]) => {

      console.log("📥 AI ORDERS RECEIVED", steps);

      setAiOrders(prev => [
        ...steps,
        ...prev
      ].slice(0, 20));
    };

    return () => {
      (window as any).onAIOrders = undefined;
    };

  }, []);

  // ✅ NORMALIZAR HUMANO
  const normalizedHuman = availableMoves.map((a: any) => ({
    type: (a.kind === "attack"
      ? (a.type || "ATTACK")
      : a.kind === "wait"
      ? "WAIT"
      : "MOVE").toUpperCase(),
    kind: a.kind,

    target_q: a.q ?? a.target_q,
    target_r: a.r ?? a.target_r,
    target_id: a.target_id,
    action_id: (a as any).action_id,

    unit_id: selectedUnitId,
    source: "HUMAN"
  }));

  // ✅ NORMALIZAR IA
  const normalizedAI = aiOrders.map((o: any) => {
    const actionClass = (o.action || "").toString();
    let type = o.type || o.kind;
    if (!type && actionClass) {
      if (/Ranged/i.test(actionClass)) type = "RANGED";
      else if (/Assault/i.test(actionClass)) type = "ASSAULT";
      else if (/Move/i.test(actionClass)) type = "MOVE";
      else type = actionClass.replace(/Action$/, "");
    }
    return {
      ...o,
      type: (type || "MOVE").toString().toUpperCase(),
      source: "AI"
    };
  });

  // ✅ MEZCLAR
  const orders = [...normalizedHuman, ...normalizedAI].slice(0, 20);

  const executeActionById = async (actionId: string) => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/game/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: actionId }),
      });
      const data = await res.json();
      if (data?.state && typeof (window as any).__setGameState === "function") {
        (window as any).__setGameState(data.state);
        gameController.updateState(data.state);
      }
    } catch (err) {
      console.error("❌ WAIT action failed", err);
    }
  };


  return (
    <>
      <div className="panel-title">Dispatched Orders</div>

      <div className="actions-list">
        {orders.length > 0 ? (
          orders.map((order, i) => {

            const actionType = (order.type || order.kind || "MOVE").toString().toUpperCase();
            const isAttack = isCombatAction(order, actionType);

            const targetQ = order.target_q ?? order.q;
            const targetR = order.target_r ?? order.r;
            const coords = targetQ != null && targetR != null
              ? formatCoords(targetQ, targetR)
              : "?";

            const canExecute = order.source === "HUMAN" && isHumanTurn;
            return (
                <div
                  key={i}
                  className={`action-card ${isAttack ? "action-attack" : ""}`}
                  onMouseEnter={() => {
                    (window as any).onOrderHover?.(order);
                    onHoverOrder?.(order);
                  }}
                  onMouseLeave={() => {
                    (window as any).onOrderLeave?.();
                    onLeaveOrder?.();
                  }}
                  onClick={() => {
                    if (!canExecute) return;
                    const q = order.target_q ?? (order as any).q;
                    const r = order.target_r ?? (order as any).r;

                    if (q != null && r != null) {

                      console.log("🖱️ EXECUTING ORDER", order);

                      // ✅ Ejecutar acción en el mapa (igual que humano)
                      (window as any).onHexClick?.(q, r);

                    } else if (actionType === "WAIT" && (order as any).action_id) {
                      void executeActionById((order as any).action_id);
                    } else {
                      console.warn("⛔ Order sin coordenadas", order);
                    }
                  }}
                  style={{ opacity: canExecute ? 1 : 0.7, cursor: canExecute ? "pointer" : "default" }}
                >

                <div className="action-header">
                  <div className="action-type">
                    {actionType}
                  </div>

                  <div className="action-coords">
                    {coords}
                  </div>
                </div>

                <div className="action-desc">
                  {actionType === "WAIT"
                    ? "Wait / End activation"
                    : isAttack
                    ? `Attack ${order.target_id ? `target ${order.target_id} ` : ""}at ${coords}`
                    : `Move to ${coords}`
                  }
                </div>
              </div>
            );
          })
        ) : (
          <div style={{
            fontSize: "12px",
            color: "var(--text-muted)",
            fontStyle: "italic",
            textAlign: "center",
            padding: "10px"
          }}>
            Awaiting dispatched orders...
          </div>
        )}
      </div>
    </>
  );
}