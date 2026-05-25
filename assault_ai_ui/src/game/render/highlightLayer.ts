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

  // ✅ CENTRALIZAMOS EL CÁLCULO (CLAVE)
  private getCenter(q: number, r: number) {
    const { x, y } = axialToPixel(q, r);

    return {
      x: Math.round(x),
      y: Math.round(y + HEX_SIZE),
    };
  }

  // ---------------------------------------------
  drawMoves(moves: any[]) {

    for (const m of moves) {

      const { x, y } = this.getCenter(m.q, m.r);

      const g = new PIXI.Graphics();

      g.circle(x, y, HEX_SIZE * 0.45);

      g.fill({
        color: 0x3399ff,
        alpha: 0.35
      });

      g.stroke({
        width: 2,
        color: 0x66ccff,
        alpha: 0.8
      });

      g.zIndex = 1;

      this.container.addChild(g);
    }
  }

  // ---------------------------------------------
  drawSelected(q: number, r: number) {

    const { x, y } = this.getCenter(q, r);

    const g = new PIXI.Graphics();

    g.circle(x, y, HEX_SIZE * 0.5);

    g.fill({
      color: 0x33ff33,
      alpha: 0.25
    });

    g.stroke({
      width: 3,
      color: 0x00ff00,
      alpha: 0.9
    });

    g.zIndex = 3;

    this.container.addChild(g);
  }

  // ---------------------------------------------
  drawHover(q: number, r: number) {

    const { x, y } = this.getCenter(q, r);

    const g = new PIXI.Graphics();

    g.circle(x, y, HEX_SIZE * 0.5);

    g.fill({
      color: 0xffff00,
      alpha: 0.2
    });

    g.stroke({
      width: 2,
      color: 0xffcc00,
      alpha: 0.9
    });

    g.zIndex = 2;

    this.container.addChild(g);
  }

  // ---------------------------------------------
  drawAttacks(targets: { q: number, r: number }[]) {

    for (const t of targets) {

      const { x, y } = this.getCenter(t.q, t.r);

      const g = new PIXI.Graphics();

      g.circle(x, y, HEX_SIZE * 0.45);

      g.fill({
        color: 0xff3333,
        alpha: 0.35
      });

      g.stroke({
        width: 2,
        color: 0xff6666,
        alpha: 0.9
      });

      g.zIndex = 1;

      this.container.addChild(g);
    }
  }
}
