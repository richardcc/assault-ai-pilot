// -------------------------------------------------
// PixiJS bootstrap – Phase 2
// FASE 1: call map renderer (grid only)
// -------------------------------------------------

// -------------------------------------------------
// 1) Root container
// -------------------------------------------------
const root = document.getElementById("pixi-root");

// -------------------------------------------------
// 2) Pixi application
// -------------------------------------------------
const app = new PIXI.Application({
  resizeTo: root,
  backgroundColor: 0x1e1e1e,
  antialias: true
});

root.appendChild(app.view);

// -------------------------------------------------
// 3) Call map renderer (FASE 1)
// -------------------------------------------------
// NOTE: map_renderer.js defines renderGrid(...)
renderGrid(app, SCENARIO);
