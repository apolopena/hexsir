# Talent names (partial)

Working list of talent names observed during save-format experiments and asset-tree archaeology. **Not comprehensive** — full canonical lists per hero live on the [Ravenswatch wiki](https://ravenswatch.fandom.com/wiki/Heroes). This doc is a working reference for the talent record reverse-engineering work, and gets populated as we encounter specific talent IDs in saves and gameplay.

**Status:** partial; expanded as new saves / experiments surface more names.
**Created:** 2026-04-27

## Talent rarity tiers

Each talent has a rarity tier: **Common**, **Rare**, **Epic**, **Legendary**. Tier is a property of the talent in a specific run, not a separate talent — i.e., the same talent name can appear at any tier depending on what the player rolls / upgrades. Asset-tree evidence: `Power_Up_Sandman_Mazor_Upgrade_Talent_To_Legendary.entity.ot.EntitySettingsResource.gen` (an in-game effect that upgrades a talent to Legendary), `HaveLegendaryTalentsInASingleRun.Achievementdef.ot` (an achievement for collecting legendary talents).

**Implications for talent record encoding:** the save's talent-slot bytes likely store BOTH the talent identity AND the tier. Possible encodings:

- `[talent_id: u32][tier: u8 or u32]` — two fields per slot
- `[combined_id: u32]` — talent×tier baked into one ID (so `Quadrotonic Common` and `Quadrotonic Legendary` would be different combined IDs)
- Tier as a separate parallel record (talent IDs in one list, tier values in another, indexed in lockstep)

Either way, talent diff signal will encompass tier changes too, not just talent identity changes.

## Empirical observations from hero-swap tests

When swapping Geppetto chapter2 saves to other heroes, the engine populated slot 1 with the new hero's L5 ultimate. The talents observed:

| Hero | Slot 1 talent (after Geppetto-chapter2 swap) | Notes |
|------|---------------------------------------------|-------|
| Carmilla | `Impalement` | One of Carmilla's two ult variants. Game UI labels these "ULTIMATE". |
| Carmilla | `Blood Lash` | Carmilla's other ult variant (offered in L5 pick UI when Impalement was already in slot 1). |
| Aladdin | `Dreamwish` | His ult #1 per UI. |
| Snow_Queen | `Frost Ray` | Her ult #1. |
| Red | `Hunter's Souvenir` | Her ult #1. |

## Geppetto

Per player input: starting talent for the existing `laser-lenses_1` proof was `Dummy Ball`. The run's name reflects the build's *meta* (LaserLenses focus), not the starting talent.

### Skill names from asset tree (assets, not necessarily talent IDs)

The `_Cooking/3D/Characters/Heroes/Geppetto/Animations/` directory contains skill animation files named `Pantin_SKILL_<Name>`. These represent Geppetto's puppet ("Pantin") performing the skill — they're 1:1 mappings between asset name and skill identity in most cases. Distinct skills observed:

- `LaserLenses` (also has `PantinUltimate_SKILL_LaserLenses` variant)
- `Pogo-Hoppers` (with `_SharpNose` cross-variant)
- `RedButton`
- `SharpNose` (also has `PantinUltimate_SKILL_SharpNose` variant)
- `OiledMechanism` (with `_SharpNose` cross-variant)

The presence of `*Ultimate*` variants on `LaserLenses` and `SharpNose` suggests these are at least two of Geppetto's ult-tier talents. The non-Ultimate-variant names (Pogo-Hoppers, RedButton, OiledMechanism, etc.) are likely standard talents or skill modifiers.

### Confirmed talent (from gameplay)

- `Dummy Ball` — starting talent in the `laser-lenses_1` proof.

## Other heroes

Talent / skill names from asset-tree scans, where available:

- **Sun_Wukong**: animation files reference `Wukong_Talent_Dash_Yang` and `Wukong_Talent_Dash_Yin` variants — likely Yin/Yang paths or alternative talent picks for his Dash ability.

For most other heroes, the asset tree didn't surface clearly named talent assets in the cursory scan (talents are inline data inside the herodef.ot binaries, not separate asset files).

## Gaps

This doc lacks:

- Full per-hero starting-talent lists (4 per hero, per game design rule)
- L2 / L3 / L4 talent options per hero
- Full L5 ult variants (we know Carmilla has Impalement + Blood Lash, but only one of the others' ults each)
- Internal talent IDs (the bytes the save uses to reference a talent — pending the talent-record discovery work)

## Sources

- `rw/ref/tree-deciphered.txt` — asset tree.
- Hero-swap experiments documented in `rw/key-findings/hero-swaps.md` — Carmilla / Aladdin / Snow_Queen / Red ult observations.
- Player-supplied gameplay info (Dummy Ball, run-id naming convention).
- [Ravenswatch wiki — Heroes](https://ravenswatch.fandom.com/wiki/Heroes) — canonical reference (not yet imported).
