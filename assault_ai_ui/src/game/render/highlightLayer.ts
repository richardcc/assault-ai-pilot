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
  // Draw attack targets (differentiated by tactical weapon type)
  // ---------------------------------------------
  drawAttacks(targets: any[]) {
    for (const t of targets) {
      const { x, y } = this.getCenter(t.q, t.r);
      const isIndirect = t.type === "ranged_indirect" || t.kind === "indirect";
      const isAssault = t.type === "assault";

      const g = new PIXI.Graphics();

      if (isIndirect) {
        // 💥 Purple Mortar / Indirect Artillery Bombardment Reticle (No-LOS required)
        g.circle(x, y, HEX_SIZE * 0.52);
        g.fill({ color: 0x9933ff, alpha: 0.28 });
        g.stroke({ width: 2.5, color: 0xcc66ff, alpha: 0.95 });

        const cross = HEX_SIZE * 0.28;
        g.moveTo(x - cross, y);
        g.lineTo(x + cross, y);
        g.moveTo(x, y - cross);
        g.lineTo(x, y + cross);
        g.stroke({ width: 2, color: 0xee99ff, alpha: 0.95 });

        g.circle(x, y, HEX_SIZE * 0.12);
        g.fill({ color: 0xffffff, alpha: 0.9 });
      } else if (isAssault) {
        // ⚔️ Crimson Close-Quarters Assault Breach Reticle
        g.circle(x, y, HEX_SIZE * 0.48);
        g.fill({ color: 0xff0044, alpha: 0.35 });
        g.stroke({ width: 2.5, color: 0xff3366, alpha: 1.0 });

        g.circle(x, y, HEX_SIZE * 0.22);
        g.fill({ color: 0xff2255, alpha: 0.85 });
      } else {
        // 🛡️ Standard Direct Ranged Fire / HMG Reticle
        g.circle(x, y, HEX_SIZE * 0.45);
        g.fill({ color: 0xff3333, alpha: 0.35 });
        g.stroke({ width: 2, color: 0xff6666, alpha: 0.9 });

        g.circle(x, y, HEX_SIZE * 0.14);
        g.fill({ color: 0xff5555, alpha: 0.9 });
      }

      g.zIndex = 1;
      this.container.addChild(g);
    }
  }

  // ---------------------------------------------
  // Draw weapon range / suppression aura
  // ---------------------------------------------
  drawWeaponAura(q: number, r: number, rangeHexes: number, role: string) {
    if (!rangeHexes || rangeHexes <= 0) return;
    const { x, y } = this.getCenter(q, r);
    const radius = Math.min(rangeHexes * HEX_SIZE * 1.55, 360);

    const isMortar = role === "indirect_mortar";
    const color = isMortar ? 0xaa44ff : 0xff9900;

    const g = new PIXI.Graphics();
    g.circle(x, y, radius);
    g.fill({ color, alpha: 0.05 });
    g.stroke({ width: 1.5, color, alpha: 0.35 });

    g.zIndex = 0;
    this.container.addChild(g);
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
      const isIndirect = type.includes("INDIRECT") || Boolean(unit?.has_indirect_fire);

      this.drawUnitHighlight(unit, isIndirect ? 0xaa44ff : 0xff4444);

      if (target) {
        this.drawUnitHighlight(target, isIndirect ? 0xcc66ff : 0xffa500);
        this.drawArrow(unit.q, unit.r, target.q, target.r, true, isIndirect);
      } else if (attackQ != null && attackR != null) {
        this.drawHexHighlight(attackQ, attackR, isIndirect ? 0x9933ff : 0xff6644);
        this.drawArrow(unit.q, unit.r, attackQ, attackR, true, isIndirect);
      }
    }

    // Release hold slightly after visuals are drawn.
    setTimeout(() => {
      this.holdClearUntilMs = 0;
    }, 950);
  }

  // ---------------------------------------------
  // Arrow (supports direct line and indirect mortar parabolic arc)
  // ---------------------------------------------
  drawArrow(fromQ: number, fromR: number, toQ: number, toR: number, isAttack = false, isIndirect = false) {

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

    const arrowColor = isIndirect ? 0xcc55ff : (isAttack ? 0xff4444 : 0x00f0ff);
    const arrowAlpha = 0.88;
    const headLen = 12;
    const headAngle = Math.PI / 5;

    const g = new PIXI.Graphics();

    if (isIndirect) {
      // Parabolic high-angle mortar flight trajectory
      const midX = (sx + ex) / 2;
      const midY = Math.min(sy, ey) - HEX_SIZE * 1.1;
      const tangAngle = Math.atan2(ey - midY, ex - midX);

      g.moveTo(sx, sy);
      g.quadraticCurveTo(midX, midY, ex, ey);
      g.stroke({ width: 2.5, color: arrowColor, alpha: arrowAlpha });

      g.moveTo(ex, ey);
      g.lineTo(
        ex - headLen * Math.cos(tangAngle - headAngle),
        ey - headLen * Math.sin(tangAngle - headAngle)
      );
      g.moveTo(ex, ey);
      g.lineTo(
        ex - headLen * Math.cos(tangAngle + headAngle),
        ey - headLen * Math.sin(tangAngle + headAngle)
      );
      g.stroke({ width: 2.5, color: arrowColor, alpha: arrowAlpha });

      g.circle(ex + nx * 4, ey + ny * 4, 4);
      g.fill({ color: arrowColor, alpha: 0.9 });
    } else {
      const angle = Math.atan2(dy, dx);

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
    }

    g.zIndex = 5;
    this.container.addChild(g);
  }
}