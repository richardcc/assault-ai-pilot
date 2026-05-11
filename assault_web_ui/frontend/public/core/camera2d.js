// =================================================
// CAMERA 2D
// Generic 2D camera (pan / zoom / rotation)
// Pure logic, no rendering, no input
// =================================================

const Camera2D = (function () {

  function create(initial = {}) {
    return {
      panX: initial.panX || 0,
      panY: initial.panY || 0,
      zoom: initial.zoom || 1.0,
      rotation: initial.rotation || 0
    };
  }

  // -------------------------------------------------
  // Apply camera transform to a canvas context
  // -------------------------------------------------
  function apply(ctx, canvas, camera) {

    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    ctx.translate(cx, cy);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.rotate(camera.rotation);
    ctx.translate(-cx + camera.panX, -cy + camera.panY);
  }

  // -------------------------------------------------
  // Center camera on a world position
  // -------------------------------------------------
  function centerOn(camera, worldX, worldY, canvas) {
    camera.panX = worldX - canvas.width / 2;
    camera.panY = worldY - canvas.height / 2;
  }

  // -------------------------------------------------
  // Clamp camera pan to world bounds (NO rotation)
  // -------------------------------------------------
  function clampToBounds(camera, bounds, canvas) {

    if (Math.abs(camera.rotation) > 0.0001) {
      // Rotated camera: clamping not supported
      return;
    }

    const viewW = canvas.width / camera.zoom;
    const viewH = canvas.height / camera.zoom;

    const minX = bounds.minX - viewW / 2;
    const maxX = bounds.maxX - viewW / 2;
    const minY = bounds.minY - viewH / 2;
    const maxY = bounds.maxY - viewH / 2;

    camera.panX = Math.min(Math.max(camera.panX, minX), maxX);
    camera.panY = Math.min(Math.max(camera.panY, minY), maxY);
  }

  // -------------------------------------------------
  // Zoom helpers
  // -------------------------------------------------
  function zoomIn(camera, factor = 1.1, max = 4.0) {
    camera.zoom = Math.min(camera.zoom * factor, max);
  }

  function zoomOut(camera, factor = 1.1, min = 0.3) {
    camera.zoom = Math.max(camera.zoom / factor, min);
  }

  // -------------------------------------------------
  // Rotate helper
  // -------------------------------------------------
  function rotate(camera, delta) {
    camera.rotation += delta;
  }

  return {
    create,
    apply,
    centerOn,
    clampToBounds,
    zoomIn,
    zoomOut,
    rotate
  };

})();