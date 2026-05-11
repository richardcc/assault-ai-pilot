// =================================================
// INPUT MOUSE
// Pan / Zoom / Rotate centered on mouse pointer
// =================================================

const MouseInput = (function () {

  function attach(canvas, camera, options = {}) {

    const {
      panButton = 0,            // Left mouse
      rotateButton = 2,         // Right mouse
      zoomFactor = 1.1,
      minZoom = 0.3,
      maxZoom = 4.0,
      rotateSensitivity = 0.005
    } = options;

    let isPanning = false;
    let isRotating = false;
    let lastX = 0;
    let lastY = 0;

    // -------------------------------------------------
    // Screen → World conversion (inverse camera transform)
    // -------------------------------------------------
    function getMouseWorldPos(e) {
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;

      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      let x = (sx - cx) / camera.zoom;
      let y = (sy - cy) / camera.zoom;

      const cos = Math.cos(-camera.rotation);
      const sin = Math.sin(-camera.rotation);

      const rx = x * cos - y * sin;
      const ry = x * sin + y * cos;

      return {
        x: rx + cx - camera.panX,
        y: ry + cy - camera.panY
      };
    }

    // -------------------------------------------------
    // Mouse handlers
    // -------------------------------------------------
    function onMouseDown(e) {
      lastX = e.clientX;
      lastY = e.clientY;

      if (e.button === panButton) isPanning = true;
      if (e.button === rotateButton) isRotating = true;
    }

    function onMouseUp() {
      isPanning = false;
      isRotating = false;
    }

    function onMouseMove(e) {
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;

      lastX = e.clientX;
      lastY = e.clientY;

      // -------------------------------------------------
      // PAN
      // -------------------------------------------------
      if (isPanning) {
        camera.panX += dx / camera.zoom;
        camera.panY += dy / camera.zoom;
      }

      // -------------------------------------------------
      // ROTATE (centered on mouse)
      // -------------------------------------------------
      if (isRotating) {
        const before = getMouseWorldPos(e);

        camera.rotation += dx * rotateSensitivity;

        const after = getMouseWorldPos(e);

        camera.panX += after.x - before.x;
        camera.panY += after.y - before.y;
      }
    }

    // -------------------------------------------------
    // ZOOM (centered on mouse)
    // -------------------------------------------------
    function onWheel(e) {
      e.preventDefault();

      const before = getMouseWorldPos(e);

      const factor = (e.deltaY < 0) ? zoomFactor : 1 / zoomFactor;
      camera.zoom = Math.min(
        maxZoom,
        Math.max(minZoom, camera.zoom * factor)
      );

      const after = getMouseWorldPos(e);

      camera.panX += after.x - before.x;
      camera.panY += after.y - before.y;
    }

    // -------------------------------------------------
    // Attach listeners
    // -------------------------------------------------
    canvas.oncontextmenu = e => e.preventDefault();

    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mouseup", onMouseUp);
    window.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    // -------------------------------------------------
    // Cleanup
    // -------------------------------------------------
    return function detach() {
      canvas.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("mousemove", onMouseMove);
      canvas.removeEventListener("wheel", onWheel);
    };
  }

  return {
    attach
  };

})();
