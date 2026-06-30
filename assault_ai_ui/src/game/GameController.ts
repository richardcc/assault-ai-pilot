import { formatCoords } from "./render/hexGridRenderer";
import { logCombatEvents } from "./systems/combatLog";
import { clearUnitActionMarkers, resolveActionMarker, setUnitActionMarker } from "./state/actionMarkers";
import { apiUrl, wsUrl } from "../config/backend";

type ControllerType = "human" | "ai";
type GameMode = "human" | "ai" | "ai_vs_ai" | "replay";
type Listener = (state: any) => void;
type TurnFlowListener = (flow: {
  autoAdvanceAfterHuman: boolean;
  waitingForManualAdvance: boolean;
}) => void;

export class GameController {
  private normalizeSideId(side: any): string {
    const raw = String(side ?? "").trim();
    if (!raw) return "";
    const upper = raw.toUpperCase();
    return upper.includes(".") ? upper.split(".").pop() || upper : upper;
  }

  private getControllerForSide(state: any, side: any): string {
    const sides = (state && typeof state === "object" ? state.sides : null) || {};
    const wanted = this.normalizeSideId(side);
    if (!wanted) return "";
    for (const [k, v] of Object.entries(sides)) {
      if (this.normalizeSideId(k) === wanted) {
        return String(v ?? "").toLowerCase();
      }
    }
    return "";
  }

  private describeCombatOrder(step: any): { label: string; target: string } {
    const actionName = String(step?.action || "").toUpperCase();
    const actionId = String(step?.action_id || "").toUpperCase();
    const typeName = String(step?.type || step?.kind || "").toUpperCase();

    let label = "Combat";
    if (
      actionName.includes("INDIRECT") ||
      actionId.startsWith("RANGED_INDIRECT:")
    ) {
      label = "Indirect Fire";
    } else if (
      actionName.includes("ASSAULT") ||
      typeName.includes("ASSAULT") ||
      actionId.startsWith("ASSAULT:")
    ) {
      label = "Assault Melee";
    } else if (
      actionName.includes("RANGED") ||
      actionName.includes("FIRE") ||
      actionId.startsWith("RANGED_DIRECT:")
    ) {
      label = "Direct Fire";
    }

    const targetId = String(step?.target_id || "").trim();
    if (targetId) {
      return { label, target: targetId };
    }

    const q = step?.target_q ?? step?.q;
    const r = step?.target_r ?? step?.r;
    if (q != null && r != null) {
      return { label, target: formatCoords(Number(q), Number(r)) };
    }

    return { label, target: "?" };
  }

  private mergeIncrementalState(patch: any) {
    const prevState =
      this.state && typeof this.state === "object" ? this.state : {};
    const incoming = patch && typeof patch === "object" ? patch : {};

    const prevUnits = Array.isArray((prevState as any).units)
      ? (prevState as any).units
      : [];
    const incomingUnits = Array.isArray((incoming as any).units)
      ? (incoming as any).units
      : [];

    const prevById = new Map<string, any>();
    for (const u of prevUnits) {
      const id = String((u as any)?.id || "");
      if (id) prevById.set(id, u);
    }
    const mergedUnits = incomingUnits.map((u: any) => {
      const id = String(u?.id || "");
      const base = id ? prevById.get(id) : null;
      return base ? { ...base, ...u } : u;
    });

    this.state = {
      ...prevState,
      ...incoming,
      units: mergedUnits,
    };
  }

  private actionIdToAx(actionId: string | null | undefined): string {
    const raw = String(actionId || "");
    const parts = raw.split(":");
    if (parts.length < 4) return "[]";
    const q = Number(parts[parts.length - 2]);
    const r = Number(parts[parts.length - 1]);
    if (!Number.isFinite(q) || !Number.isFinite(r)) return "[]";
    return formatCoords(q, r);
  }

  private mode: GameMode = "human";
  private state: any = null;
  private scenarioId = "mettete_i_piedi_terra_1_min";
  private sidesConfig: Record<string, string> = { GE: "human", US: "ai" };

  private listeners: Listener[] = [];
  private turnFlowListeners: TurnFlowListener[] = [];
  private lastState: any = null;

  private socket: WebSocket | null = null;
  private suppressReconnect = false;
  private aiLoopToken = 0;
  private aiLoopTimer: ReturnType<typeof setTimeout> | null = null;
  private startRequestToken = 0;
  private aiTurnInFlight = false;
  private pendingWsState: any = null;
  private loopFn: (() => void) | null = null;
  private autoAdvanceAfterHuman = true;
  private waitingForManualAdvance = false;

  // ✅ NUEVO: referencia al highlight layer
  private highlightLayer: any = null;

  // ----------------------------------
  async start(
    mode: GameMode,
    scenarioId?: string,
    sidesConfig?: Record<string, string>
  ) {
    const requestToken = ++this.startRequestToken;
    this.stopLoop();
    this.waitingForManualAdvance = false;
    this.emitTurnFlow();

    // If a session is already running, treat start() as a full restart
    // (needed when user switches scenario from the dropdown).
    if (this.socket) {
      this.suppressReconnect = true;
      try {
        this.socket.close();
      } catch {
        // ignore websocket close errors on restart
      }
      this.socket = null;
    }

    this.mode = mode;
    clearUnitActionMarkers();
    if (scenarioId) {
      this.scenarioId = scenarioId;
    }
    if (sidesConfig && Object.keys(sidesConfig).length > 0) {
      this.sidesConfig = sidesConfig;
    }

    console.log("Starting mode:", mode);

    // ✅ iniciar partida en backend
    const startRes = await fetch(apiUrl("/api/game/start"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: this.scenarioId,
        sides: this.sidesConfig
      })
    });
    if (!startRes.ok) {
      const detail = await startRes.text();
      throw new Error(`Backend start failed (${startRes.status}): ${detail}`);
    }
    if (requestToken !== this.startRequestToken) return;

    await this.loadScenario();
    if (requestToken !== this.startRequestToken) return;

    setTimeout(() => {
      if (requestToken !== this.startRequestToken) return;
      this.startWebSocket();
    }, 300);

    if (requestToken !== this.startRequestToken) return;
    if (mode === "human" || mode === "ai" || mode === "ai_vs_ai") {
      this.startLoop();
    }
  }

  // ----------------------------------
  private async loadScenario() {
    try {
      const res = await fetch(apiUrl("/api/game/state"));

      const data = await res.json();

      this.state = data;

      this.emit();

    } catch (e) {
      console.error("❌ Scenario load error", e);
    }
  }

  // ----------------------------------
  private startWebSocket() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      return;
    }

    this.socket = new WebSocket(wsUrl("/ws/game"));

    this.socket.onopen = () => {
      console.log("✅ WS connected");
    };

    this.socket.onerror = (err) => {
      console.error("❌ WS error", err);
    };

    this.socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "MAP_STATE" && msg.payload) {
        // During backend-driven AI turn animation, defer websocket sync.
        // Applying state immediately can snap units to final hexes and make
        // animation callbacks look like no-op after first turns.
        if (this.aiTurnInFlight) {
          this.pendingWsState = msg.payload;
          return;
        }
        // MAP_STATE websocket payload is incremental/partial.
        // Merge carefully so we don't lose unit metadata (unit_key, etc.)
        // needed by roster/status panels and action selection.
        this.mergeIncrementalState(msg.payload);
        this.emit();
        return;
      }
      if (
        (msg.type === "REACTION_WINDOW" || msg.type === "REACTION_FIRE" || msg.type === "REACTION_FIRE_SKIPPED")
        && msg.payload
      ) {
        // Never replace core map/status with reaction-only payloads.
        // Only patch pending_reaction when we already have a hydrated game state.
        const hasHydratedState =
          this.state &&
          typeof this.state === "object" &&
          Array.isArray((this.state as any).units) &&
          Array.isArray((this.state as any).hexes);
        if (!hasHydratedState) return;
        this.state = {
          ...this.state,
          pending_reaction: msg.type === "REACTION_WINDOW" ? msg.payload : null,
        };
        this.emit();
      }
    };

    this.socket.onclose = () => {
      console.log("❌ WS closed");
      this.socket = null;

      if (this.suppressReconnect) {
        this.suppressReconnect = false;
        return;
      }

      setTimeout(() => {
        if (this.mode) {
          console.log("🔄 retry WS...");
          this.startWebSocket();
        }
      }, 1000);
    };
  }

  // ----------------------------------
  subscribe(cb: Listener) {
    this.listeners.push(cb);

    if (this.lastState) {
      cb(this.lastState);
    }

    return () => {
      this.listeners = this.listeners.filter((l) => l !== cb);
    };
  }

  subscribeTurnFlow(cb: TurnFlowListener) {
    this.turnFlowListeners.push(cb);
    cb({
      autoAdvanceAfterHuman: this.autoAdvanceAfterHuman,
      waitingForManualAdvance: this.waitingForManualAdvance,
    });
    return () => {
      this.turnFlowListeners = this.turnFlowListeners.filter((l) => l !== cb);
    };
  }

  private emitTurnFlow() {
    const payload = {
      autoAdvanceAfterHuman: this.autoAdvanceAfterHuman,
      waitingForManualAdvance: this.waitingForManualAdvance,
    };
    for (const cb of this.turnFlowListeners) {
      cb(payload);
    }
  }

  private maybePauseForManualAdvance(prevState: any, nextState: any) {
    if (this.mode !== "human") return;
    if (!nextState || nextState.done) return;
    const prevSide = prevState?.active_side;
    const nextSide = nextState?.active_side;
    if (!prevSide || !nextSide || prevSide === nextSide) return;
    const prevController = this.getControllerForSide(prevState, prevSide);
    const nextController = this.getControllerForSide(nextState, nextSide);
    if (prevController === "human" && nextController === "ai") {
      const shouldWait = !this.autoAdvanceAfterHuman;
      if (this.waitingForManualAdvance !== shouldWait) {
        this.waitingForManualAdvance = shouldWait;
        this.emitTurnFlow();
      }
    }
  }

  setAutoAdvanceAfterHuman(enabled: boolean) {
    this.autoAdvanceAfterHuman = Boolean(enabled);
    if (this.autoAdvanceAfterHuman && this.waitingForManualAdvance) {
      this.waitingForManualAdvance = false;
      if (this.loopFn) {
        this.scheduleLoop(this.loopFn, 20);
      }
    }
    this.emitTurnFlow();
  }

  getAutoAdvanceAfterHuman(): boolean {
    return this.autoAdvanceAfterHuman;
  }

  isWaitingForManualAdvance(): boolean {
    return this.waitingForManualAdvance;
  }

  continueAfterHumanAction() {
    if (!this.waitingForManualAdvance) return;
    this.waitingForManualAdvance = false;
    this.emitTurnFlow();
    if (this.loopFn) {
      this.scheduleLoop(this.loopFn, 20);
    }
  }

  private emit() {
    if (!this.state) return;

    this.lastState = this.state;

    for (const cb of this.listeners) {
      cb(this.state);
    }
  }

  // ----------------------------------
  updateState(newState: any) {
    if (!newState || typeof newState !== "object") {
      return;
    }
    const prevState = this.state;
    this.state = newState;
    this.maybePauseForManualAdvance(prevState, newState);
    this.emit();
    // Keep GameCanvas turn-transition hooks in sync (marker reset, unit sync).
    // Some flows (backend ai-turn loop) update controller state directly and
    // otherwise skip __setGameState, leaving activation markers stale.
    try {
      (window as any).__setGameState?.(newState);
    } catch {
      // ignore UI bridge failures
    }
  }

  // ----------------------------------
  // ✅ NUEVO: setter para conectar Pixi layer
  setHighlightLayer(layer: any) {
    this.highlightLayer = layer;
  }

  // ----------------------------------
  private async sendMove(unitId: string, move: any) {

    if (!move?.action_id) return;

    await fetch(apiUrl("/api/game/step"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        action_id: move.action_id
      })
    });
  }

  // ----------------------------------
  // 🔥 IA BACKEND + VISUAL HIGHLIGHTS
  // ----------------------------------
  private stopLoop() {
    this.aiLoopToken += 1;
    this.aiTurnInFlight = false;
    this.pendingWsState = null;
    this.loopFn = null;
    if (this.aiLoopTimer) {
      clearTimeout(this.aiLoopTimer);
      this.aiLoopTimer = null;
    }
  }

  private scheduleLoop(loop: () => void, delayMs: number) {
    if (this.aiLoopTimer) {
      clearTimeout(this.aiLoopTimer);
    }
    this.aiLoopTimer = setTimeout(loop, delayMs);
  }

  private startLoop() {
    this.stopLoop();
    const token = this.aiLoopToken;
    console.log("🤖 AI loop started (backend-driven)");

    const loop = async () => {
      if (token !== this.aiLoopToken) return;

      if (!this.state) {
        this.scheduleLoop(loop, 1000);
        return;
      }

      const data = this.state;
      if (data?.done) {
        this.aiTurnInFlight = false;
        this.pendingWsState = null;
        return;
      }
      const activeSide = data.active_side;

      if (!activeSide) {
        this.scheduleLoop(loop, 1000);
        return;
      }

      // ✅ solo ejecuta si el lado es IA
      if (this.getControllerForSide(data, activeSide) !== "ai") {
        this.scheduleLoop(loop, 1200);
        return;
      }

      if (this.waitingForManualAdvance) {
        this.scheduleLoop(loop, 400);
        return;
      }

      if (this.aiTurnInFlight) {
        this.scheduleLoop(loop, 400);
        return;
      }

      console.log("🤖 CALLING BACKEND AI TURN");
      this.aiTurnInFlight = true;

      try {

        const res = await fetch(apiUrl("/api/game/ai-turn"), {
          method: "POST"
        });

        const result = await res.json();
        console.log("🤖 /api/game/ai-turn response:", result);
        if (result?.blocked === "pending_reaction") {
          if (result?.state) {
            this.updateState(result.state);
          }
          this.aiTurnInFlight = false;
          this.pendingWsState = null;
          this.scheduleLoop(loop, 1200);
          return;
        }

        const steps = Array.isArray(result?.steps) ? result.steps : [];
        if (steps.length > 0) {
          const step0 = steps[0];
          const unitId = step0?.unit_id || step0?.unit;
          const aiSource = String(step0?.source || "").toLowerCase();
          const sb3Status = String(step0?.sb3_status || "unknown");
          const sb3Reason = String(step0?.sb3_reason || "unknown");
          const sb3Meta = `sb3=${sb3Status}:${sb3Reason}`;
          if (aiSource.startsWith("heuristic")) {
            const actionId = step0?.action_id || "?";
            const ax = this.actionIdToAx(actionId);
            (window as any).logSystemEvent?.(
              "heuristic",
              `🧠 Heuristic AI (${unitId || "?"}): ${actionId} ${ax} [${aiSource}] [${sb3Meta}]`
            );
          }
          const corrected = !!step0?.corrected;
          if (corrected) {
            const proposed = step0?.proposed_action_id || "?";
            const executed = step0?.action_id || "?";
            const proposedAx = this.actionIdToAx(proposed);
            const executedAx = this.actionIdToAx(executed);
            const reason = step0?.corrected_reason || "backend_recovery";
            console.warn(
              "🤖 AI action corrected before execution",
              { unitId, proposed, executed, reason, source: step0?.source }
            );
            (window as any).logSystemEvent?.(
              "alert",
              `⚠️ AI corrected (${unitId || "?"}): ${proposed} ${proposedAx} -> ${executed} ${executedAx} [${reason}] [${sb3Meta}]`
            );
          }
          if (unitId) {
            setUnitActionMarker(unitId, resolveActionMarker(step0));
          }
          const stepType = String(step0?.type || step0?.kind || "").toUpperCase();
          const moveQ = step0?.move_q ?? step0?.move_to?.q ?? step0?.q;
          const moveR = step0?.move_r ?? step0?.move_to?.r ?? step0?.r;
          if (stepType === "MOVE" || step0?.kind === "move") {
            const coordStr = moveQ != null && moveR != null ? formatCoords(moveQ, moveR) : "?";
            (window as any).logSystemEvent?.("move", `🤖 AI Order: Move ${unitId || "?"} to hex ${coordStr}`);
          } else {
            const combat = this.describeCombatOrder(step0);
            (window as any).logSystemEvent?.(
              "combat",
              `⚔️ AI Order: ${combat.label} attack by ${unitId || "?"} on target ${combat.target}`
            );
            // If backend executed a combat order but produced no ACTION_EFFECT,
            // clarify that no dice were rolled (e.g. invalid/no target at resolution).
            const events = Array.isArray(result?.state?.last_events) ? result.state.last_events : [];
            const hasCombatEffect = events.some((ev: any) => {
              if (ev?.type !== "ACTION_EFFECT") return false;
              const p = ev?.payload || {};
              return String(p?.attacker || "") === String(unitId || "");
            });
            if (!hasCombatEffect) {
              (window as any).logSystemEvent?.(
                "system",
                `ℹ️ No dice roll for ${unitId || "?"}: combat did not resolve to ACTION_EFFECT.`
              );
            }
          }
        }
        (window as any).onAIOrders?.(steps);
        const animateOrder = (window as any).onAIAnimateOrder;
        if (typeof animateOrder === "function") {
          for (const step of steps) {
            try {
              await animateOrder(step);
            } catch {
              // keep loop resilient even if animation callback fails
            }
          }
        }

        const aiTurnState = result?.state || null;
        if (aiTurnState) {
          // Apply backend state after animating AI steps. If we sync first, unit
          // sprites snap to final coordinates and movement animations become no-op.
          this.updateState(aiTurnState);
        }

        // Log AI combat results to the System Log (the websocket MAP_STATE
        // payload does not carry last_events, so do it from the ai-turn result).
        logCombatEvents(result.state?.last_events, result.state?.units || []);

        // ✅ NUEVO: render visual de acciones IA
        if (steps.length > 0 && this.highlightLayer) {

          for (let i = 0; i < steps.length; i++) {

            const step = steps[i];

            setTimeout(() => {
              this.highlightLayer.highlightAction(step, this.state);
            }, i * 400); // delay animado
          }
        }
        const hasAiStep = steps.length > 0;
        this.aiTurnInFlight = false;
        if (this.pendingWsState) {
          // Never let deferred websocket state overwrite a terminal backend state.
          // This prevents losing done/winner/end_reason flags at match end.
          if (!aiTurnState || !aiTurnState.done) {
            this.mergeIncrementalState(this.pendingWsState);
            this.emit();
          }
          this.pendingWsState = null;
        }
        this.scheduleLoop(loop, hasAiStep ? 1100 : 1800);
        if (aiTurnState?.done) {
          this.stopLoop();
          return;
        }
        return;

      } catch (e) {
        console.error("❌ AI turn error", e);
        this.aiTurnInFlight = false;
        if (this.pendingWsState) {
          // pendingWsState comes from websocket MAP_STATE payloads, which are
          // incremental snapshots. Merge instead of replacing full state, or we
          // can lose `sides`/`active_side` and stall the AI scheduler.
          this.mergeIncrementalState(this.pendingWsState);
          this.emit();
          this.pendingWsState = null;
        }
        this.scheduleLoop(loop, 1800);
        return;
      }
    };

    this.loopFn = loop;
    loop();
  }

  // ----------------------------------
  private async loadReplay() {
    console.warn("Replay not implemented yet");
  }
}