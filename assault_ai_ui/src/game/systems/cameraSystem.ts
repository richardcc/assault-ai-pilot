// File: C:\repos\python\assault\assault_ai_ui\src\game\systems\cameraSystem.ts

import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";

export function registerFocusUnit(worldRef: any, appRef: any, lastStateRef: any) {

  (window as any).focusUnit = (unitId: string) => {

    const data = lastStateRef.current;
    if (!data?.units) return;

    const unit = data.units.find((u: any) => u.id === unitId);
    if (!unit) return;

    const { x, y } = axialToPixel(unit.q, unit.r);

    const world = worldRef.current;
    const app = appRef.current;

    if (!world || !app) return;

    world.pivot.set(x, y + HEX_SIZE);
    world.position.set(
      app.renderer.width / 2,
      app.renderer.height / 2
    );
  };
}