// -------------------------------------------------
// Visual Effects Helpers (shared)
// -------------------------------------------------

function highlightHexPair(
  q1, r1,
  q2, r2,
  grid,
  app,
  options = {}
) {
  const {
    color1 = 0x3399ff, // attacker
    color2 = 0xff3333, // defender
    alpha1 = 0.45,
    alpha2 = 0.55,
    duration = 600
  } = options;

  const layer =
    app.stage.children.find(c => c.name === "overlayLayer") ||
    app.stage;

  const hex1 = drawHexAt(q1, r1, grid, color1, alpha1);
  const hex2 = drawHexAt(q2, r2, grid, color2, alpha2);

  layer.addChild(hex1);
  layer.addChild(hex2);

  let elapsed = 0;

  function tick() {
    elapsed += app.ticker.elapsedMS;
    const t = elapsed / duration;
    const pulse = 0.25 + Math.sin(t * Math.PI * 2) * 0.18;

    hex1.alpha = pulse;
    hex2.alpha = pulse;

    if (elapsed >= duration) {
      app.ticker.remove(tick);
      layer.removeChild(hex1);
      layer.removeChild(hex2);
      hex1.destroy();
      hex2.destroy();
    }
  }

  app.ticker.add(tick);
}

// Expose globally (same pattern you already use)
window.highlightHexPair = highlightHexPair;