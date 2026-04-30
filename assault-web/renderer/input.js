// renderer/input.js

export function screenToWorld(canvas, camera, screenX, screenY) {
  const rect = canvas.getBoundingClientRect();

  const x =
    (screenX - rect.left) / camera.zoom + camera.x;
  const y =
    (screenY - rect.top) / camera.zoom + camera.y;

  return { x, y };
}