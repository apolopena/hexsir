# Terminology

Standardized terms for talents, items, seeds, and indexing. Read before writing docs, code, or commit messages that touch these domains. Splits per-domain may come later; for now everything lives here.

## Indexing

Anything user-facing (CLI args, docs, slot numbers mirroring the UI) is **1-based**. Everything else (byte offsets, list/array indices, loop counters) is **0-based**. Translate at the access boundary, not in the public API.

The slot/controller numbers in `tools/rerw-src/lib/talent_edit.py` and `lib/item_edit.py` take **1-based** values and do `(n - 1)` internally before indexing bytes — that is the canonical pattern.

## Talents

- **HUD slot** — the 10 player-facing slots (1–10 user, 0–9 in raw byte/array math). Slot 5 is the ult slot (no rarity).
- **Talent pool** — the 28 skill controllers per hero (1–28 user, 0–27 code). Defined in the hero's `herodef.ot`. The full set of talents the hero could theoretically have. The picker draws from this pool to fill HUD slots.
- **Skill controller** — one entry in the talent pool. Has a stable 16-byte GUID. Each is one tag=0x10 record in a save.
- **Picker pool** — the runtime input array passed to a picker function at fire time. Filtered down from the talent pool by class, prior picks, eligibility. **Not** the same as "talent pool" — see Cross-cutting collisions below.
- **Rarity** — Common / Rare / Epic / Legendary. The CLI accepts only those four lowercase strings; anything else is rejected. Stored on disk as a u32 / u8 with values 0..3 (and 4 for the ult-marker / uninitialized sentinel). Internal byte fields are named "rarity"; do not use "tier" anywhere in CLI args, code, or docs.

## Items

- **Item / "magical object" / "MO"** — same thing. Player-facing name is "magical object." Code uses "MO" or "item" interchangeably.
- **Item slot** — position in the run's records array (1-indexed user, 0-indexed code). Order matches counter sequence.
- **Runtime GUID vs asset GUID** — 16-byte IDs. Runtime GUID lives in tag=0x1a run records; asset GUID lives in tag=0x05 catalog records. Both originate from the same entity-settings file but are not interchangeable.
- **Item catalog** — the static set of all 114 possible items, stored in the save as tag=0x05 records. Identical across all saves. It plays the same role in the items domain that the talent pool plays in the talents domain — but the term is different, deliberately. **Don't call it the "item pool."** The runtime records-array (tag=0x1a) is "what the player has now"; the catalog is "what exists in the world."

## Seeds and RNG

- **The seed** — the single u32 at TLS+0xff3c. **One per session.** Every gameplay roll reads and advances this same slot.
- **PCG step** — one advance of the seed. Each step produces a new value AND mutates the seed. Inlined at 30+ sites in the binary.
- **Stream** — the sequence of values produced by repeated stepping. Forcing the seed sets the starting point of a stream.
- **Master chapter seed** — the value shown on-screen during a run. Different concept from the gameplay seed. Persistence location is **unverified** (open dig). Feeds entity-spawn paths via the leaf PCG function `pcg_step_thread_local_seed` (image+0x4ffb70). NOT the gameplay seed at TLS+0xff3c.
- **Forced Seed UInt** — the INI file setting. Feeds the master-seed path only. Does **not** make gameplay rolls deterministic — gameplay rolls bypass it.
- **Roll** — a consumer-side draw against the seed (e.g., "the picker rolls for tier"). One roll = one or more PCG steps depending on the consumer.

## Cross-cutting collisions

- **"Pool"** is overloaded. Always disambiguate:
  - **Talent pool** = the 28 skill controllers per hero (static, defined in herodef).
  - **Picker pool** = the runtime input array a picker is choosing from (filtered subset, varies per fire).
  - The **item catalog** is the items-domain equivalent role — but it is **not** called a pool. Keep "pool" in the talents domain only.
- **"Seed"** is overloaded. Always disambiguate:
  - **The seed** (gameplay) = TLS+0xff3c, drives picker/chest/shop rolls.
  - **Master chapter seed** = on-screen value, drives entity spawns.
  - **Forced Seed UInt** = INI setting, feeds master-seed path only.
- **"Slot"** is fine across domains (HUD slot, tier array slot, item slot) as long as the indexing base is clear from context. When in doubt, say "1-based" or "0-based" explicitly.

## Save artifact types

Three artifact types live under `rw/saves/`. Definitions, path conventions, and promotion paths are in `rw/docs/workflow/save-editing.md`. Quick summary:

- **Lab** — gitignored work-in-progress save edit.
- **Golden** — verified save edit whose chain does NOT use `rerw mint savefile`.
- **Mint** — verified save edit whose chain DOES use `rerw mint savefile` (zeroed per-run state, chapter-1 output). Lives under `saves/mints/`, organized by source-chapter, requires an `info.md` next to `Profile_1.ob`.

## References

- `rw/docs/workflow/save-editing.md` — save artifact types, path conventions, promotion paths, CLI promotion rules.
- `rw/findings/talent-records.md` — talent record format, picks block, rarity records.
- `rw/findings/magical-objects.md` — item record format, catalog, edit primitives.
- `rw/findings/rng-behavior.md` — single-seed PCG model, forcing strategy.
- `rw/findings/random-seed-system.md` — open dig: master chapter seed location.
