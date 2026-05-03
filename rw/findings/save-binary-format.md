[← Back to findings](README.md)

# Save: binary format and edit primitives

**Status:** confirmed
**Status notes:** active — canonical state-of-knowledge for Ravensmith save-file editing.
**Created:** 2026-04-27

Save-file editing is the active track. Live-memory work is **tabled, not closed** — see "Live memory: tabled" below and the archived findings under `rw/findings/` for the technical record. Read-only live monitoring may return as a future track if per-session ASLR re-discovery (`rs discover` / structural anchoring) is built; live trainer editing is not on the near roadmap.

## Save file structure

Verified across the four Geppetto proof saves (`rw/saves/proofs/geppetto/{clean,chapter2,chapter3,epilogue}/.../Profile_1.ob`):

| Region | Range | Contents |
|--------|-------|----------|
| Header | `0x00 – 0x0B` | Format header (12 bytes; not yet decoded) |
| CRC32 of body | `0x0C – 0x0F` | 4 bytes int32 LE; computed as `zlib.crc32(data[16:])` |
| Body — type registry | `0x10 – 0x700` | Schema definitions (undecoded; likely defines record-type → key/value layout) |
| Body — profile + run records | `0x700 – ~0x10000` | Stored fields keyed by GUID |
| String index | `0x10000 – 0x12000` | Indexed string table (undecoded) |

File-size deltas confirm the run-state region: `clean` is 69,459 bytes; chapter-2 / chapter-3 / epilogue saves are 74,239 / 76,465 / 78,460 bytes. The ~5 KB delta over `clean` is the run-specific record set.

CRC32 is verified by `hexsir checksum verify`. Editing any byte after offset `0x10` invalidates the stored CRC; the body-CRC must be recomputed and rewritten at `0x0C` for the save to load. All editing tools handle this automatically.

## Record format

Fields in the body region are keyed by **15-byte GUIDs**, with the value following immediately after the GUID:

```
+0    GUID (15 bytes)
+15   value
```

Some GUIDs contain a visible ASCII prefix (the tail of the underlying asset's filename); others are entirely opaque. Examples:

- `66 61 75 6c 74 64 65 66 2e 6f 74  26 ba 45 19` — bytes 0–10 are ASCII `faultdef.ot` (the tail of `All_Chapters.gamemodedefaultdef.ot.GameModeDefaultDefinition.gen` deciphered via `rerw decipher`); byte 11 is `&` (also ASCII, possibly a separator); bytes 12–14 are binary `ba 45 19`.
- `b5 31 7e fe 6f 4a 95 73 73 25 67 57 93 e6 00` — no contiguous ASCII; entirely opaque.

The segmentation of the non-ASCII portion (separator vs hash vs interned ID) is not yet determined — see "Open questions" and `rw/findings/save-guid-hash-tail.md`.

**GUID stability:** the 15-byte GUID values are stable across all saves observed and across saves of differing run lengths (chapter 2, chapter 3, epilogue). They are compile-time-baked references — not per-save random IDs.

**Offset volatility:** save offsets are NOT stable. The body grows with run-state, so a GUID's absolute byte position shifts per-save. **Locate by `data.find(guid)`, not by offset.**

## Verified editable fields

Two fields have been verified end-to-end (edit → load → observe in-game):

| Field | GUID(s) (hex) | Type | Value position | Semantics |
|-------|--------------|------|----------------|-----------|
| `level` | `b5317efe6f4a95737325675793e600` | int32 LE | GUID + 15 | In-run hero level. Game caps display at 15; save accepts higher. Damage scales with level (float overflow between L25–L99). |
| `chapter` | `13fa8e2c314d88babb71a8e3c4df01` (Counter A, opaque) **AND** `6661756c746465662e6f7426ba4519` (Counter B, ASCII tail `faultdef.ot`) | int32 LE | GUID + 15 | "Chapters completed." Edit both GUIDs in lockstep. 0=ch1, 1=ch2, 2=ch3, 3=epilogue. Records absent in clean profiles. |

These two are the entries in `tools/rerw-src/data/save-fields.yaml` that drive `rerw read savefile` / `rerw write savefile`.

**Verification scope and known-unknowns:**

- Verified **for these two fields**, on **Geppetto saves only**, on **the current game build**.
- **Generality is unverified.** Whether arbitrary other GUIDs in the save body follow the same `GUID + 15 → int32 LE` shape has not been tested. Other shapes (different value types, length-prefixed records, packed structs) are plausible.
- **Cross-hero stability is unverified.** All proof saves are Geppetto. The `chapter` GUIDs (especially Counter B referencing the `All_Chapters` GameMode) are likely hero-independent; field-specific GUIDs (e.g., per-character base-stats, per-character progression markers) may not be. The hero-identity field (planned next experiment) will be the first cross-hero data point.
- **Cross-build stability is unverified but likely-fragile.** GUIDs are compile-time-baked; a game patch that touches the underlying asset (recompile, rename, schema change) will likely shift them. The ASCII-tailed GUIDs would shift their hash/index portion at minimum.

### Misidentified — pulled from verified table

| Pulled field | GUID | What we thought | What the test showed |
|------|------|-----------------|----------------------|
| (was) `ProfileDreamShards` | `b43eeb58d162fa41acef99d128f2cb` | Persistent profile-level dream shards (per `mod_save.py`'s `KNOWN_GUIDS` and the original `geppetto-save-analysis.md` triage). | Edited 101 → 9999 in chapter3 save and loaded — in-game profile shards counter was unchanged (still 21). The GUID has stable value 101 across all proof saves but is not the displayed profile shards. Likely a tier cap, milestone threshold, or other persistent constant. Identity now unknown. |

## Edit procedure

1. Read the save into a mutable bytearray.
2. For each target field:
   - Locate each of its GUID(s) via `data.find(guid)`.
   - Write the new value (correctly typed + endian-encoded) at `guid_offset + 15`.
3. Recompute CRC32 of the body (`zlib.crc32(data[16:])`) and write the result as int32 LE at offset `0x0C`.
4. Write the result as `Profile_1.ob` (filename is forced — game expects exactly this; encode variant identity in the directory path per `rw/docs/workflow/save-editing.md`).
5. Install into the active save slot via `rerw swap savefile --source <modified>`.

## Steam Cloud sync (testing constraint)

Ravenswatch saves automatically at chapter completion; there is no in-game save action. Swaps placed with the game off DO load on the next launch. They do NOT persist across restarts. Loading any savegame and quitting updates Steam Cloud at quit; the next launch pulls cloud → local, overwriting whatever was on disk. Each in-game test is single-session: swap → launch → load → observe → quit; the next session needs a fresh swap.

## Run-state preservation observation

Verified end-to-end 2026-04-27 (chapter rewind from chapter-3 save → chapter=0 + level=99): all run-coupled state was preserved on load:

- Hero level
- Equipment / talents
- Currencies (dream shards, stars of fate, keys, raven's feathers)
- Inventory items

**Implication:** the engine's run-state is not gated on the chapter counter; only the scene-load path reads it. Other "key" fields like Level appear similarly isolated. For each new field added to the editable registry, the question "what other state does the engine couple to this?" should be tested empirically — but to date, no such coupling has been observed.

### Level-downgrade test (2026-04-27)

Verified by editing chapter2 source (chapter=1, level=5, mid-run with talents and XP accumulated) to chapter=0 + level=1, loading, then comparing to the unchanged chapter2 source for the same hero ability:

- **Slot loads cleanly** despite the deliberately inconsistent state (level-1 character with talents earned at L2/L3/L4/L5). No engine validation rejection.
- **Level field IS the displayed level.** HUD shows level 1 when the field is 1; level 5 when the field is 5.
- **Talents persist independent of the level field.** Talents earned at higher levels remained equipped on the level-1 character — no auto-removal.
- **XP value carries; XP threshold tracks the level field.** With `level=1`, the HUD shows `2890 / 400` (L1→L2 threshold). With `level=5`, the HUD shows `2890 / 5000` (L5→L6 threshold). XP value is preserved across the level edit; threshold is recomputed from the level.
- **Engine does not auto-promote on load.** Even with XP `2890` well above the L1→L2 threshold of `400`, the character stays at level 1 until an in-run XP gain event triggers a level-up check.
- **Per-ability damage is coupled to the level field.** Hammer Strike tooltip on Geppetto with the same talent loadout: `23 damage at level=1`, `34 damage at level=5`. +11 damage across 4 levels. The exact scaling formula is underdetermined from two points (linear `+2.75/level` and multiplicative `~10.3%/level` both fit); pinning it would require sampling L2/L3/L4 with the same talents.

**Inconsistent-state tolerance — generalized observation.** The engine accepts deliberately inconsistent state for at least three field categories now: (1) chapter rewind (chapter-3 run-state on a chapter-1 scene-load), (2) level downgrade (high-level talents on a low-level character), (3) level + chapter combined (the `chapter-rewind-from-ch3-level99` golden). No "must reconcile fields before load" gate has been encountered.

### Hero swap test (2026-04-27)

Verified by editing chapter2 source — byte-replacing the hero record's path string `Heroes\Geppetto.herodef.ot` → `Heroes\Carmilla.herodef.ot` at offset `0x11da2` (8-for-8 character swap, no length-prefix update, no body shift), recomputing CRC32, and loading. Resulting save lives at `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-carmilla/Profile_1.ob`.

- **Slot loads cleanly.** No engine validation rejection.
- **Character identity is fully Carmilla's.** The character that spawned in the hub area is Carmilla (model, white-hair / dark-outfit appearance, the displayed name "Carmilla"). Carmilla's intro quote ("No pleasure on this earth quite matches the ecstasy of the hunt.") plays. The ability bar shows Carmilla's ability set (blood-themed icons), not Geppetto's hammer/lasers.
- **Run state preserved.** Chapter (=2), level (=5), XP, currencies, inventory all carried through unchanged from the Geppetto source.
- **Talent UI state.** Carmilla's talent UI shows some empty slots (the bottom-most empty slot corresponds to the L2 talent pick per the run-start mechanic) and two ult-tier abilities populated: `Impalement` (one slot) and `Blood Lash` (another slot, dual-tagged `ATTACK + ULTIMATE` in its tooltip). Carmilla normally chooses one ult per run from {`Impalement`, `Blood Lash`}, so seeing both is non-canonical. **The mechanism by which Geppetto's saved talent records produce this state on Carmilla has not been investigated** — talent-record bytes in the save are still unparsed.

## Open questions

- **Type registry decoding (`0x00–0x700`).** Undecoded ~1.7 KB segment. Likely defines record-type → key/value-layout mappings. Decoding it would resolve segmentation ambiguity in GUIDs and possibly expose record schemas for currently-unfindable fields.
- **String index (`0x10000–0x12000`).** Undecoded ~8 KB indexed string table. May be referenced by record values (e.g., item-id-as-string-index).
- **Dream shards storage** (both in-run HUD count and the persistent profile counter visible at character select / hub) — neither has been located as a writable int32+GUID record. The previously-suspected `ProfileDreamShards` GUID (`b43eeb58...`) was disproven by live test (see "Misidentified" above). Likely candidates: inventory-array record, computed-from-other-state, or stored under a different schema (possibly the type-registry-defined record types that aren't yet decoded).
- **Stars of Fate** (HUD count) — same. Searched as plain int32 with GUID variations; no consistent storage. Likely an item count in an array.
- **Talents** — RESOLVED. Stored as 5×16-byte skill-controller GUID references in a tag=0x12 talent record, with a per-talent tier byte in tag=0x10 first-occurrence records near the hero. See `talent-records.md` for full structure, GUID encoding, tier mapping, and the verified edit primitives. Both edit primitives are wired into `rerw write savefile` (`--talent-slot`, `--talent-id`, `--tier`).
- **Items / abilities** — no clear storage pattern as GUID+value records. Likely length-prefixed inventory arrays of asset-id refs.
- **Cross-hero GUID stability.** Geppetto-only data. Untested on Aurora, Ratbo, etc.
- **Hero-identity field.** Not yet investigated. Discoverable by the same approach used for chapter and level (mod a candidate GUID's int32 → load → observe). **Planned next experiment.**
- **Hash-tail reversal.** Trailing bytes of save-record GUIDs may encode a hash of the asset path. If reversed, this unlocks programmatic GUID minting from the asset tree → potentially the path to item editing. See `rw/findings/save-guid-hash-tail.md` for the experiment plan.

## Tooling

- **`tools/rerw read savefile --source FILE [--chapter] [--level] [-v]`** — print field values from the YAML registry. Canonical (rerw 0.2.0+).
- **`tools/rerw write savefile --source FILE --dest DIR [--chapter N] [--level N] [-f] [-v]`** — atomic multi-field edit with single CRC recompute. Canonical.
- **`tools/rerw swap savefile --source FILE`** — install a save as the active `Profile_1.ob` in the game's `_Save` directory.
- **`rw/scripts/mod_save.py`** — legacy script. Has `Level` and `ProfileDreamShards` in `KNOWN_GUIDS`; chapter GUIDs not registered there. Functional but superseded by `rerw save` for new work.
- **`tools/hexsir checksum verify` / `hexsir mint`** — CRC32 verification + minting; useful for arbitrary save inspection.
- **`tools/rerw cipher` / `rerw decipher`** — substitution cipher for asset filenames; useful for decoding ASCII portions of GUIDs and for searching `rw/ref/tree-ciphered.txt`.
- **`tools/rerw-src/data/save-fields.yaml`** — the YAML field registry. Adding a new field is a YAML edit + corresponding CLI flag in `commands/read_savefile.py` and `commands/write_savefile.py`.

## Live memory: tabled

The live-memory track was investigated extensively (MAINT-3 through MAINT-6) and tabled when the trainer-edit use case did not pan out. Headline findings:

- **OEngine wraps observable values in `oe::DynamicCpntValueListenerData<T>` listener instances.** Vtables, per-type RVAs, and listener instances for Level / XP / dream shards / etc. were located in the heap by value-progression scanning across L1..L5 in-process snaps.
- **Pinned listener instances are decoupled from the live HUD source-of-truth.** Game-driven trigger events do not propagate into the pins; external writes to pins do not propagate to the live game. Verified bidirectionally for HP, Level, XP threshold, XP current, dream shards, and stars of fate.
- **Mirror cascades exist.** For dream shards specifically, value-progression scanning surfaced 28 mirror addresses that DO track HUD changes. Sentinel writes to all 28 simultaneously did not affect the HUD — the canonical source is upstream of every address surfaced by memory-only techniques.
- **Most stats are computed-on-demand**, reconstructed per frame from `base + Σ(modifiers)`. They have no single live storage to pin. Verified by the failed armor-base hunt.

**Why this is tabled, not closed:**

- **Read-only monitoring is architecturally viable.** The 28 dream-shards mirrors verifiably track HUD changes. Reading them gives real-time values; the obstacle is per-session ASLR re-discovery (every Ravenswatch launch shifts module bases and heap allocations).
- **A `rs discover` workflow** — interactive value-progression discovery + multi-address watch over a Session — would make per-session re-discovery practical (~5–10 min user cost per session). Scoped as a future track in `rw/findings/live-state-mirror-cascade.md` but not built.
- **Trainer-style writing is unattractive.** Writes to mirrors are silently overwritten by the engine (active high-frequency tier) or persisted but ignored by the read path (passive event-mirror tier). Memory-only modding would likely require code-side techniques (function hooking, breakpoints) — a different toolchain.

For the full technical record (template specializations, vtable RVAs, RTTI-walk methodology, listener heap-scan technique, mirror tier classification, pin-identity hypothesis space), see the archived findings: [`rw/findings/oe-dynamic-listener-data.md`](archive/oe-dynamic-listener-data.md).

## Sources

### Active artifacts

- `rw/saves/proofs/geppetto/{clean,chapter2,chapter3,epilogue}/.../Profile_1.ob` — proof saves; the source data for all save-format work.
- `rw/saves/edits/golden/geppetto/chapter1/laser_lenses_1/chapter-rewind-from-ch3/Profile_1.ob` — verified golden mod (chapter rewind end-to-end).
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/{level5,level8,level14,level17,level20}/Profile_1.ob` — verified golden mods (level edits).
- `tools/rerw-src/data/save-fields.yaml` — YAML field registry.
- `tools/rerw-src/lib/save_edit.py`, `tools/rerw-src/lib/save_fields.py` — pure CRC + GUID-locate primitives.
- `rw/scripts/mod_save.py` — legacy edit script.

### Triages (in-flight)

- `rw/findings/geppetto-save-analysis.md` — original GUID survey + the unfound-stats list (in-run dream shards, stars of fate, items, abilities). Some entries are now superseded by this key finding; the unfound stats remain open.
- `rw/findings/save-guid-hash-tail.md` — hash-tail reversal hypothesis + experiment plan.
- `rw/findings/level-runtime-address.md` — historical: live-memory pin of Level. Superseded for the trainer-edit use case but useful as method record.
- `rw/findings/pin-identity-uncertain.md` — hypothesis space for what pinned listeners actually are.
- `rw/findings/live-state-mirror-cascade.md` — mirror tier classification + the `rs discover` proposal.

### Archive

- `rw/findings/oe-dynamic-listener-data.md` — full live-memory work record.
- `rw/findings/save-chapter-counter.md` — original chapter-counter writeup.

### Tools

- `tools/rerw` — Ravensmith RE tool (cipher/decipher, swap, read/write savefile).
- `tools/hexsir` — CRC32 + binary checksum probe.
- `rw/ref/tree-ciphered.txt` — asset tree (Rosetta stone for asset-filename ↔ deciphered-name).
