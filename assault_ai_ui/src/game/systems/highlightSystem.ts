// File: systems/highlightSystem.ts

export function updateHighlights(
  layer: any,
  data: any,
  selectedUnitId: string | null,
  availableMoves: any[],
  hoverHex: { q: number; r: number } | null,
  orderHoverTarget: any | null,
  pendingReaction: any | null = null
) {
  if (!layer || !data) return;

  layer.clear();

  // 1. Find selected unit position
  let selectedUnit: any = null;

  if (selectedUnitId) {
    selectedUnit = data.units?.find((u: any) => u.id === selectedUnitId);

    if (selectedUnit) {
      layer.drawSelected(selectedUnit.q, selectedUnit.r);
    }
  }

  // 2. Draw all valid move/attack destinations
  const moves   = availableMoves.filter((m: any) => m.kind !== "attack");
  const attacks = availableMoves.filter((m: any) => m.kind === "attack");

  if (moves.length > 0)   layer.drawMoves(moves);
  if (attacks.length > 0) layer.drawAttacks(attacks);

  // 3. Draw hover highlight + directional arrow from unit to hovered hex or hovered attack target unit
  if (hoverHex && selectedUnit) {
    const hoverMove = moves.find((m: any) => m.q === hoverHex.q && m.r === hoverHex.r);
    const hoverAttack = attacks.find((a: any) => a.q === hoverHex.q && a.r === hoverHex.r);

    if (hoverMove || hoverAttack) {
      layer.drawHover(hoverHex.q, hoverHex.r);
      layer.drawArrow(
        selectedUnit.q, selectedUnit.r,
        hoverHex.q,     hoverHex.r,
        !!hoverAttack
      );

      if (hoverAttack && hoverAttack.target_id) {
        const targetUnit = data.units?.find(
          (u: any) => u.id === hoverAttack.target_id || u.unit_id === hoverAttack.target_id
        );

        if (targetUnit) {
          layer.drawUnitHighlight(targetUnit, 0xffcc44);
        }
      }
    }
  }

  // 4. Highlight dispatched order target from UI hover
  if (orderHoverTarget) {
    const targetQ = orderHoverTarget.target_q ?? orderHoverTarget.q;
    const targetR = orderHoverTarget.target_r ?? orderHoverTarget.r;
    const targetId = orderHoverTarget.target_id;
    const orderUnitId = orderHoverTarget.unit_id;
    const isAttack =
      orderHoverTarget.kind === "attack" ||
      /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/i.test(
        (orderHoverTarget.type || "").toString()
      );

    const sourceUnit =
      (orderUnitId
        ? data.units?.find(
            (u: any) => u.id === orderUnitId || u.unit_id === orderUnitId
          )
        : null) ?? selectedUnit;

    const targetUnitById = targetId
      ? data.units?.find(
          (u: any) => u.id === targetId || u.unit_id === targetId
        )
      : null;

    const unitsAtHex =
      targetQ != null && targetR != null
        ? (data.units ?? []).filter(
            (u: any) => u.q === targetQ && u.r === targetR
          )
        : [];

    const targetUnit = targetUnitById ?? unitsAtHex[0] ?? null;
    const destQ = targetUnit?.q ?? targetQ;
    const destR = targetUnit?.r ?? targetR;
    const moveQ = orderHoverTarget.move_q ?? orderHoverTarget.move_to?.q;
    const moveR = orderHoverTarget.move_r ?? orderHoverTarget.move_to?.r;

    if (destQ != null && destR != null) {
      const destColor = isAttack ? 0xff6644 : 0x00f0ff;
      layer.drawHexHighlight(destQ, destR, destColor);

      if (targetUnit) {
        layer.drawUnitHighlight(targetUnit, isAttack ? 0xffaa22 : 0x44ddff);
      }

      for (const u of unitsAtHex) {
        if (u !== targetUnit) {
          layer.drawUnitHighlight(u, 0x88aaff);
        }
      }

      if (sourceUnit) {
        layer.drawArrow(
          sourceUnit.q,
          sourceUnit.r,
          destQ,
          destR,
          isAttack
        );
      }
    }

    // Composite move/fire actions: also show movement destination.
    if (moveQ != null && moveR != null) {
        layer.drawHexHighlight(moveQ, moveR, 0x44ddff);
        if (sourceUnit) {
          layer.drawArrow(
            sourceUnit.q,
            sourceUnit.r,
            moveQ,
            moveR,
            false
          );
        }
    }
  }

  // 5. Highlight pending reaction participants while the popup is open.
  if (pendingReaction) {
    const reactorId = String(pendingReaction?.reactor_id || "");
    const targetId = String(pendingReaction?.target_id || "");
    const units = Array.isArray(data?.units) ? data.units : [];
    const reactor = units.find(
      (u: any) => String(u?.id || u?.unit_id || "") === reactorId
    );
    const target = units.find(
      (u: any) => String(u?.id || u?.unit_id || "") === targetId
    );

    if (reactor) {
      layer.drawUnitHighlight(reactor, 0xffcc44);
      layer.drawHexHighlight(reactor.q, reactor.r, 0xffcc44);
    }
    if (target) {
      layer.drawUnitHighlight(target, 0xff4444);
      layer.drawHexHighlight(target.q, target.r, 0xff4444);
    }
    if (reactor && target) {
      layer.drawArrow(reactor.q, reactor.r, target.q, target.r, true);
    }
  }
}
