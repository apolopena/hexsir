[← Back to findings](README.md)

# Random seed system — locate and edit
**Status:** in-progress


## Sources

- pre-policy — written before the Sources header was mandatory.

## What this doc is — for non-experts

**Plain-English summary.** Ravenswatch decides "random" things (which talents appear at level-up, what rarity each one is, what's in chests, what's in shops) by drawing from a single internal random number. This doc tracks our progress at locating, reading, and overriding that number so we can replay or engineer specific outcomes.

**Status as of 2026-05-08: MOSTLY RESOLVED.**

- ✅ **Talent picker (selection + rarity rolls)** — locked. The single-seed model is verified. Frida hook on `SkillController_roll_proposed_skills` (`image+0x39c300`) writes the seed at function entry; combined with nulling `param_3` (R8) the picker proposes the same talents at the same rarities every reroll. See `rw/findings/rng-behavior.md`.
- ✅ **Persistent rarity** — `rerw write savefile all-talent-rarities <rarity>` locks the picker's rarity stamp by writing both the per-controller tier bytes and the per-slot u32 array.
- ✅ **Master chapter seed (in-memory) — LOCKED 2026-05-08.** The on-screen seed is distributed at chapter load by `apply_session_seed_to_scene_contexts` (RVA `0x26af00`) to four per-context subseed slots. Live-verified end-to-end. Frida force via `tools/frida/mods/powers/Seed.js` controls camps, camp placement, reward-slot distribution, and other map-scoped procedural decisions. Does NOT control talent/item/chest/shop picks (those use TLS+0xff3c, separate path). See `rw/findings/seed-master-distribution.md` for the full architecture.
- ⏸ **Chest / Sandman shop / item picker** — same single-seed model expected, separate function entry not yet hooked. Implementation would mirror the talent-picker harness.
- ⏸ **Master chapter seed (in save)** — whether the master persists in `Profile_1.ob` is still open. Earlier session searched for the displayed seed value as raw bytes and didn't find it. Live-memory force makes save persistence less urgent (override at chapter load), but identifying the on-disk byte if any would let `rerw` set seeds.

**Rules of thumb when working with this:**

1. **Don't try to hook the leaf PCG function.** Per-event RNG inlines the PCG step; the leaf is only used by the master chapter seed and some entity-spawn paths.
2. **Frida is the working approach.** Save-edit alone can't lock per-roll outcomes (the seed isn't persisted in the save in any encoding we've found). Save-edit CAN lock rarity via the dual-storage mechanism described in `rng-behavior.md`.
3. **Master seed in the save:** unverified. Earlier session searched for the displayed in-game seed value as raw bytes and didn't find it; either persistence happens differently or the seed isn't fully save-resident.

---

## Detailed status

### Resolved 2026-05-02 — talent-picker RNG forcing

The talent picker uses an inline PCG against TLS+`0xff3c`. Forcing the seed at function entry (Frida hook) gives full deterministic control over both selection and rarity roll. See:

- `rw/findings/rng-behavior.md` — full mechanism
- `tools/frida/rw_lab.js` — working harness with `force(seed)` / `forceFresh(seed)` / `clearHeldNext(slotIdx)` REPL commands
- `rw/findings/talent-records.md` — the dual-storage tier model
- Renamed Ghidra functions: `SkillController_roll_proposed_skills`, `SkillController_state_dispatch`, `SkillController_repropose_skills`, `talent_roll_tier_weighted`, `talent_stamp_tier`, `uniform_float_in_range_pcg`, `SkillController_sync_slot_tiers_from_talents`, `SkillController_init_or_load_persistent`

### Resolved 2026-05-08 — master chapter seed (in-memory) located + Frida-forceable

The on-screen master seed is distributed at chapter load by `apply_session_seed_to_scene_contexts` (RVA `0x26af00`). It writes the master to four per-context subseed slots (`MapSceneContext+0x80`, `EntitySceneContext+0x3b8`, `*DAT_141446a98`, `*DAT_141446a78`); each slot has a running stream at `+0x04` initialized to `PCG_step(master)` and stepped per roll.

Live-verified by reading the on-screen seed (`1720768478` / `0x6690D7DE`) and observing it intact at both `MapSceneContext+0x80` and `EntitySceneContext+0x3b8`.

**Forcing primitive:** `tools/frida/mods/powers/Seed.js`. Hook on `apply_session_seed_to_scene_contexts` entry; overwrites `args[1] + 0x1c` (the master) with armed value. One write controls all four subseeds → deterministic camps, camp placement, reward-slot distribution. Does NOT cover talent/item/chest/shop picks (those use TLS+0xff3c).

Full writeup: `rw/findings/seed-master-distribution.md`.

### Open — master chapter seed in save format

Save-file persistence of the master is still unverified. Earlier session searched the displayed seed value as raw bytes across proof saves and didn't find it. Possibilities: per-run-only (not persisted), or stored in a non-trivial encoding. Live-memory force via `Seed.js` makes this less urgent; identifying the save byte would let `rerw` set seeds offline.

### Open — chest, Sandman shop, item picker hooks

Same approach as talent picker. Find each picker's entry function via xref of the relevant named-event hash, hook it, write TLS+`0xff3c`. Unstarted but mechanically straightforward given the talent-picker template.

### Open — slot 6–10 picks-block storage

Picks block storage layout for >5-pick saves (chapter-3, epilogue) is genuinely different from the chapter-2 5-pick block — no `count=N` sentinel exists in the save for higher pick counts. Blocks `rerw write savefile talent --slot N --key K` from working on those saves. Solving requires runtime tracing of the save deserializer or a more thorough byte-diff. Documented as engineering debt.

## Open questions

- Is the master seed per-run only, or persisted across the save? Open — see "Open — master chapter seed in save format" above.
- ~~Is there one master seed per chapter, or one master seed that drives a deterministic per-chapter sub-seed?~~ **Resolved 2026-05-08:** master drives multiple per-context subseeds (camp/map/two globals). Each subsystem advances its own stream from the same seed. See `seed-master-distribution.md`.
- Does the master seed change on chapter rollback (`rerw write savefile chapter`), or is it preserved? Open.

## Cross-references

- `rw/findings/seed-master-distribution.md` — master → 4 subseed slot architecture, Frida force via `Seed.js`
- `rw/findings/rng-behavior.md` — TLS+0xff3c per-event RNG (separate path; not covered by master force)
- `rw/findings/talent-records.md` — talent record byte layouts, slot.tier u32 array
- `tools/frida/mods/powers/Seed.js` — master-seed forcing power
- `tools/frida/rw_lab.js` — talent-picker forcing harness
- `rw/docs/workflow/save-editing.md` — `all-talent-rarities` CLI capability
