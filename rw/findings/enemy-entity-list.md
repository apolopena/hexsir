[← Back to findings](README.md)

# Enemy entity list — chapter 1 (Dark Hills)

**Status:** in-progress
**Created:** 2026-05-10

Name-keyed catalog of combat-NPC entities observed during chapter-1 load. Names are the durable lookup key — settings pointers are ASLR-randomized per launch and not stable.

## Sources

- `rw/ref/registry/ctor/ctor-20260508-062825.jsonl` — chapter-1 initial load (30,453 entries)
- `rw/ref/registry/ctor/ctor-20260508-063658.jsonl` — chapter-1 cache load (29,479 entries)

Names extracted from `oCEntity::ctor` records (`name` field = `oCEntitySettings.+0x08` asset-name string). Filtered to combat enemies only; props (`Standard_Table*`, `Destructible_*`, `Tombstone_*`, `Witch_Ashes_Pile`, `Cultist_Blood_Puddle`, etc.), camps (`*_Camp`, `Enemy_Camp_Reward_Spawner_*`), spawner anchors (`[Entity spawner] *`), tile entries (`40x40_*`, `64x64_*`, `6x6_*`, `3x3_*`), VFX (`FX_*`, `ENV_*`, `Decal_*`), and props matching enemy faction names but not the enemies themselves are excluded.

## Enemies

### Boss

- `Boss_Marsh_Ghoul`

### Elite

- `Elite_Lumbering_Treant`
- `Elite_Scarecrow_Enchanted`
- `Elite_Tentacle_Nightmare`
- `Elite_Undead_Hog_Captain`
- `Elite_White_Lady_Masked`

### Standard

- `Standard_Clawed_Treant`
- `Standard_Cultist_Fanatic`
- `Standard_Cultist_Priest`
- `Standard_Root_Treant`
- `Standard_Scarecrow_Day`
- `Standard_Scarecrow_Night`
- `Standard_Undead_Hog_Fisherman`
- `Standard_Undead_Hog_Reaper`
- `Standard_White_Lady_Lantern`
- `Standard_White_Lady_Screaming`

### Named / variant

- `Cultist_Big_Rock_Summoner`
- `Cultist_Small_Rock_Summoner`
- `Cultist_Lantern_Priest`
- `Devouring_Ghoul`
- `Festering_Ghoul`
- `Sling_Ghoul`
- `Spider_Nightmare_Biter`
- `Spider_Nightmare_Elite`
- `Spider_Nightmare_Spitter`
- `Fish_Skeleton`

### Quest / NPC-flagged combat

- `Jack_NPC_Fighting_Ogre` *(cache-load dump only; Jack-quest related — combat status during quest TBD)*

## Notes

- **Asset-name stability.** Names are baked into the cooked `.gen` files, so they're stable across launches and (typically) across game patches unless the dev renames an asset. Settings pointers are heap-allocated and ASLR'd per launch — re-resolve at runtime.
- **Runtime resolution.** From a Frida session, the ctor hook in `tools/frida/mods/spawn_capture.js` (and `Hourglass._spawners`) captures `(name, settings*)` pairs as entities ctor during chapter load. Lookup by name → settings pointer is then a dict-lookup on the captured set.
- **Coverage caveat.** Only entities whose ctors fired during the captured loads appear here. Some chapter-1 enemies may be tied to specific events (waves, side quests) and not load until triggered. A second-pass dump after triggering all chapter-1 events would close gaps.
- **Other chapters.** Storm Island, Avalon, etc. — empty placeholders pending dumps from those chapters.
