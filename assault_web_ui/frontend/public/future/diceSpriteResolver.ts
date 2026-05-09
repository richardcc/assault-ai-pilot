// src/combat/diceSpriteResolver.ts
//
// Canonical dice sprite resolver.
//
// Responsibility:
// - Map a die result { color, faces } to a sprite filename.
// - NO game logic.
// - NO rendering.
// - Deterministic mapping only.
//
// Assumes replay format:
// {
//   color: "RED" | "YELLOW" | "GREEN" | "BLUE",
//   faces: string[]   // [] means BLANK
// }

export type DiceColor = "RED" | "YELLOW" | "GREEN" | "BLUE";
export type DiceFace = "CRITICAL" | "DAMAGE" | "SUPPRESS";

export interface DiceResultDTO {
  color: DiceColor;
  faces: DiceFace[];
}

// -------------------------------------------------
// Sprite table (matches your assets 1:1)
// -------------------------------------------------

const DICE_SPRITE_MAP: Record<
  DiceColor,
  Record<string, string>
> = {
  BLUE: {
    "": "blue_01.png",
    "DAMAGE": "blue_02.png",
  },

  GREEN: {
    "": "green_01.png",
    "DAMAGE": "green_02.png",
    "CRITICAL+DAMAGE": "green_03.png",
  },

  YELLOW: {
    "": "yellow_01.png",
    "DAMAGE": "yellow_02.png",
    "DAMAGE+DAMAGE": "yellow_03.png",
    "CRITICAL+DAMAGE": "yellow_04.png",
  },

  RED: {
    "": "red_01.png", // if ever used
    "DAMAGE": "red_01.png",
    "DAMAGE+DAMAGE": "red_03.png",
    "CRITICAL+DAMAGE": "red_04.png",
  },
};

// -------------------------------------------------
// Public API
// -------------------------------------------------

export function getDiceSprite(die: DiceResultDTO): string {
  const key = normalizeFaces(die.faces);
  const sprite = DICE_SPRITE_MAP[die.color][key];

  if (!sprite) {
    console.warn(
      "[DiceSpriteResolver] Missing sprite for",
      die.color,
      key
    );
    return "unknown.png";
  }

  return sprite;
}

// -------------------------------------------------
// Helpers
// -------------------------------------------------

function normalizeFaces(faces: DiceFace[]): string {
  if (!faces || faces.length === 0) {
    return "";
  }

  // Stable canonical order
  return [...faces].sort().join("+");
}
