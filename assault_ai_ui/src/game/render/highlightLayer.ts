import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";

export class HighlightLayer {

  private container: PIXI.Container;
  private holdClearUntilMs = 0;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.zIndex = 1000;

    world.addChild(this.container);
    world.sortableChildren = true;
  }

  clear(force: boolean = false) {
    if (!force && Date.now() < this.holdClearUntilMs) {
      return;
    }
    this.container.removeChildren();
  }

  private getCenter(q: number, r: number) {
    const { x, y } = axialToPixel(q, r);
    return {
      x: Math.round(x),
      y: Math.round(y + HEX_SIZE),
    };
  }

  // ---------------------------------------------
  // ✅ NUEVO: highlight unit
  // ---------------------------------------------
  drawUnitHighlight(unit: any, color = 0xffff00) {
    const { x, y } = this.getCenter(unit.q, unit.r);

    const g = new PIXI.Graphics();
    g.circle(x, y, HEX_SIZE * 0.55);
    g.fill({ color, alpha: 0.2 });
    g.stroke({ width: 3, color, alpha: 1 });

    g.zIndex = 10;
    this.container.addChild(g);
  }

  // ---------------------------------------------
  // ✅ NUEVO: highlight hex
  // ---------------------------------------------
  drawHexHighlight(q: number, r: number, color = 0x00ff00) {
    const { x, y } = this.getCenter(q, r);

    const g = new PIXI.Graphics();
    g.circle(x, y, HEX_SIZE * 0.5);
    g.fill({ color, alpha: 0.25 });
    g.stroke({ width: 2, color, alpha: 0.9 });

    g.zIndex = 9;
    this.container.addChild(g);
  }

  // ---------------------------------------------
  // Draw valid move destinations
  // ---------------------------------------------
  drawMoves(moves: any[]) {
    for (const m of moves) {
      const { x, y } = this.getCenter(m.q, m.r);

      const g = new PIXI.Graphics();

      g.circle(x, y, HEX_SIZE * 0.5);
      g.fill({ color: 0x3399ff, alpha: 0.15 });
      g.stroke({ width: 1.5, color: 0x66ccff, alpha: 0.6 });

      g.circle(x, y, HEX_SIZE * 0.15);
      g.fill({ color: 0x66ccff, alpha: 0.9 });

      g.zIndex = 1;
      this.container.addChild(g);
    }
  }

  // ---------------------------------------------
  // Draw attack targets
  // ---------------------------------------------
  drawAttacks(targets: { q: number; r: number }[]) {
    for (const t of targets) {
      const { x, y } = this.getCenter(t.q, t.r);

      const g = new PIXI.Graphics();

      g.circle(x, y, HEX_SIZE * 0.45);
      g.fill({ color: 0xff3333, alpha: 0.35 });
      g.stroke({ width: 2, color: 0xff6666, alpha: 0.9 });

      g.zIndex = 1;
      this.container.addChild(g);
    }
  }

  // ---------------------------------------------
  // Draw selected unit hex highlight
  // ---------------------------------------------
  drawSelected(q: number, r: number) {
    const { x, y } = this.getCenter(q, r);

    const g = new PIXI.Graphics();

    g.circle(x, y, HEX_SIZE * 0.52);
    g.fill({ color: 0x00ff88, alpha: 0.18 });
    g.stroke({ width: 2.5, color: 0x00ff88, alpha: 0.95 });

    g.zIndex = 3;
    this.container.addChild(g);
  }

  // ---------------------------------------------
  // Draw hover hex highlight
  // ---------------------------------------------
  drawHover(q: number, r: number) {
    const { x, y } = this.getCenter(q, r);

    const g = new PIXI.Graphics();

    g.circle(x, y, HEX_SIZE * 0.5);
    g.fill({ color: 0xffff00, alpha: 0.2 });
    g.stroke({ width: 2, color: 0xffcc00, alpha: 0.9 });

    g.zIndex = 2;
    this.container.addChild(g);
  }

  // ---------------------------------------------
  // ✅ 🔥 ACTION HIGHLIGHT (LO QUE QUERÍAS)
  // ---------------------------------------------
  highlightAction(action: any, state: any) {

    if (!action || !state) return;

    // Keep action highlight visible briefly even if reactive hover/selection
    // updates trigger frequent clear() calls.
    this.holdClearUntilMs = Date.now() + 900;
    this.clear(true);

    const actorId =
      action.unit_id ??
      action.unit ??
      action.actor_id ??
      action.attacker_id ??
      action.source_id;
    const targetId =
      action.target_id ??
      action.target?.id ??
      action.defender_id ??
      action.enemy_id;
    const unit = state.units?.find(
      (u: any) => u.id === actorId || u.unit_id === actorId
    );
    if (!unit) return;

    const type = String(action.type || action.kind || action.action || "").toUpperCase();
    const targetQ = action.target_q ?? action.move_q ?? action.q ?? action.target?.q ?? action.move_to?.q;
    const targetR = action.target_r ?? action.move_r ?? action.r ?? action.target?.r ?? action.move_to?.r;
    const hasTargetUnit = Boolean(targetId);
    const attackQ =
      action.attack_q ??
      action.target_q ??
      action.target?.q ??
      action.q;
    const attackR =
      action.attack_r ??
      action.target_r ??
      action.target?.r ??
      action.r;
    const isMove =
      type === "MOVE" ||
      type.includes("MOVE") ||
      (!hasTargetUnit && targetQ != null && targetR != null);
    const isAttack =
      type === "ATTACK" ||
      type.includes("ATTACK") ||
      type.includes("RANGED") ||
      type.includes("ASSAULT") ||
      type.includes("FIRE") ||
      hasTargetUnit;

    // ---------------- MOVE ----------------
    if (isMove && targetQ != null && targetR != null) {
      this.drawUnitHighlight(unit, 0x00ccff);
      this.drawHexHighlight(targetQ, targetR, 0x00ff00);
      this.drawArrow(unit.q, unit.r, targetQ, targetR, false);
    }

    // ---------------- ATTACK ----------------
    if (isAttack) {
      const target = state.units?.find(
        (u: any) => u.id === targetId || u.unit_id === targetId
      );

      this.drawUnitHighlight(unit, 0xff4444);

      if (target) {
        this.drawUnitHighlight(target, 0xffa500);
        this.drawArrow(unit.q, unit.r, target.q, target.r, true);
      } else if (attackQ != null && attackR != null) {
        this.drawHexHighlight(attackQ, attackR, 0xff6644);
        this.drawArrow(unit.q, unit.r, attackQ, attackR, true);
      }
    }

    // Release hold slightly after visuals are drawn.
    setTimeout(() => {
      this.holdClearUntilMs = 0;
    }, 950);
  }

  // ---------------------------------------------
  // Arrow (sin cambios)
  // ---------------------------------------------
  drawArrow(fromQ: number, fromR: number, toQ: number, toR: number, isAttack = false) {

    const from = this.getCenter(fromQ, fromR);
    const to = this.getCenter(toQ, toR);

    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const len = Math.sqrt(dx * dx + dy * dy);

    if (len < 1) return;

    const nx = dx / len;
    const ny = dy / len;

    const startGap = HEX_SIZE * 0.35;
    const endGap = HEX_SIZE * 0.4;

    const sx = from.x + nx * startGap;
    const sy = from.y + ny * startGap;
    const ex = to.x - nx * endGap;
    const ey = to.y - ny * endGap;

    const arrowColor = isAttack ? 0xff4444 : 0x00f0ff;
    const arrowAlpha = 0.85;
    const headLen = 12;
    const headAngle = Math.PI / 5;
    const angle = Math.atan2(dy, dx);

    const g = new PIXI.Graphics();

    g.moveTo(sx, sy);
    g.lineTo(ex, ey);
    g.stroke({ width: 2.5, color: arrowColor, alpha: arrowAlpha });

    g.moveTo(ex, ey);
    g.lineTo(
      ex - headLen * Math.cos(angle - headAngle),
      ey - headLen * Math.sin(angle - headAngle)
    );
    g.moveTo(ex, ey);
    g.lineTo(
      ex - headLen * Math.cos(angle + headAngle),
      ey - headLen * Math.sin(angle + headAngle)
    );
    g.stroke({ width: 2.5, color: arrowColor, alpha: arrowAlpha });

    g.circle(ex + nx * 4, ey + ny * 4, 4);
    g.fill({ color: arrowColor, alpha: 0.9 });

    g.zIndex = 5;
    this.container.addChild(g);
  }
}