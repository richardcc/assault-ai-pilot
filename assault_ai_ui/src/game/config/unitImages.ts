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

  IT_RIFLES_43: {
    label: "IT Rifles 43",
    full: "/art/counters/IT Rifles 43.png",
    half: "/art/counters/IT Rifles 43b.png",
    card: "/art/counters/IT Unit Rifles 43.jpg",
    card_half: "/art/counters/IT Unit Rifles 43b.jpg"
  },

  IT_LMG_SQUAD_43: {
    label: "IT LMG Squad 43",
    full: "/art/counters/IT LMG Squad 43.png",
    half: "/art/counters/IT LMG Squad 43b.png",
    card: "/art/counters/IT Unit LMG Squad 43.jpg",
    card_half: "/art/counters/IT Unit LMG Squad 43b.jpg"
  },

  IT_SOLOTHURN_ATR_43: {
    label: "IT Solothurn ATR 43",
    full: "/art/counters/IT Solothurn ATR 43.png",
    half: "/art/counters/IT Solothurn ATR 43b.png",
    card: "/art/counters/IT Unit Solothurn ATR 43.jpg",
    card_half: "/art/counters/IT Unit Solothurn ATR 43b.jpg"
  },

  IT_20MM_BREDA_AA_43: {
    label: "IT 20mm Breda AA 43",
    full: "/art/counters/IT 20mm Breda AA 43.png",
    half: "/art/counters/IT 20mm Breda AAb.png",
    card: "/art/counters/IT Unit 20mm Breda AA.jpg",
    card_half: "/art/counters/IT Unit 20mm Breda AAb.jpg"
  },

  IT_BREDA_MMG: {
    label: "IT Breda MMG",
    full: "/art/counters/IT Breda MMG.png",
    half: "/art/counters/IT Breda MMG.png",
    card: "/art/counters/IT Unit Breda MMG.jpg",
    card_half: "/art/counters/IT Unit Breda MMG.jpg"
  },

  IT_SNIPER_43: {
    label: "IT Sniper 43",
    full: "/art/counters/IT Sniper 43.png",
    half: "/art/counters/IT Sniper 43b.png",
    card: "/art/counters/IT Unit Sniper 43.jpg",
    card_half: "/art/counters/IT Unit Sniper 43b.jpg"
  },

  IT_45MM_BRIXIA: {
    label: "IT 45mm Brixia",
    full: "/art/counters/IT 45mm Brixia Team.png",
    half: "/art/counters/IT 45mm Brixia Teamb.png",
    card: "/art/counters/IT Unit 45mm Brixia Mortar.jpg",
    card_half: "/art/counters/IT Unit 45mm Brixia Mortarb.jpg"
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
