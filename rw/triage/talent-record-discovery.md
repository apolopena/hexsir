# Talent record discovery in Geppetto chapter 2 saves

**Status:** RESOLVED — talent storage located, structure decoded, edit primitive designed.
**Created:** 2026-04-27
**Resolved:** 2026-04-27 (same session, after pivoting to herodef parse)

## Resolution summary

The 5 talent picks are stored as 16-byte skill-controller GUID references in a
fixed-tag record (tag=0x12, record GUID `bfe7f660...12a5`). Tier values (0=Common,
1=Rare, 2=Epic, 3=Legendary) for slots 1–4 sit earlier in the same record header.
Slot 5 (the ultimate) has no tier. Full byte layout, GUID-to-talent mapping, and
edit-primitive design: `rw/dumps/geppetto/talent-record-decoded.txt`.

The breakthrough came from parsing `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen`,
extracting all 28 skill-controller GUIDs, and finding that exactly 5 of them appear
TWICE in each save — once in the herodef-reference region near the hero record,
and once in a dedicated talent-pick block at the end of the talent record. Each
save's 5-pick block matches the player's gameplay-confirmed talent picks 1:1.

## Sources

- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
- rw/saves/proofs/geppetto/chapter2/twin-dummies-all-legendary-talents/Profile_1.ob
- rw/dumps/Ravenswatch.exe
- rw/ref/tree-deciphered.txt
- rw/key-findings/save-binary-format.md
- rw/key-findings/talents.md

## Confirmed Findings

### Talents are not stored as ASCII strings

Searched both proofs for known talent names — `Twin Dummies`, `Family Meeting`, `Clockwork Medicine`, `Sharp Noses`, `Overclock` (and underscore / no-space variants), plus cross-hero ult names (`Impalement`, `Blood Lash`, `Dreamwish`, `Frost Ray`, `Hunter's Souvenir`), plus asset-tree-derived Geppetto skill names (`LaserLenses`, `Pogo-Hoppers`, `SharpNose`, `RedButton`, `OiledMechanism`), plus `Pantin` and `Hero_Geppetto`. Zero hits.

A heuristic length-prefixed-string scan of the save body (post-type-registry, offset 0x700+) returned only 11 candidate strings: `Definitions` (path component, 2x), `Text`, six `MinimapMarker_*` UI labels, the player's Steam name `Quadrotonic`, and a few false-match short strings. None are talent names. Talents are encoded as compact identifiers, not strings.

### No standalone talent-definition asset extension exists

The deciphered asset tree has these `*def.ot` extensions: `Achievementdef`, `challengedef`, `dreamsharddef`, `enemycampdifficultydef`, `enemycamptierdef`, `enemydef`, `enemytribedef`, `gamemodedefaultdef`, `gamemodifierdef`, `herodef`, `ingredientdef`, `mapdef`, `rewarddef`, `tiledef`, `versiondef`. There is **no** `talentdef`, `skilldef`, `abilitydef`, or `powerdef`. Talents are inline data inside the cooked `Heroes/<Name>.herodef.ot.DtHeroDefinition.gen` binary, not separate assets. Implication: talent identifiers in the save are internal-to-herodef indexes/hashes — there's no asset path to grep for.

### Save record structure: paired `11 11 bb aa` / `22 22 bb aa` markers

Both chapter 2 proofs are bracketed into records by these markers. Counts (this session):

- `laser-lenses_1`: 2,471 records, supporting depth 0–2 nesting.
- `twin-dummies-all-legendary-talents`: 2,442 records (delta −29).

Records share a body format `[u32 type-tag][...body...]` between the start and end markers. Records can be nested.

### Size-68 and size-115 record buckets are NOT talent records

Initial heuristic: find buckets where exactly 5 records are unique to each save (matching the 5-talent-slot count). Two buckets fit: size 68 (5x in each) and size 115 (5x in each). Both inspected via full-body hex dumps:

- **Size 68:** body shape `[u32=33][nested-start][u32=25][4-byte-varying][float][int32_max sentinel][4-byte-varying][nested-end]`. Differences between A and B at the "varying" positions are 1-byte counter increments (e.g., `56 03 00 00` vs `57 03 00 00` = 854 vs 855). Engine-state counters or timers, not talent identifiers.
- **Size 115:** paired records have IDENTICAL first 32 bytes; differences are 2-byte tweaks at +0x42 (and one record has additional 2-byte differences at +0x18, +0x21, +0x29). Per-instance state drift, not talent identifiers.

Both ruled out. **Talents are not in the "5 records of fixed identical size" pattern.**

### Hero structural facts (player-supplied, gameplay-confirmed)

- Each hero has exactly **4 starting talents** ("special type 1 of 4").
- Each hero has exactly **2 ultimate talents** ("special type 2 of 2").
- Talents have rarity tiers **Common, Rare, Epic, Legendary** for non-ultimate slots; **L5 ultimate slot has no rarity tier**.
- Tier is per-run state (talents can be upgraded mid-run via items / mechanics; achievement `HaveLegendaryTalentsInASingleRun` exists in the asset tree).

### Ground truth for the second proof

`twin-dummies-all-legendary-talents` was produced by the player with all five talents at LEGENDARY tier (a deliberately uncommon gameplay state — picked specifically to maximize diff signal):

| Slot | Level | Talent | Tier |
|------|------:|--------|------|
| 1 | start | `Twin Dummies` | Legendary |
| 2 | L2 | `Family Meeting` | Legendary |
| 3 | L3 | `Clockwork Medicine` | Legendary |
| 4 | L4 | `Sharp Noses` | Legendary |
| 5 | L5 (ult) | `Overclock` | (no tier — ults have no rarity) |

For the existing `laser-lenses_1` proof, only the starting talent is known: `Dummy Ball`. The other 4 picks and their tiers are unknown.

### Talents are not in the hero container record

The hero record (length-prefixed `Heroes\Geppetto.herodef.ot` path) lives inside a 1323-byte container record at offsets 0x11cd0..0x121fb in `laser-lenses_1`. That container has 9 nested records. Inspection identified them as: a 35-sequential-u32 progression-flags list, a small 20-byte record, six 125–131 byte `BookMenu\UI_Icon_*` UI tracking records, and a 163-byte player profile record (which contains the Steam name `Quadrotonic`). **None are talent records** — the BookMenu UI records are content tracking; the player profile is account metadata.

## Unresolved

### Where are talent records actually located?

Three previously-stated hypotheses, two now ruled out:

1. ~~**Inside the 83-byte high-entropy base64 run-id blob**~~ — **ruled out this session.** Decoded both proofs' blobs and diffed byte-by-byte. Structure is `[stable 32-byte prefix][51-byte tail]`. The 32-byte prefix is byte-identical across the two distinct chapter-2 runs (so not a per-run UUID), but doesn't appear in the chapter-3, epilogue, clean, or EXE files (so not a hero key either). Most plausible: a chapter-2-entry checkpoint hash. The 51-byte tail diverges in a pattern with no structural alignment to 5 talent slots. Pre-blob header parses as `[u32=3][u32=729][float — A=1409.92 / B=1221.49, fits cumulative run-time in seconds][u32=112]`. Full byte-level dump: `rw/dumps/geppetto/talent-blob-and-record-analysis.txt`.

2. **A single large record holding the entire talent loadout.** Still open. Multi-record cluster analysis this session ruled out the unique-to-each clusters and singletons at sizes 29/50/54/78/82/119/155 (all show small numeric drift consistent with engine state, not 5 talent IDs). One untested candidate remains: the **~4800-byte top-level record at offset 0x702** (an array of ~1,190 u32 values mostly in the 13–36 range, with size delta exactly -12 entries between A and B — possibly an engine-state list, but not yet exhaustively parsed).

3. **Variable-size talent records.** Still open. Cluster heuristics by `(type_tag, depth, body_size)` did not surface a divergent group with the right shape, but tag-only or content-shape clustering hasn't been tried.

### Tier-homogeneity and talent-ID signature null results (this session)

Player gameplay ground truth: every talent in B is different from A, and B's 4 tiered talents are all Legendary while A had varied tiers.

- **Tier-homogeneity scan** (positions where A is heterogeneous and B is constant) across all unique-record clusters with count ≥ 4: **zero matches**. Talents are not stored as parallel per-slot records with a per-record tier byte.
- **All-distinct-IDs scan** (positions where each record holds a unique value): every "promising" position turned out to be either a session-allocation counter with a global per-save offset (e.g., tag=0x07 +0x47: A's 5 values are exactly 12 higher than B's at all positions — single counter, not 5 IDs), a run-stable shared ID (same in both saves), or a +1 mid-run drift.

These null results push the encoding away from "5 parallel records, one per slot" toward either "inline array in one record" or "outside the bracketed-record framework entirely."

### Why do chapter counters diverge here?

The `laser-lenses_1` proof has Counter A=1 / Counter B=1; the `twin-dummies` proof has Counter A=0 / Counter B=1. Both proofs are at chapter 2 entry per the player's confirmation. The earlier `save-binary-format.md` finding of "chapter counters always in lockstep" was based on chapter-transition saves only (chapter2 → chapter3 → epilogue). At intermediate auto-save triggers (mid-chapter, post-chapter-1-completion variants?) the counters apparently diverge. Mechanism unclear; not blocking talent work but should be noted in the canonical doc when convenient.

### What encoding does talent storage use?

Even once we locate the records, the encoding is unknown. Per the rarity-tier observations, each talent slot likely stores BOTH talent identity and tier. Three plausible encodings:

- `[talent_id: u32][tier: u8 or u32]` — two fields per slot.
- `[combined_id: u32]` — talent×tier baked into one ID (`Twin Dummies Common` and `Twin Dummies Legendary` would be different combined IDs).
- Tier as a separate parallel record (talent IDs in one list, tier values in another, indexed in lockstep).

The L5-ult-has-no-tier observation makes the encoding asymmetric — slots 1–4 carry tier info, slot 5 doesn't. That asymmetry might be discoverable as a structural difference between slot-5 records and slots-1-4 records once the location is found.

## Notes

### Diff substrate: same-character / same-progression / different-talents

The two proofs are deliberately structured for talent-isolation diff:

- Same hero (Geppetto in both source bytes; both proofs are post-chapter-1-completion checkpoints).
- Same level (5 in both).
- All 5 talent picks are different between the two saves.
- The `twin-dummies` proof has all-legendary tier — guaranteed to maximize tier-byte differences alongside talent-id differences. (Discriminating tier-bytes from talent-id-bytes will require a follow-up proof with same talents at different tiers, or byte-flip experiments. This is downstream work.)

### Methodology recap (sessions to date)

1. ASCII string searches across both proofs and the EXE.
2. Heuristic length-prefixed-string scan over save body.
3. Record-level diff: parse both saves into bracketed records, compute SHA-256 fingerprint of each record body, compare set membership across saves.
4. Bucket analysis: group records by size, find buckets where exactly 5 records are unique to each save.
5. Full-body hex inspection of bucket-matching records to verify or reject talent-record hypothesis.
6. **Base64 run-id blob decode + diff** (this session, dump at `rw/dumps/geppetto/talent-blob-and-record-analysis.txt`).
7. **Cluster by `(type_tag, depth, body_size)` rather than size alone** (this session) — surfaces additional clusters but none with talent-shaped signatures.
8. **GUID-paired diff%** across all unique-to-each records — max divergence 12%, no record is wholly different. (Caveat: GUID extraction is unreliable for container records whose offset 4..7 holds the nested-record start marker.)
9. **Tier-homogeneity signature** scan (A heterogeneous, B homogeneous) — zero hits anywhere.
10. **All-distinct-IDs signature** scan — every match resolves to a session counter with global offset between saves.
11. **Anchor-based byte-level diff** of the full saves — works in early file regions (header / type registry), breaks down once files go significantly out of sync mid-run-state.

### Steam Cloud constraint affects byte-flip discrimination

When a candidate record region is identified, byte-flip experiments are the discriminator: modify a u32 in the candidate region, swap into game with player permission, observe whether displayed talent in slot N changes. Each experiment is single-session per the Steam Cloud overwrite-on-launch behavior. Plan accordingly — bundle multiple flips per session if possible, observe carefully before quit.

### `Heroes/Geppetto.herodef.ot` parsing as fallback

If save-byte-level discovery exhausts, parsing the cooked `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` directly would give us the per-hero talent ID registry (since talents are inline in the herodef binary). The OEngine cooked-asset format is unknown to this project; would require reverse-engineering. Substantial effort but a definitive path. Not yet attempted.
