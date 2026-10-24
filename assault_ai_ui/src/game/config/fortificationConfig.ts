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

export interface FortificationRenderConfig {
  scaleX: number;
  scaleY: number;
  edgeOffset: number;
  xNudge: number;
  yNudge: number;
  isCentered?: boolean;
}

export const FORTIFICATION_RENDER_DEFAULTS: FortificationRenderConfig = {
  scaleX: 1.25,
  scaleY: 1.25,
  edgeOffset: 0.0,
  xNudge: 0.0,
  yNudge: 0.0,
  isCentered: true,
};

export const FORTIFICATION_CONFIG: Record<
  string,
  { label: string; short: string; art: string; render: FortificationRenderConfig }
> = {
  trench: {
    label: "trench",
    short: "TR",
    art: "/art/terrain/Terrain Trenches.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  bunker: {
    label: "bunker",
    short: "BK",
    art: "/art/terrain/Terrain Bunker.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  casemate: {
    label: "casemate",
    short: "CS",
    art: "/art/terrain/Terrain Pillbox.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  pillbox: {
    label: "pillbox",
    short: "PB",
    art: "/art/terrain/Terrain Pillbox.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  gun_emplacement: {
    label: "gun emplacement",
    short: "GN",
    art: "/art/terrain/Terrain Gun Emplacement.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  barbed_wire: {
    label: "barbed wire",
    short: "WR",
    art: "/art/terrain/Terrain Barbed Wire.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  sandbag: {
    label: "sandbag",
    short: "SB",
    art: "/art/terrain/Terrain Sandbag Position.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  sandbag_position: {
    label: "sandbag position",
    short: "SB",
    art: "/art/terrain/Terrain Sandbag Position.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  tank_barricades: {
    label: "tank barricades",
    short: "TB",
    art: "/art/terrain/Terrain Tank Barricades.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  tank_barricade: {
    label: "tank barricade",
    short: "TB",
    art: "/art/terrain/Terrain Tank Barricades.png",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
  minefield: {
    label: "minefield",
    short: "MN",
    art: "",
    render: { scaleX: 1.25, scaleY: 1.25, edgeOffset: 0.0, xNudge: 0.0, yNudge: 0.0, isCentered: true },
  },
};

export function getFortificationArt(type: string): string {
  const clean = (type || "").toLowerCase().trim();
  return FORTIFICATION_CONFIG[clean]?.art ?? "";
}

export function getFortificationShort(type: string): string {
  const clean = (type || "").toLowerCase().trim();
  return FORTIFICATION_CONFIG[clean]?.short ?? clean.slice(0, 2).toUpperCase();
}

export function getFortificationRender(type: string): FortificationRenderConfig {
  const clean = (type || "").toLowerCase().trim();
  return FORTIFICATION_CONFIG[clean]?.render ?? FORTIFICATION_RENDER_DEFAULTS;
}
