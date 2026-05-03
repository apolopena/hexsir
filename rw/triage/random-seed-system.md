# Random seed system — locate and edit

## What this doc is — for non-experts

**Plain-English summary.** Ravenswatch decides "random" things (which talents appear at level-up, what rarity each one is, what's in chests, what's in shops) by drawing from a single internal random number. This doc tracks our progress at locating, reading, and overriding that number so we can replay or engineer specific outcomes.

**Status as of 2026-05-02: PARTIALLY RESOLVED.**

- ✅ **Talent picker (selection + rarity rolls)** — locked. The single-seed model is verified. Frida hook on `SkillController_roll_proposed_skills` (`image+0x39c300`) writes the seed at function entry; combined with nulling `param_3` (R8) the picker proposes the same talents at the same rarities every reroll. See `rw/key-findings/rng-behavior.md`.
- ✅ **Persistent rarity** — `rerw write savefile all-talent-rarities <rarity>` locks the picker's rarity stamp by writing both the per-controller tier bytes and the per-slot u32 array.
- ⏸ **Chest / Sandman shop / item picker** — same single-seed model expected, separate function entry not yet hooked. Implementation would mirror the talent-picker harness.
- ⏸ **Master chapter seed** (the seed displayed in-game on screen) — not yet located in the save format. Still on the backlog.

**Rules of thumb when working with this:**

1. **Don't try to hook the leaf PCG function.** Per-event RNG inlines the PCG step; the leaf is only used by the master chapter seed and some entity-spawn paths.
2. **Frida is the working approach.** Save-edit alone can't lock per-roll outcomes (the seed isn't persisted in the save in any encoding we've found). Save-edit CAN lock rarity via the dual-storage mechanism described in `rng-behavior.md`.
3. **Master seed in the save:** unverified. Earlier session searched for the displayed in-game seed value as raw bytes and didn't find it; either persistence happens differently or the seed isn't fully save-resident.

---

## Detailed status

### Resolved 2026-05-02 — talent-picker RNG forcing

The talent picker uses an inline PCG against TLS+`0xff3c`. Forcing the seed at function entry (Frida hook) gives full deterministic control over both selection and rarity roll. See:

- `rw/key-findings/rng-behavior.md` — full mechanism
- `tools/frida/rw_lab.js` — working harness with `force(seed)` / `forceFresh(seed)` / `clearHeldNext(slotIdx)` REPL commands
- `rw/key-findings/talent-records.md` — the dual-storage tier model
- Renamed Ghidra functions: `SkillController_roll_proposed_skills`, `SkillController_state_dispatch`, `SkillController_repropose_skills`, `talent_roll_tier_weighted`, `talent_stamp_tier`, `uniform_float_in_range_pcg`, `SkillController_sync_slot_tiers_from_talents`, `SkillController_init_or_load_persistent`

### Open — master chapter seed location

The game UI displays a seed number on screen during chapter play. Capture exact format on next play session — is it hex? decimal? how many digits? Then:

- Ghidra string-search the rendered seed format (`%08X`, `Seed:`, `Run Seed`, etc.) → caller is the renderer → walk back to source field
- Live-memory search for the displayed integer once WinDbg/trainer is viable (currently deferred — WinDbg crashes on save event per user)
- Save-file search: byte-search the displayed value across known proof saves; if it appears, the seed is persisted

### Open — chest, Sandman shop, item picker hooks

Same approach as talent picker. Find each picker's entry function via xref of the relevant named-event hash, hook it, write TLS+`0xff3c`. Unstarted but mechanically straightforward given the talent-picker template.

### Open — slot 6–10 picks-block storage

Picks block storage layout for >5-pick saves (chapter-3, epilogue) is genuinely different from the chapter-2 5-pick block — no `count=N` sentinel exists in the save for higher pick counts. Blocks `rerw write savefile talent --slot N --key K` from working on those saves. Solving requires runtime tracing of the save deserializer or a more thorough byte-diff. Documented as engineering debt.

## Open questions

- Is the master seed per-run only, or persisted across the save? (If only per-run, a save edit can't set it — we'd need live-memory write.)
- Is there one master seed per chapter, or one master seed that drives a deterministic per-chapter sub-seed?
- Does the master seed change on chapter rollback (`rerw write savefile chapter`), or is it preserved?

## Cross-references

- `rw/key-findings/rng-behavior.md` — single-seed model, dual-storage tier, Frida-forcing strategy
- `rw/key-findings/talent-records.md` — talent record byte layouts, slot.tier u32 array
- `tools/frida/rw_lab.js` — talent-picker forcing harness
- `rw/docs/save-edit-capabilities.md` — `all-talent-rarities` CLI capability
