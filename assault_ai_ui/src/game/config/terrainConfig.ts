// ---------------------------------------------
// Terrain configuration
// ---------------------------------------------

export type TerrainType =
  | "clear"
  | "water"
  | "light_forest"
  | "olive_vine_grove"
  | "brush"
  | "rocky"
  | "building_single"
  | "building_multi";

// ---------------------------------------------
export const TERRAIN_CONFIG = {

  clear: {
    color: 0x3b3b3b,
    label: "clear",
    short: "C",
  },

  water: {
    color: 0x3366cc,
    label: "water",
    short: "W",
  },

  light_forest: {
    color: 0x6aa84f,
    label: "light forest",
    short: "LF",
  },

  olive_vine_grove: {
    color: 0x93c47d,
    label: "olive grove",
    short: "OG",
  },

  brush: {
    color: 0x9bbb59,
    label: "brush",
    short: "BR",
  },

  rocky: {
    color: 0x999999,
    label: "rocky",
    short: "R",
  },

  building_single: {
    color: 0x8b5a2b,
    label: "building",
    short: "B",
  },

  building_multi: {
    color: 0x5a3a1b,
    label: "building+",
    short: "B+",
  },

} as const;

// ---------------------------------------------
export function getTerrainColor(t: string): number {
  return TERRAIN_CONFIG[t as keyof typeof TERRAIN_CONFIG]?.color ?? 0xff00ff;
}

export function getTerrainLabel(t: string): string {
  return TERRAIN_CONFIG[t as keyof typeof TERRAIN_CONFIG]?.label ?? t;
}

export function getTerrainShort(t: string): string {
  return TERRAIN_CONFIG[t as keyof typeof TERRAIN_CONFIG]?.short ?? "?";
}
