# Annex B - PDF Traceability (Rule -> Implementation Mapping)

## 1. Canonical Sources

- Core Rulebook: `2024_09_18_Rulebook_rev6_web.pdf`
- LOS Examples: `2024_10_LOS_Examples_v1.pdf`
- Terrain/Support Aid: `PN007_GameAid_Back_rev3_web.pdf`
- Terrain Clarification: `TEC_Clarification.pdf`
- Campaign: `ITA_Assault_Libro_Campagna_v1.0.pdf`
- Optional FoW: `2025_09_10_FoW_v01.pdf`

## 2. Mapping Matrix

| PDF section family | Documentation chapter | Engine concern |
| --- | --- | --- |
| Ch. 6-8 phase and action flow | `02_TURN_SEQUENCE_AND_ACTIONS.md` | phase machine, legal actions, activation |
| Ch. 9 movement and terrain | `03_MOVEMENT_AND_TERRAIN.md` | pathing, terrain costs, objective entry |
| Ch. 10 LOS/spotting/fire | `04_LOS_SPOTTING_AND_RANGED_FIRE.md` | LOS states, spotting gates, ranged dice |
| Ch. 11 close combat | `05_CLOSE_COMBAT_AND_CRITICALS.md` | close-combat rounds, critical routing |
| Ch. 12 TAS/OAS | `06_TAS_OAS_AND_TERRAIN_DAMAGE.md` | support sequence, blast, crater mutation |
| Campaign book | `07_GELA_CAMPAIGN.md` | persistent progression and branching |
| FoW module | `08_OPTIONAL_FOW_RULES.md` | contact markers, reveal, recon |

## 3. Review Procedure

When any PDF changes:

1. identify impacted chapter(s),
2. update corresponding markdown chapter(s),
3. validate code-path alignment,
4. log update date in roadmap backlog.

## 4. Coverage Status Semantics

Use this status vocabulary in roadmap/backlog:

- `implemented`: behavior exists and is test-covered,
- `implemented-partial`: behavior exists with known gaps,
- `documented-only`: behavior specified but not coded,
- `unknown`: not yet assessed.

## 5. Known Work Item

Create and maintain `docs/GAP_ANALYSIS.md` with:

- vendor requirement,
- current implementation status,
- gap severity (high/medium/low),
- owner and target milestone.
