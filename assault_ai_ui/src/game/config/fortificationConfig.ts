// ---------------------------------------------
// Fortification configuration
// ---------------------------------------------

export type FortificationType =
  | "trench"
  | "bunker"
  | "casemate"
  | "pillbox"
  | "gun_emplacement"
  | "barbed_wire"
  | "sandbag"
  | "tank_barricades"
  | "minefield";

export const FORTIFICATION_RENDER_DEFAULTS = {
  scaleX: 1.7,
  scaleY: 1.5,
  edgeOffset: 0.,
  xNudge: -0.26,
  yNudge: .10,
} as const;

export const FORTIFICATION_CONFIG = {
  trench: {
    label: "trench",
    short: "TR",
    art: "/art/terrain/Terrain Trenches.png",
  },
  bunker: {
    label: "bunker",
    short: "BK",
    art: "/art/terrain/Terrain Bunker.png",
  },
  casemate: {
    label: "casemate",
    short: "CS",
    art: "/art/terrain/Terrain Pillbox.png",
  },
  pillbox: {
    label: "pillbox",
    short: "PB",
    art: "/art/terrain/Terrain Pillbox.png",
  },
  gun_emplacement: {
    label: "gun emplacement",
    short: "GN",
    art: "/art/terrain/Terrain Gun Emplacement.png",
  },
  barbed_wire: {
    label: "barbed wire",
    short: "WR",
    art: "/art/terrain/Terrain Barbed Wire.png",
  },
  sandbag: {
    label: "sandbag",
    short: "SB",
    art: "/art/terrain/Terrain Sandbag Position.png",
  },
  tank_barricades: {
    label: "tank barricades",
    short: "TB",
    art: "/art/terrain/Terrain Tank Barricades.png",
  },
  minefield: {
    label: "minefield",
    short: "MN",
    art: "",
  },
} as const;

export function getFortificationArt(type: string): string {
  return FORTIFICATION_CONFIG[type as keyof typeof FORTIFICATION_CONFIG]?.art ?? "";
}

export function getFortificationShort(type: string): string {
  return FORTIFICATION_CONFIG[type as keyof typeof FORTIFICATION_CONFIG]?.short ?? type.slice(0, 2).toUpperCase();
}

export function getFortificationRender(type: string) {
  return FORTIFICATION_RENDER_DEFAULTS;
}
