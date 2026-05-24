import * as PIXI from "pixi.js";

export function setupCamera(
  app: PIXI.Application,
  world: PIXI.Container,
  container: HTMLDivElement
) {

  let dragging = false;
  let last = { x: 0, y: 0 };

  // ----------------------------
  // MOUSE DRAG
  // ----------------------------
  app.canvas.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    dragging = true;
    last.x = e.clientX;
    last.y = e.clientY;
  });

  window.addEventListener("mouseup", () => {
    dragging = false;
  });

  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;

    const dx = e.clientX - last.x;
    const dy = e.clientY - last.y;

    world.x += dx;
    world.y += dy;

    last.x = e.clientX;
    last.y = e.clientY;
  });

  // ----------------------------
  // ZOOM + ROTATE
  // ----------------------------
  const handleWheel = (e: WheelEvent) => {
    e.preventDefault();

    const rect = app.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (e.shiftKey) {
      // ROTATE
      const rot = e.deltaY * 0.001;

      const before = {
        x: (mouseX - world.x) / world.scale.x,
        y: (mouseY - world.y) / world.scale.y,
      };

      world.rotation += rot;

      const cos = Math.cos(rot);
      const sin = Math.sin(rot);

      const after = {
        x: before.x * cos - before.y * sin,
        y: before.x * sin + before.y * cos,
      };

      world.x = mouseX - after.x * world.scale.x;
      world.y = mouseY - after.y * world.scale.y;

    } else {
      // ZOOM
      const factor = 1.1;
      const dir = e.deltaY > 0 ? 1 / factor : factor;

      const before = {
        x: (mouseX - world.x) / world.scale.x,
        y: (mouseY - world.y) / world.scale.y,
      };

      world.scale.x *= dir;
      world.scale.y *= dir;

      const minScale = 0.5;
      const maxScale = 3;

      world.scale.x = Math.max(minScale, Math.min(maxScale, world.scale.x));
      world.scale.y = world.scale.x;

      const after = {
        x: before.x * world.scale.x,
        y: before.y * world.scale.y,
      };

      world.x = mouseX - after.x;
      world.y = mouseY - after.y;
    }
  };

  container.addEventListener("wheel", handleWheel);

  return () => {
    container.removeEventListener("wheel", handleWheel);
  };
}
