[← Back to findings](README.md)

# Save Mint — Status and Known Issues

**Status:** in-progress
**Status notes:** mostly working, follow-ups in progress
**Created:** 2026-04-30
**Renamed:** 2026-05-01 (was `save-mint-unresolved.md`)

## Where the mint stands as of 2026-05-01

The mint pipeline works end-to-end and is shipped as `rerw mint savefile`. The major silencer blocker that prevented saves from writing to disk was identified, fixed, and verified across all three predicted symptoms (silencer modal absence, score-details cleanup after restart, save-and-quit producing a real disk write). See `rw/findings/save-silencer-mechanism.md`.

Held-inventory editing for keys is now a working primitive (verified end-to-end via in-HUD load test of `keys-count-5__from-test3-mint`).

**(2026-05-01 update — BREAKTHROUGH-1, commit `52cff33`):** the dynamic walker has been folded into the production mint at `tools/rerw-src/lib/hc_walker.py`. The chapter-2-shaped-source gate is removed; `rerw mint savefile` runs cleanly on chapter-2, chapter-3, and epilogue sources.

### Known remaining issues (the items below)

1. **Activity-icon carryover** — RESOLVED 2026-05-01 (BREAKTHROUGH-1). Cause was preserved ActivityScore bodies driving chapter-N icon rendering. Fix is to REMOVE the AS records and zero the parent count u32 in CRP body so the deserialize loop runs zero iterations. Score-zero suppression hypothesis was tested and FALSIFIED in-game; AS-removal is the working fix. A second carryover bug was discovered and fixed in the same session — chapter-progression banner at the top of the end-screen showed source-proof's run history; driven by a CRP-body u32 (`3 × chapters_completed_before_death`, located at `first-AS-frame.start - 8`), zeroed by the production mint. Both fixes verified in-game on the chapter-3 mint. New chapter-1 golden: `mint__from-chapter3-laser_lenses_1-proof/`.
2. **Held inventory beyond keys (feathers/wood/bean/dream-shards-spendable)** — partial. RESOLVED: Raven Feathers (CRP+0x15D, u32, this session) and Dream Shards (HC+0x1D, float32, BREAKTHROUGH-2 / 2026-05-01). Still open: wood, bean, other ingredient-type held resources. Confirmed: feathers and shards do NOT live in the HC HeroIngredient vector (which is keys-only in the saves we've inspected); they each live in their own bespoke fields elsewhere in HC/CRP, so the remaining held resources likely follow the same pattern.
3. **HC body+0x25 mirror cascade** — RESOLVED IN UNDERSTANDING but no behavioral fix needed: this field is "Raven Feathers consumed" (per-run stat), confirmed by edit test. The "stuck at 4" earlier observation was confounded by the silencer; with silencer fixed, the field writes work normally and the new `rerw mint savefile` zeros it as part of the recipe.
4. **Score-Details achievement records source** — RESOLVED: was the ActivityScore × 6 records all along. The original "we already touched them" conclusion was wrong. See item 1.

## Sources

- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — input proof for the mint chain (chapter-2 boss-kill, original)
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/Profile_1.ob` — v4 zeroed golden (intermediate)
- `rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/Profile_1.ob` — minted chapter-1 starting golden (CRC `0xC14F2CBB`)
- `rw/saves/edits/golden/geppetto/chapter2/2for1-thru-with-inventory/Profile_1.ob` — chapter-2 follow-on save after playing the chapter-1 minted golden through to chapter 2 boss kill
- `tools/rerw-src/lib/cooked.py` — the decoder/encoder used for byte-diff analysis
- Ghidra session: `oCDtEntityCpntHeroControllerPersistentData_Serialize` (vtable[3] @ 0x140380490) — wire-format reference for HC body
- Cross-reference: `rw/findings/live-state-mirror-cascade.md` — directly relevant for #3 below
- Cross-reference: `rw/findings/save-edit-pipeline.md` — full pipeline doc, includes confirmed stat-source mappings

## Context

The mint recipe (zero per-run state of a chapter-2 proof, roll chapter back to 1 via `rerw --chapter 0`) works end-to-end and was promoted as a golden + downstream play-through golden. **Three issues remain unresolved.** Each is documented below as a separate triage item; the hypothesis list and discriminating tests are intended to guide the next dig.

The empirical proof of the round-trip (mint → load → play 2 chapters → save → restart → state intact) is captured in the two goldens' `info.md` files. None of the unresolved items below invalidate that POC; they're recipe gaps and observability mysteries.

---

## (1) Held-inventory byte location is unmapped — keys, feathers, bean

### The question

Where in the save bytes does the engine persist held-inventory counts (Nightmare Keys, Raven Feathers, Bean ingredient, etc.)?

### Evidence — persistence is real

Verified by user test on the chapter-2 follow-on save (`2for1-thru-with-inventory/Profile_1.ob`):
- Collected 2 keys before chapter 2 boss
- Save event fired at boss kill (game-engine save dialog accepted)
- Quit game → restarted → loaded the save → entered world with 2 keys still held
- Quit again → restarted → entered with 2 keys still held

The keys persist across save → restart cycles. The save file carries the state.

### Evidence — but our diffs didn't find them

Records inspected for byte-level deltas between the chapter-2 proof (no held inventory) and the play-through golden (2 keys + 1 bean + 2 feathers + extra dream shards held):

- **HeroController body**: only our v4 edits differ (damage region zero, +0x25/0x29/0x2d probe edits, +0x35d zero). No unmapped delta.
- **HeroIngredient vector at HC body+0x21**: count = 0 in both proof AND golden. The vector that *appears* to be for ingredients is empty in every save we've looked at.
- **CounterPersistentData × 3**: identical between proof and golden (values 3/2/7 unchanged).
- **HeroMOPersistentData × 21**: identical between proof and golden.
- **HeroProfileData × 12**: identical between proof and golden.
- **HeroScoreData**: fully zeroed in golden (our v4 zeroing took); play-through did not repopulate it.
- **CurrentRunProfileData parent body** (region before first ActivityScore frame): identical between proof and golden — the `1, 0, 1, 0, 7, 3, 6` u32 sequence is constant.

### Hypotheses

- **H1**: held inventory lives in a record we know by name but didn't dump fully (e.g., the `oCEntityPersistentDataContainer × 2` instances, or `CurrentRunProfileData` body regions after the children frames).
- **H2**: held inventory is derived from chapter-achievement records (since key acquisition is a chapter achievement per user). Achievement-record source is also unmapped — see (2).
- **H3**: held inventory is in a record outside `Profile_1.ob` (separate file, Steam profile, registry, etc.). Less likely given user confirmed Steam Cloud is off.

### Ruled out

- HeroController body (exhaustively diffed)
- ~~HeroIngredient vector at HC+0x21 (empty in all saves checked)~~ ← **RULING OVERTURNED 2026-05-01**: see status update below
- CounterPersistentData × 3 (unchanged across proof/golden)
- HeroMOPersistentData × 21 (unchanged)
- HeroProfileData × 12 (unchanged)
- HeroScoreData (fully zeroed in golden)

### Status update 2026-05-01 — KEYS RESOLVED, OTHER INGREDIENTS STILL OPEN

The test-3 mint-derived save at `rw/saves/mints/geppetto/chapter2/test3-silencer-fix-verified/Profile_1.ob` (75977 bytes, hash `71f093f11484eae1...`) was the breakthrough — first save we've ever observed with a non-empty HeroIngredient vector. Schema decoded and edit verified end-to-end:

- HC body+0x21: u32 `count` = number of distinct ingredient TYPES held
- Each record: framed `oSDtHeroIngredient` (MARK_START + class_idx + body + MARK_END)
- Per-record body: `u32 type_id + u32 count`
- For 2 keys: 1 record with type_id `0xc4cb986e`, count=2
- New class `oSDtHeroIngredient` enters the registry only when this vector is non-empty (40 classes vs 39 in zero-ingredient saves)

**Edit verification (2026-05-01):** lab `rw/saves/edits/lab/keys-count-5/Profile_1.ob` modified the count subfield from 2 → 5, loaded in-game, HUD displayed **5 keys**. End-to-end ingredient editing for the held vector is working. **Held-inventory editing for KEYS specifically is now a working primitive.**

### Open follow-ups

- **Status update 2026-05-01 (BREAKTHROUGH-2):** held Dream Shards mapped at HC body+0x1D as float32 (front-anchored across all chapters). NOT in the HeroIngredient vec — lives in the static prefix of the HC body. HUD reads it verbatim; verified via `held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof` golden. Edit via `rerw write savefile shards <number>`. See `rw/findings/held-dream-shards.md`.
- **Status update earlier this session:** held Raven Feathers mapped at CRP body+0x15D (u32). Also NOT in the HeroIngredient vec. Edit via `rerw write savefile feathers <number>`.
- **Calibrate the type_id hash function.** Type_id `0xc4cb986e` = Nightmare Key is anchored; brute-force candidates against this value with various hash algorithms (standard CRC32, the table-CRC32 with init=0xff documented in `rw/findings/save-subsystem.md`, FNV variants, etc.) to identify the input string format. Without the hash, we can SET counts of existing types but not ADD new types from scratch (relevant for adding a Keys record on saves that don't already have one).
- **Map held wood / bean / other ingredient storage.** Three held inventory currencies are now mapped (keys, feathers, shards) and they live in three DIFFERENT records — keys in the HeroIngredient vec at HC+0x21, feathers in CRP+0x15D, shards in HC+0x1D. The remaining held resources (wood, bean, any other ingredient types in the player's HUD) likely follow the same pattern: each in its own bespoke field, not necessarily co-located. Approach: take a save with known non-zero counts of each (the test3-mint or a fresh-play save) and a clean-zero save, brute-diff for each known integer/float value across HC/CRP/HSD bodies and any other singleton or growing record.

---

## (2) Chapter-achievement records source unknown — drives the compounding-blanks bug

### The question

Which save record stores chapter achievements (the icons displayed on statistics page 2 / Score Details)?

### Evidence

The score-details page shows colorful achievement icons earned during the run (e.g., bought a Raven Feather at a heroes' altar, conquered a cauldron, killed a Nightmare Tumor, completed a side activity). When a save is minted from a chapter-2 proof and played through chapter 1 → chapter 2, the page shows:

- Active chapter-1 achievement icons in the leftmost positions
- A run of empty grey diamond placeholder slots in the middle
- Active chapter-2 achievement icons appended after the blanks

The middle blanks are inherited records from the chapter-2 proof that the v4 mint did not clear. They occupy positions but cannot render in chapter-1 context. New achievements are added on top, not replacing them.

See screenshot: `rw/saves/edits/golden/geppetto/chapter2/2for1-thru-with-inventory/score-details-blanks-bug.png`

### Hypotheses

- **H1 (PARTIALLY CONFIRMED 2026-05-01, ADDITIONAL OPEN ITEM)**: ActivityScore × 6 truncation was the root cause of the SAVE SILENCER (Error code 4) — fully verified across three tests (silencer fix doc has detail). Truncation also produced SOME of the score-details display issues, but **the activity-icon carryover bug is NOT fully resolved by the truncation fix**. CONFIRMED 2026-05-01 late session that activity records appear in the score-details panel on BOTH the chapter-2 mint output (`mint-feathers-consumed-zero__from-laser-lenses_1-proof__chapter1-stars7/`) AND the chapter-3 dynamic mint output (`dynamic-mint__from-chapter3-laser_lenses_1-proof/`). The mint preserves ActivityScore bodies (necessary to avoid silencer); each preserved body's strings (icon path + text + localization) drive icon rendering regardless of whether the player completed the activity in this run. The score-value-gates-display hypothesis (lab `dynamic-mint-as-scores-zero__from-chapter3...`) was built but not yet tested in-game. Symptoms remaining in the test3 mint-derived save's defeat screen (see screenshots `Screenshot 2026-05-01 004549.png`, `Screenshot 2026-05-01 004616.png`, `Screenshot 2026-05-01 004650.png` in `rw/saves/mints/geppetto/chapter2/test3-silencer-fix-verified/`):
  - The score-details row still shows extra blank/empty slots being appended after the active icon, even though the fix cleared the previously-stuck blanks. User observation: "they're added, they're cleared out, but they're still being appended."
  - A "local sentence text not loaded+5%" localization-key failure appears at the bottom of the defeat screen — possibly an unresolved string-lookup against text the engine expects but our restored bodies don't satisfy in the right form for chapter-1 → chapter-2 context.
  - The displayed Score (442) may itself be incorrect — flagged for verification.
  - Net interpretation: the silencer cause is identified and fixed (ActivityScore truncation). The score-details display has at least one ADDITIONAL distinct cause beyond truncation, still unmapped. H2/H3 below remain plausible candidates for the residual display issue.
- **H2**: a record we haven't named yet. The class registry has 39 classes, most accounted for; check the unmapped ones. (Less likely now given H1, but not ruled out — H1 only fully holds if both symptoms resolve together.)
- **H3**: the records are inside `oCEntityPersistentDataContainer × 2` or another container we haven't drilled into. (Same caveat as H2.)

### Ruled out

- HeroMOPersistentData × 21 (unchanged across proof/golden)
- CounterPersistentData × 3 (unchanged)
- HeroProfileData × 12 (unchanged)

### Next dig

- Inspect the two `oCEntityPersistentDataContainer` instances — these are containers and could hold per-run achievement data.
- Find xrefs in Ghidra to event hashes for known achievement-trigger events (e.g., "bought feather at altar", "conquered cauldron", "killed tumor"). Trace what code writes to a record on those events.

---

## (3) "Raven Feathers consumed" stat stuck at 4 — possible mirror cascade

### The question

Why does the score-page row "Number of Raven Feather consumed" keep reading 4 even when we set `HeroController body+0x25` to other values (including 0)?

### Evidence

- We probe-edited `body+0x25` from 1 → 4 in a lab save. Score page on next play showed "Raven Feather consumed: 4" — confirming the field maps to that score-page row.
- Subsequent attempts to clear it back to 0 by writing 0 at `body+0x25` did not take — the score page still showed 4 on next load.
- The byte at `body+0x25` was successfully written to 0 at the file level (verified by re-parsing).
- This pattern matches the mirror-cascade behavior documented in `rw/findings/live-state-mirror-cascade.md`: the on-disk byte is a downstream mirror, the live source-of-truth is in a different memory location that the disk byte doesn't propagate to.

### Hypotheses

- **H1**: `body+0x25` is a downstream mirror in the same way as the pinned addresses in `live-state-mirror-cascade.md` — it's read at runtime to populate the score-page display, but the runtime ALSO holds the value in another in-memory location, and the runtime's "save event" writes from the in-memory location back to disk, overwriting our edit. This would explain why our 0 doesn't take.
- **H2**: the score-page displays a value from a *different* field than the one we identified, and our 1→4 test was coincidence (i.e., body+0x25 happened to be 4 *and* the real source happened to be 4). Less likely given the matching values, but possible if both fields drift together.
- **H3**: there's a runtime cache that persists across save events independent of the file (e.g., a profile-level achievement counter).

### Ruled out / not yet

- (none yet — this triage item needs more probing)

### Next dig

- Set `body+0x25` to a distinctive non-1, non-4 value (e.g., 99) in a controlled lab save. Load and check the score page. If it reads 99 → field is correct, mirror-cascade hypothesis holds. If it reads something else → different field source.
- Diff the running game's memory while playing, looking for u32=4 instances near the HeroController instance. Use `tools/rs-src/` (the rs trainer CLI from the live-state-mirror-cascade investigation) to find pin addresses.
- Find Ghidra code paths that write to `HeroController.this+0x64` (in-memory offset corresponding to body+0x25 per HC Serialize). Whoever writes there is either the live source or the propagation point.

---

## Cross-references

- `rw/saves/edits/golden/geppetto/chapter1/zero-scores-stars7-ch1/info.md` — minted chapter-1 starting golden (the upstream of the round-trip POC)
- `rw/saves/edits/golden/geppetto/chapter2/2for1-thru-with-inventory/info.md` — chapter-2 follow-on (the downstream of the POC), where these three issues manifest
- `rw/findings/save-edit-pipeline.md` — pipeline docs + confirmed stat-source mappings + edit recipes
- `rw/findings/live-state-mirror-cascade.md` — directly relevant for issue (3); same decoupling pattern
- `rw/findings/geppetto-save-analysis.md` — early Geppetto save format triage
- `tools/rerw-src/lib/cooked.py` — decoder/encoder
