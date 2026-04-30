export class Camera {
  constructor() {
    this.x = 0;
    this.y = 0;
    this.zoom = 1.0;
  }

  worldToScreen(wx, wy) {
    return {
      x: (wx - this.x) * this.zoom,
      y: (wy - this.y) * this.zoom
    };
  }
}
``