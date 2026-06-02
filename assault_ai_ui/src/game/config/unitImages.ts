export const unitImages = {
  GE_RIFLES_43: {
    label: "GE Rifles 43",
    full: "/art/counters/GE Rifles 43.png",
    half: "/art/counters/GE Rifles 43b.png",
    card: "/art/counters/GE Unit Rifles 43.jpg",
    card_half: "/art/counters/GE Unit Rifles 43b.jpg"
  },

  GE_FJ_RIFLES_43: {
    label: "GE FJ Rifles 43",
    full: "/art/counters/GE FJ Rifles 43.png",
    half: "/art/counters/GE FJ Rifles 43b.png"
  },

  GE_HEAVY_MG_42: {
    label: "GE Heavy MG 42",
    full: "/art/counters/GE HMG 42.png",
    half: "/art/counters/GE HMG 42b.png",
    card: "/art/counters/GE Unit Heavy MG42.jpg",
    card_half: "/art/counters/GE Unit Heavy MG42b.jpg"
  },

  GE_50MM_MORTAR: {
    label: "GE 50mm Mortar",
    full: "/art/counters/GE 50mm Mortar.png",
    half: "/art/counters/GE 50mm Mortarb.png",
    card: "/art/counters/GE Unit 50mm Mortar.jpg",
    card_half: "/art/counters/GE Unit 50mm Mortarb.jpg"
  },

  US_RIFLES_43: {
    label: "US Rifles 43",
    full: "/art/counters/US Rifles 43.png",
    half: "/art/counters/US Rifles 43b.png",
    card: "/art/counters/US Unit Rifles 43.jpg",
    card_half: "/art/counters/US Unit Rifles 43b.jpg"
  },

  US_RANGERS_43: {
    label: "US Rangers 43",
    full: "/art/counters/US Rangers 43.png",
    half: "/art/counters/US Rangers 43b.png",
    card: "/art/counters/US Unit Rangers 43.jpg",
    card_half: "/art/counters/US Unit Rangers 43b.jpg"
  },

  US_BAZOOKA_TEAM: {
    label: "US Bazooka Team 43",
    full: "/art/counters/US Bazooka Team 43.png",
    half: "/art/counters/US Bazooka Team 43b.png",
    card: "/art/counters/US Unit Bazooka Team 43.jpg",
    card_half: "/art/counters/US Unit Bazooka Team 43b.jpg"
  },

  US_81MM_MORTAR: {
    label: "US 81mm Mortar",
    full: "/art/counters/US 81mm Mortar.png",
    half: "/art/counters/US 81mm Mortarb.png",
    card: "/art/counters/US Unit 81mm Mortar.jpg",
    card_half: "/art/counters/US Unit 81mm Mortarb.jpg"
  }
};

export function getUnitCardArt(unitKey: string, hp?: number): string | undefined {
  const def = unitImages[unitKey as keyof typeof unitImages];
  if (!def) return undefined;
  if (hp === 1 && def.card_half) return def.card_half;
  return def.card;
}
