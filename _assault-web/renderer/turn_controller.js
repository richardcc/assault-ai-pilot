export function renderTurnWithTransition({
  ctx,
  camera,
  maps,
  state,
  prevState,
  drawBackground,
  drawUnits,
  highlightFn,
  explainFn,
  delay = 400
}) {
  if (!state.decision || !prevState) {
    drawBackground();
    drawUnits(state.units);
    return;
  }

  drawBackground();
  drawUnits(prevState.units);

  highlightFn(state, prevState);
  explainFn(state, prevState);

  setTimeout(() => {
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    drawBackground();
    drawUnits(state.units);
  }, delay);
}