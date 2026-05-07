[← Back to docs](README.md)

# Game rules

In-game mechanics rules for Ravenswatch — the gameplay-level model that constrains how live tests, mods, and modeling work can be designed. Distinct from `rw/findings/` (RE/engineering observations about specific symbols, structs, and offsets) and from `rw/docs/workflow/` (process: how RE work happens here).

This doc exists because agents repeatedly designed live tests that depended on gameplay assumptions which the game does not guarantee. The rules below are short, hard-learned, and load-bearing for test design.

## Cauldrons and waves

### Mechanism

Cauldrons in a chapter trigger an enemy wave when activated. The mechanism, as currently understood:

- **Main enemies phase in at trigger time.** The cauldron does not "wake" pre-placed sleeping enemies. When a cauldron is activated, the main enemies of the wave are constructed at trigger time via the universal `oCEntity::ctor` factory chain (RVA `0x6c96f0`). They appear, they are not revealed.
- **Some main enemies summon their own minions during the fight.** Spider Nightmare main enemies summon eggs. Cultist Summoners summon tentacles. Mid-fight minion-summons go through the same `oCEntity::ctor` factory chain. The summon mechanism appears to be tied to specific main-enemy templates and is the *mechanism of interest* for live-mod work — it is not yet known whether the summon primitive can be invoked separately from its parent enemy.
- **Effects, projectiles, and puddles** (egg projectiles, line attacks, poison puddles) are also runtime-constructed via the same path. Always.

The full RE-side detail — the factory chain, the class metadata table, the `EnemyController` component identification — lives in `rw/findings/enemy-spawn-architecture.md`. This entry is the gameplay-level view.

### Cauldron content is randomized

Cauldron content is randomized per chapter run. The wave that appears when the cauldron is activated is drawn from a pool of cauldron variants (cultist/summoner, spider nightmare, ghoul, pig, …). The pool size is unknown; the same family rarely repeats back-to-back across runs.

**Not knowable in advance:**
- Which cauldron family will appear in any given chapter.
- How many distinct cauldron families exist.
- Whether a specific family will appear within N runs.

### Test-design constraint

Because cauldron content is randomized and the family pool is large and unmeasured: **never design a live test that depends on a specific enemy template appearing.** Tests must be type-agnostic — defined over "whatever the cauldron wakes" — or run opportunistically when the user reports the family currently in front of them.

Concrete bad pattern (do not do this):
> "Run the cultist cauldron, capture the tentacle template, ..."

Concrete good pattern:
> "Activate any cauldron. Filter captured entities by the `EnemyController` component (per `enemy-spawn-architecture.md`). Operate on the filtered set without assuming which templates are present."

### Future digs (gameplay-level)

The "redirect enemy AI to fight each other" question is a gameplay-level tangent that emerged from the spawn-architecture work. Recorded in `rw/findings/enemy-ai.md` (RE-side) and `rw/docs/wishlist.md` (technical work items). Mentioned here so the gameplay framing is discoverable from the rules side too.

## Saves

Saves are only generated at chapter-boss kills. There is no autosave, quicksave, save-on-quit, or save-on-death. This is a project-wide rule with broad implications for save-edit experiments — full narrative and implications live in `CLAUDE.md` and `rw/docs/workflow/save-editing.md` §Gotchas. Recorded here as a pointer because it is a gameplay-level rule.
