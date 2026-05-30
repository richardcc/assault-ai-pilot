/**
 * Smoothly animates a PixiJS container from its current position to a target
 * pixel position using requestAnimationFrame and cubic ease-in-out.
 * Blocks re-entry via __isMoving. Always calls onComplete (with safety timeout).
 */
export function animateMove(
  container: any,
  to: { x: number; y: number },
  _ticker: any,           // kept for API compat, not used
  duration = 380,
  onComplete?: () => void
) {
  if (!container) {
    onComplete?.();
    return;
  }

  const startX = container.x;
  const startY = container.y;

  // Guard: invalid positions
  if (
    !isFinite(startX) || !isFinite(startY) ||
    !isFinite(to.x)   || !isFinite(to.y)
  ) {
    console.error("❌ animateMove: invalid positions", {
      id: container.__unitId,
      from: { x: startX, y: startY },
      to,
    });
    onComplete?.();
    return;
  }

  // Already at destination
  if (Math.abs(startX - to.x) < 0.5 && Math.abs(startY - to.y) < 0.5) {
    container.x = to.x;
    container.y = to.y;
    onComplete?.();
    return;
  }

  // Block double-dispatch
  container.__isMoving = true;

  const startTime = performance.now();

  // Safety timeout — always resolves even if rAF never fires
  const safetyTimer = setTimeout(() => {
    container.x = to.x;
    container.y = to.y;
    container.__isMoving = false;
    onComplete?.();
  }, duration + 200);

  function frame(now: number) {
    const t = Math.min((now - startTime) / duration, 1);

    // Cubic ease-in-out
    const ease = t < 0.5
      ? 4 * t * t * t
      : 1 - Math.pow(-2 * t + 2, 3) / 2;

    container.x = startX + (to.x - startX) * ease;
    container.y = startY + (to.y - startY) * ease;

    if (t < 1) {
      requestAnimationFrame(frame);
    } else {
      // Snap exactly to target
      container.x = to.x;
      container.y = to.y;
      container.__isMoving = false;
      clearTimeout(safetyTimer);
      onComplete?.();
    }
  }

  requestAnimationFrame(frame);
}
