// =================================================
// INPUT POINTER
// Pan (left) / Rotate (right) / Zoom (wheel)
// =================================================

window.attachPixiMouseInput = function (canvas, camera) {

  const zoomFactor = 1.1;
  const minZoom = 0.3;
  const maxZoom = 5.0;
  const rotateSensitivity = 0.005;

  let lastX = 0;
  let lastY = 0;
  let activePointerId = null;

  // Prevent browser gestures & context menu
  canvas.style.touchAction = "none";
  canvas.addEventListener("contextmenu", e => e.preventDefault());

  // -------------------------------------------------
  // POINTER DOWN
  // -------------------------------------------------
  canvas.addEventListener("pointerdown", e => {
    activePointerId = e.pointerId;
    canvas.setPointerCapture(e.pointerId);
    lastX = e.clientX;
    lastY = e.clientY;
  });

  // -------------------------------------------------
  // POINTER MOVE
  // -------------------------------------------------
  canvas.addEventListener("pointermove", e => {
    if (e.pointerId !== activePointerId) return;

    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;

    lastX = e.clientX;
    lastY = e.clientY;

    // LEFT BUTTON → PAN
    if (e.buttons & 1) {
      camera.x -= dx / camera.zoom;
      camera.y -= dy / camera.zoom;
    }

    // RIGHT BUTTON → ROTATE IN PLACE
    if (e.buttons & 2) {
      camera.rotation += dx * rotateSensitivity;
    }
  });

  // -------------------------------------------------
  // POINTER UP
  // -------------------------------------------------
  canvas.addEventListener("pointerup", e => {
    if (e.pointerId === activePointerId) {
      canvas.releasePointerCapture(e.pointerId);
      activePointerId = null;
    }
  });

  // -------------------------------------------------
  // ZOOM (centered on canvas)
  // -------------------------------------------------
  canvas.addEventListener(
    "wheel",
    e => {
      e.preventDefault();

      const factor = e.deltaY < 0 ? zoomFactor : 1 / zoomFactor;
      camera.zoom = Math.max(
        minZoom,
        Math.min(maxZoom, camera.zoom * factor)
      );
    },
    { passive: false }
  );

  console.log("[INPUT] pan (left), rotate (right), zoom");
};
