import { useEffect, useState, useMemo } from "react";
import { formatCoords } from "../render/hexGridRenderer";

export type Order = {
  type?: string;
  kind?: string;
  unit_id?: string;
  target_q?: number;
  target_r?: number;
  target_id?: string;
  move_q?: number;
  move_r?: number;
  move_to?: { q?: number; r?: number } | null;
  action_id?: string;
  source?: string;
  action?: string;
};

type DispatchedOrdersPanelProps = {
  availableMoves?: Order[];
  selectedUnitId?: string | null;
  isHumanTurn?: boolean;
  onHoverOrder?: (order: Order) => void;
  onLeaveOrder?: () => void;
  onActionExecuted?: (order: Order) => void;
};

export type ActionCategory = "ALL" | "MOVE" | "FIRE" | "ASSAULT" | "WAIT";

export function categorizeOrder(order: Order): ActionCategory {
  const type = String(order.type || order.kind || "").toUpperCase();
  const kind = String(order.kind || "").toLowerCase();
  const action = String(order.action || "").toUpperCase();

  if (kind === "wait" || type === "WAIT" || action.includes("WAIT")) {
    return "WAIT";
  }
  if (
    type === "ASSAULT" ||
    type.includes("ASSAULT") ||
    action.includes("ASSAULT") ||
    type.includes("GRENADE") ||
    action.includes("GRENADE") ||
    kind === "assault"
  ) {
    return "ASSAULT";
  }
  if (
    type.includes("RANGED") ||
    type.includes("FIRE") ||
    type === "ATTACK" ||
    kind === "attack" ||
    action.includes("RANGED") ||
    action.includes("FIRE") ||
    action.includes("ATTACK")
  ) {
    return "FIRE";
  }
  if (type === "MOVE" || kind === "move" || action.includes("MOVE")) {
    return "MOVE";
  }
  return "MOVE";
}

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
  onLeaveOrder,
  onActionExecuted,
}: DispatchedOrdersPanelProps) {
  const [aiOrders, setAiOrders] = useState<Order[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<ActionCategory>("ALL");

  useEffect(() => {
    (window as any).onAIOrders = (steps: Order[]) => {
      console.log("📥 AI ORDERS RECEIVED", steps);
      setAiOrders((prev) => [...steps, ...prev].slice(0, 40));
    };

    return () => {
      (window as any).onAIOrders = undefined;
    };
  }, []);

  // Reset category to ALL if selected category has no orders on unit change
  useEffect(() => {
    setSelectedCategory("ALL");
  }, [selectedUnitId]);

  // ✅ NORMALIZAR HUMANO (sin excluir wait!)
  const normalizedHuman: Order[] = useMemo(() => {
    return availableMoves.map((a: any) => {
      const rawKind = String(a.kind || "").toLowerCase();
      let type = "MOVE";
      if (rawKind === "wait") {
        type = "WAIT";
      } else if (rawKind === "attack") {
        type = (a.type || "ATTACK").toUpperCase();
      } else if (a.type) {
        type = String(a.type).toUpperCase();
      }

      return {
        type,
        kind: a.kind || (type === "WAIT" ? "wait" : type === "MOVE" ? "move" : "attack"),
        target_q: a.target_q ?? a.q,
        target_r: a.target_r ?? a.r,
        target_id: a.target_id,
        move_q: a.move_q ?? a.q,
        move_r: a.move_r ?? a.r,
        move_to: a.move_to,
        action_id: a.action_id,
        unit_id: selectedUnitId ?? undefined,
        source: "HUMAN",
      };
    });
  }, [availableMoves, selectedUnitId]);

  // ✅ NORMALIZAR IA
  const normalizedAI: Order[] = useMemo(() => {
    return aiOrders.map((o: any) => {
      const actionClass = (o.action || "").toString();
      let type = o.type || o.kind;
      if (!type && actionClass) {
        if (/Ranged/i.test(actionClass)) type = "RANGED";
        else if (/Assault/i.test(actionClass)) type = "ASSAULT";
        else if (/Wait/i.test(actionClass)) type = "WAIT";
        else if (/Move/i.test(actionClass)) type = "MOVE";
        else type = actionClass.replace(/Action$/, "");
      }
      return {
        ...o,
        type: (type || "MOVE").toString().toUpperCase(),
        source: "AI",
      };
    });
  }, [aiOrders]);

  // Orders source
  const orders = useMemo(() => {
    return selectedUnitId ? normalizedHuman : [...normalizedHuman, ...normalizedAI];
  }, [selectedUnitId, normalizedHuman, normalizedAI]);

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts = {
      ALL: orders.length,
      MOVE: 0,
      FIRE: 0,
      ASSAULT: 0,
      WAIT: 0,
    };
    for (const ord of orders) {
      const cat = categorizeOrder(ord);
      if (cat in counts) {
        counts[cat]++;
      }
    }
    return counts;
  }, [orders]);

  // Filtered orders by active category
  const filteredOrders = useMemo(() => {
    if (selectedCategory === "ALL") return orders;
    return orders.filter((o) => categorizeOrder(o) === selectedCategory);
  }, [orders, selectedCategory]);

  const executeActionById = async (actionId: string, order?: Order) => {
    try {
      const executed = await (window as any).onExecuteOrder?.(order);
      if (executed) {
        return;
      }
      console.warn("⛔ executeActionById rejected: onExecuteOrder did not execute", actionId);
    } catch (err) {
      console.error("❌ Action by id failed", err);
    }
  };

  return (
    <>
      <div className="panel-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Available Actions</span>
        {selectedUnitId && (
          <span style={{ fontSize: "10px", color: "var(--neon-cyan)", fontFamily: "var(--font-mono)" }}>
            Unit {selectedUnitId}
          </span>
        )}
      </div>

      {/* Action Category Selector Tabs */}
      <div className="actions-category-tabs">
        <button
          className={`action-cat-tab ${selectedCategory === "ALL" ? "active" : ""}`}
          onClick={() => setSelectedCategory("ALL")}
        >
          ALL ({categoryCounts.ALL})
        </button>

        <button
          className={`action-cat-tab cat-move ${selectedCategory === "MOVE" ? "active" : ""} ${
            categoryCounts.MOVE === 0 ? "disabled" : ""
          }`}
          onClick={() => categoryCounts.MOVE > 0 && setSelectedCategory("MOVE")}
          disabled={categoryCounts.MOVE === 0}
          title="Filter Movement actions"
        >
          🏃 MOVE ({categoryCounts.MOVE})
        </button>

        <button
          className={`action-cat-tab cat-fire ${selectedCategory === "FIRE" ? "active" : ""} ${
            categoryCounts.FIRE === 0 ? "disabled" : ""
          }`}
          onClick={() => categoryCounts.FIRE > 0 && setSelectedCategory("FIRE")}
          disabled={categoryCounts.FIRE === 0}
          title="Filter Ranged / Mortar Fire actions"
        >
          🎯 FIRE ({categoryCounts.FIRE})
        </button>

        <button
          className={`action-cat-tab cat-assault ${selectedCategory === "ASSAULT" ? "active" : ""} ${
            categoryCounts.ASSAULT === 0 ? "disabled" : ""
          }`}
          onClick={() => categoryCounts.ASSAULT > 0 && setSelectedCategory("ASSAULT")}
          disabled={categoryCounts.ASSAULT === 0}
          title="Filter Close Assault & Grenades actions"
        >
          💥 ASSAULT ({categoryCounts.ASSAULT})
        </button>

        <button
          className={`action-cat-tab cat-wait ${selectedCategory === "WAIT" ? "active" : ""} ${
            categoryCounts.WAIT === 0 ? "disabled" : ""
          }`}
          onClick={() => categoryCounts.WAIT > 0 && setSelectedCategory("WAIT")}
          disabled={categoryCounts.WAIT === 0}
          title="Filter Wait / End Activation"
        >
          ⏸ WAIT ({categoryCounts.WAIT})
        </button>
      </div>

      <div className="actions-list">
        {filteredOrders.length > 0 ? (
          filteredOrders.map((order, i) => {
            const actionType = (order.type || order.kind || "MOVE").toString().toUpperCase();
            const category = categorizeOrder(order);
            const isAttack = isCombatAction(order, actionType);
            const isWait = category === "WAIT";
            const isAssault = category === "ASSAULT";

            const targetQ = order.target_q ?? (order as any).q;
            const targetR = order.target_r ?? (order as any).r;
            const coords =
              targetQ != null && targetR != null ? formatCoords(targetQ, targetR) : isWait ? "END TURN" : "?";
            const moveQ = (order as any).move_q ?? (order as any).q ?? (order as any).move_to?.q;
            const moveR = (order as any).move_r ?? (order as any).r ?? (order as any).move_to?.r;
            const moveCoords = moveQ != null && moveR != null ? formatCoords(moveQ, moveR) : null;

            const canExecute = (order.source === "HUMAN" || !order.source) && isHumanTurn;

            const buildDescription = () => {
              if (isWait) return "Wait / End activation and mark unit as Done";
              if (isAssault) {
                const targetText = order.target_id ? `squad ${order.target_id}` : `position ${coords}`;
                return `Close Assault & Grenades against ${targetText}`;
              }
              if (!isAttack) return `Advance squad to ${coords}`;

              const targetText = `${order.target_id ? `target ${order.target_id} ` : ""}at ${coords}`;
              if (actionType === "RANGED_INDIRECT") {
                return `Indirect Mortar Fire against ${targetText}`;
              }
              if (actionType === "MOVE_THEN_FIRE") {
                return moveCoords
                  ? `Move to ${moveCoords} then attack ${targetText}`
                  : `Move then attack ${targetText}`;
              }
              if (actionType === "FIRE_THEN_MOVE") {
                return moveCoords
                  ? `Attack ${targetText} then move to ${moveCoords}`
                  : `Attack ${targetText} then move`;
              }
              return `Direct Ranged Fire against ${targetText}`;
            };

            let cardExtraClass = "";
            if (isWait) cardExtraClass = "action-wait";
            else if (isAssault) cardExtraClass = "action-assault";
            else if (isAttack) cardExtraClass = "action-attack";

            const getCategoryIcon = () => {
              if (isWait) return "⏸";
              if (isAssault) return "💥";
              if (actionType === "RANGED_INDIRECT") return "💣";
              if (isAttack) return "🎯";
              return "🏃";
            };

            return (
              <div
                key={order.action_id || `${order.type}_${targetQ}_${targetR}_${i}`}
                className={`action-card ${cardExtraClass}`}
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
                  (window as any).onOrderLeave?.();
                  onLeaveOrder?.();
                  onActionExecuted?.(order);
                  (window as any).onCloseSquadDrawer?.();

                  const actionId = (order as any).action_id;
                  if (actionId) {
                    void executeActionById(actionId, order);
                    return;
                  }

                  const q = order.target_q ?? (order as any).q;
                  const r = order.target_r ?? (order as any).r;

                  if (q != null && r != null) {
                    console.log("🖱️ EXECUTING ORDER ON MAP", order);
                    (window as any).onHexClick?.(q, r);
                  } else {
                    console.warn("⛔ Order missing coordinates and action_id", order);
                  }
                }}
                style={{ opacity: canExecute ? 1 : 0.65, cursor: canExecute ? "pointer" : "default" }}
              >
                <div className="action-header">
                  <div className="action-type">
                    <span style={{ marginRight: 4 }}>{getCategoryIcon()}</span>
                    {actionType}
                  </div>

                  <div className="action-coords">{coords}</div>
                </div>

                <div className="action-desc">{buildDescription()}</div>
              </div>
            );
          })
        ) : (
          <div
            style={{
              fontSize: "12px",
              color: "var(--text-muted)",
              fontStyle: "italic",
              textAlign: "center",
              padding: "16px 10px",
            }}
          >
            {selectedUnitId
              ? `No actions available for category "${selectedCategory}".`
              : "Select a squad to deploy tactical orders."}
          </div>
        )}
      </div>
    </>
  );
}
