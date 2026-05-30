// File: render/highlightLayer.ts

import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";

export class HighlightLayer {

  private container: PIXI.Container;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.zIndex = 1000;

    world.addChild(this.container);
    world.sortableChildren = true;
  }

  clear() {
    this.container.removeChildren();
  }

  // Centralised pixel centre calculation
  private getCenter(q: number, r: number) {
    const { x, y } = axialToPixel(q, r);
    return {
      x: Math.round(x),
      y: Math.round(y + HEX_SIZE),
    };
  }

  // ---------------------------------------------
  // Draw valid move destinations
  // ---------------------------------------------
  drawMoves(moves: any[]) {
    for (const m of moves) {
      const { x, y } = this.getCenter(m.q, m.r);

      const g = new PIXI.Graphics();

      // Outer glow ring
      g.circle(x, y, HEX_SIZE * 0.5);
      g.fill({ color: 0x3399ff, alpha: 0.15 });
      g.stroke({ width: 1.5, color: 0x66ccff, alpha: 0.6 });

      // Inner dot
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

    // Pulsing glow ring
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
  // Draw vector arrow from selected unit to hover destination
  // Called when hovering over a valid move hex with a unit selected
  // ---------------------------------------------
  drawArrow(
    fromQ: number, fromR: number,
    toQ: number, toR: number,
    isAttack = false
  ) {
    const from = this.getCenter(fromQ, fromR);
    const to   = this.getCenter(toQ, toR);

    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const len = Math.sqrt(dx * dx + dy * dy);

    if (len < 1) return;

    const nx = dx / len;
    const ny = dy / len;

    // Shorten shaft so it doesn't overlap the unit/destination circles
    const startGap = HEX_SIZE * 0.35;
    const endGap   = HEX_SIZE * 0.4;

    const sx = from.x + nx * startGap;
    const sy = from.y + ny * startGap;
    const ex = to.x   - nx * endGap;
    const ey = to.y   - ny * endGap;

    const arrowColor = isAttack ? 0xff4444 : 0x00f0ff;
    const arrowAlpha = 0.85;
    const headLen    = 12;
    const headAngle  = Math.PI / 5;
    const angle      = Math.atan2(dy, dx);

    const g = new PIXI.Graphics();

    // Shaft
    g.moveTo(sx, sy);
    g.lineTo(ex, ey);
    g.stroke({ width: 2.5, color: arrowColor, alpha: arrowAlpha });

    // Arrowhead (two lines)
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

    // Tip dot at destination
    g.circle(ex + nx * 4, ey + ny * 4, 4);
    g.fill({ color: arrowColor, alpha: 0.9 });

    g.zIndex = 5;
    this.container.addChild(g);
  }
}
