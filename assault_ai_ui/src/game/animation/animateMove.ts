export function animateMove(
  container: any,
  to: { x: number; y: number },
  ticker: any,
  duration = 300
) {
  if (!container || !ticker) return;

  const startX = container.x;
  const startY = container.y;

  // ✅ guard against invalid values
  if (
    isNaN(startX) ||
    isNaN(startY) ||
    isNaN(to.x) ||
    isNaN(to.y)
  ) {
    console.error("💣 INVALID POSITIONS", {
      id: container.__unitId,
      from: { x: startX, y: startY },
      to
    });
    return;
  }

  let time = 0;

  // ✅ block sync while animating
  container.__isMoving = true;

  const update = (delta: number) => {
    time += delta * (1000 / 60);

    const t = Math.min(time / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);

    container.x = startX + (to.x - startX) * ease;
    container.y = startY + (to.y - startY) * ease;

    // ✅ finish only once
    if (t >= 1) {
      ticker.remove(update);

      container.x = to.x;
      container.y = to.y;

      // ✅ release after frame
      if (t >= 1) {
        ticker.remove(update);

        container.x = to.x;
        container.y = to.y;

        container.__isMoving = false; // 💣 FIX REAL
      }
    }
  };

  ticker.add(update);
}
