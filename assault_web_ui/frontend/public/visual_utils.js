function highlightHexPair(
  q1, r1,
  q2, r2,
  app,
  options = {}
) {
  const {
    color1 = 0x3399ff, // attacker
    color2 = 0xff3333, // defender
    alpha = 0.45,
    duration = 1500
  } = options;

  const layer =
    app.stage.children.find(c => c.name === "overlayLayer") ||
    app.stage;

  // ✅ drawHexAt already uses the map's internal grid
  const hex1 = drawHexAt(q1, r1, color1, alpha);
  const hex2 = drawHexAt(q2, r2, color2, alpha);

  layer.addChild(hex1);
  layer.addChild(hex2);

  let elapsed = 0;

  function tick() {
    elapsed += app.ticker.elapsedMS;
    const pulse = 0.3 + Math.sin(elapsed / 120) * 0.2;

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

window.highlightHexPair = highlightHexPair;