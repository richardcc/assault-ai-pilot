import { useEffect, useState } from "react";
import { formatCoords } from "../render/hexGridRenderer";

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
};

export function DispatchedOrdersPanel({ availableMoves = [], selectedUnitId }: DispatchedOrdersPanelProps) {

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
      : "MOVE").toUpperCase(),

    target_q: a.q ?? a.target_q,
    target_r: a.r ?? a.target_r,
    target_id: a.target_id,

    unit_id: selectedUnitId,
    source: "HUMAN"
  }));

  // ✅ NORMALIZAR IA
  const normalizedAI = aiOrders.map((o: any) => ({
    ...o,
    source: "AI"
  }));

  // ✅ MEZCLAR
  const orders = [...normalizedHuman, ...normalizedAI].slice(0, 20);


  return (
    <>
      <div className="panel-title">Dispatched Orders</div>

      <div className="actions-list">
        {orders.length > 0 ? (
          orders.map((order, i) => {

            const actionType = (order.type || order.kind || "MOVE").toString().toUpperCase();
            const isAttack = actionType === "ATTACK" || order.kind === "attack";

            const targetQ = order.target_q ?? order.q;
            const targetR = order.target_r ?? order.r;
            const coords = targetQ != null && targetR != null
              ? formatCoords(targetQ, targetR)
              : "?";

            return (
                <div
                  key={i}
                  className={`action-card ${isAttack ? "action-attack" : ""}`}

                  onClick={() => {
                    const q = order.target_q ?? (order as any).q;
                    const r = order.target_r ?? (order as any).r;

                    if (q != null && r != null) {

                      console.log("🖱️ EXECUTING ORDER", order);

                      // ✅ Ejecutar acción en el mapa (igual que humano)
                      (window as any).onHexClick?.(q, r);

                    } else {
                      console.warn("⛔ Order sin coordenadas", order);
                    }
                  }}
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
                  {isAttack
                    ? `Attack target ${order.target_id || "unknown"}`
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
``