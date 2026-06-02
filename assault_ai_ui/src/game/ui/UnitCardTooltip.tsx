import { useState } from "react";
import { createPortal } from "react-dom";
import { getUnitCardArt, unitImages } from "../config/unitImages";

const overlayRoot = () =>
  document.getElementById("overlay-root") ?? document.body;

type UnitCardTooltipProps = {
  unitKey: string;
  hp?: number;
  anchorX: number;
  anchorY: number;
};

export function UnitCardTooltip({ unitKey, hp, anchorX, anchorY }: UnitCardTooltipProps) {
  const art = getUnitCardArt(unitKey, hp);
  const [src, setSrc] = useState(art);

  if (!art) return null;

  const label = unitImages[unitKey as keyof typeof unitImages]?.label || unitKey;
  const bottom = window.innerHeight - anchorY + 10;

  return createPortal(
    <div
      className="unit-card-hover-preview"
      style={{ left: anchorX, bottom }}
    >
      <img
        src={encodeURI(src || art)}
        alt={label}
        onError={() => {
          if (src?.includes("/art/counters/")) {
            setSrc(src.replace("/art/counters/", "/art/unit_cards/"));
          }
        }}
      />
    </div>,
    overlayRoot()
  );
}
