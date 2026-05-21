import * as PIXI from "pixi.js";

export function setupCamera(
  app: PIXI.Application,
  world: PIXI.Container,
  container: HTMLDivElement
) {
  // ----------------------------
  // ZOOM (wheel)
  // ----------------------------
  container.addEventListener("wheel", (e) => {
    if (e.shiftKey) return; // evita conflicto con rotate

    e.preventDefault();

    const scaleFactor = 1.1;
    const direction = e.deltaY > 0 ? 1 / scaleFactor : scaleFactor;

    const rect = app.canvas.getBoundingClientRect();

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const worldPosBefore = {
      x: (mouseX - world.x) / world.scale.x,
      y: (mouseY - world.y) / world.scale.y,
    };

    world.scale.x *= direction;
    world.scale.y *= direction;

    const worldPosAfter = {
      x: worldPosBefore.x * world.scale.x,
      y: worldPosBefore.y * world.scale.y,
    };

    world.x = mouseX - worldPosAfter.x;
    world.y = mouseY - worldPosAfter.y;
  });

  // ----------------------------
  // PAN (drag)
  // ----------------------------
  let dragging = false;
  let last = { x: 0, y: 0 };

  app.canvas.addEventListener("mousedown", (e) => {
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
  // ROTATE (shift + wheel)
  // ----------------------------
  container.addEventListener("wheel", (e) => {
    if (!e.shiftKey) return;

    e.preventDefault();

    const rect = app.canvas.getBoundingClientRect();

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const rotationAmount = e.deltaY * 0.001;

    const before = {
      x: (mouseX - world.x) / world.scale.x,
      y: (mouseY - world.y) / world.scale.y,
    };

    world.rotation += rotationAmount;

    const cos = Math.cos(rotationAmount);
    const sin = Math.sin(rotationAmount);

    const after = {
      x: before.x * cos - before.y * sin,
      y: before.x * sin + before.y * cos,
    };

    world.x = mouseX - after.x * world.scale.x;
    world.y = mouseY - after.y * world.scale.y;
  });
}
