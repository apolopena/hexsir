# Talent record discovery in Geppetto chapter 2 saves

**Status:** CLOSED — talent picks AND tier byte both located, decoded, and verified end-to-end (3 verified golden mods + in-game player screenshots). Edit primitive shipped as `rerw write savefile --talent-slot N --talent-id ... --tier ...` (committed as PRP-2 / planning-system PRP-3). Canonical reference: `rw/key-findings/talent-records.md`.
**Created:** 2026-04-27
**Resolved:** 2026-04-28 (multi-session investigation; tier byte location landed in the second session after the body+0x35 false lead was falsified by a lab-edit test)

## Resolution summary

The 5 talent picks are stored as 16-byte skill-controller GUID references in a fixed-tag record (tag=0x12, record GUID `bf e7 f6 60 43 85 cb 48 87 f6 b4 b7 9f 68 12` + separator byte `0xa5`). The picks sit at the END of the record body, anchored by an 8-byte sentinel `[u32 = 0][u32 = 5]` and laid out back-to-back at 16-byte intervals.

Tier is **NOT** stored in the talent record. Tier is a single u8 at offset GUID+17 of each tag=0x10 first-occurrence record, in the herodef-reference region near the hero record. The engine reads tier from the tag=0x10 record matching the slot's *current* GUID — change the slot's GUID and the engine looks up tier from the new talent's tag=0x10 record. Tier-value encoding: `0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker (slot 5 ult; no real tier)`.

The breakthrough came in two stages: (1) parsing `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` to extract all 28 skill-controller GUIDs, then noticing 5 of them appear twice in each save (once in the herodef-reference region as tag=0x10 records, once in the talent-pick block at the end of the tag=0x12 record); (2) ruling out a near-coincidence (the body+0x35 u32 sequence inside the talent record statistically matched player tier distribution, but a single-byte lab edit confirmed the engine doesn't read tier from there — see "Ruled out" below).

End-to-end verified by three in-game tests on Save A: talent-only swap (slot 1 → Trait Twins, displayed at Common), tier-only edit (Dummy Ball Common → Legendary), and combined (slot 1 → Trait Twins at Legendary). All three goldens shipped under `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/talent-slot1-*/`.

## Sources

- rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
- rw/saves/proofs/geppetto/chapter2/twin-dummies-all-legendary-talents/Profile_1.ob
- rw/harvested/Definitions/Heroes/*.yqz (12 hero herodef binaries; deciphered names of form `<Name>.herodef.ot.DtHeroDefinition.gen`)
- rw/dumps/Ravenswatch.exe
- rw/ref/tree-deciphered.txt
- rw/key-findings/save-binary-format.md
- rw/key-findings/talents.md
- rw/key-findings/talent-records.md  ← canonical state-of-knowledge after this triage closed

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

## Ruled out during this investigation (closed leads)

### "Inside the 83-byte high-entropy base64 run-id blob"

Decoded both proofs' blobs and diffed byte-by-byte. Structure is `[stable 32-byte prefix][51-byte tail]`. The 32-byte prefix is byte-identical across the two distinct chapter-2 runs (so not a per-run UUID), but doesn't appear in the chapter-3, epilogue, clean, or EXE files (so not a hero key either). Most plausible: a chapter-2-entry checkpoint hash. The 51-byte tail diverges with no structural alignment to 5 talent slots. Pre-blob header parses as `[u32=3][u32=729][float — A=1409.92 / B=1221.49, fits cumulative run-time in seconds][u32=112]`. Investigation dump: `rw/dumps/geppetto/talent-blob-and-record-analysis.txt`.

### "Size-68 / size-115 record buckets contain talents"

Heuristic: find buckets where exactly 5 records are unique to each save. Size 68 (5x in each) and size 115 (5x in each) both fit. Hex inspection ruled both out — engine-state counters / per-instance state drift, not talent identifiers.

### "A single large record holds the entire talent loadout"

Multi-record cluster analysis ruled out unique-to-each clusters and singletons at sizes 29/50/54/78/82/119/155 (all small numeric drift, engine state). Also ruled out: the ~4800-byte top-level record at offset 0x702 (array of ~1,190 u32s in the 13–36 range, size delta -12 between A and B — looks like an engine-state list / spawn-id pool).

### "Tier values for slots 1–4 sit at body+0x35..+0x44 of the talent record"

This was the closest near-miss in the investigation. The 4 u32 LE values at body+0x35..+0x44 of the tag=0x12 talent record statistically match the player's tier distribution **perfectly**:

- Save A: `[0, 2, 1, 0]` matches Common/Epic/Rare/Common (4 tiered slots).
- Save B: `[3, 3, 3, 3]` matches all-Legendary (player gameplay-confirmed).

The values appear at **exactly the same body-relative offset (0x35) in both saves**, with no other location in the file matching. The `0x00..0x03` value range fits Common-Rare-Epic-Legendary. By pure statistics this is far too clean to be coincidence.

**Falsified by lab test:** wrote `u32(3)` to all 4 positions in Save A and loaded — Dummy Ball still displayed at Common. The bytes ARE tier-related (a parallel encoding the engine writes alongside the canonical) but the engine does NOT read them for HUD display.

The ACTUAL tier byte was found shortly after, at GUID+17 of each tag=0x10 first-occurrence record near the hero record. Single-byte lab edit (`0x00 → 0x03`) at that position changed Dummy Ball's display tier from Common to Legendary. End-to-end verified.

### "Tier-homogeneity / talent-ID signature scans of unique-to-each records"

Multiple structural scans all produced null results:
- **Tier-homogeneity** (positions where A is heterogeneous and B is constant) across unique-record clusters with count ≥ 4: zero matches in any cluster.
- **All-distinct-IDs** scan: every "promising" position turned out to be either a session-allocation counter (e.g., tag=0x07 +0x47: A's 5 values are exactly 12 higher than B's at every position — single global counter, not 5 IDs), a run-stable shared ID, or a +1 mid-run drift.

These null results were correct — the unique-to-each clusters genuinely don't contain the talent picks. The picks live in the tag=0x12 record's pick block (which differs per slot but pairs by record GUID, not by content shape).

## Side observation (not blocking, not closed)

### Chapter counters diverge between the two chapter-2 proofs

The `laser-lenses_1` proof has Counter A=1 / Counter B=1; the `twin-dummies` proof has Counter A=0 / Counter B=1. Both proofs are at chapter 2 entry per the player's confirmation. The earlier `save-binary-format.md` finding of "chapter counters always in lockstep" was based on chapter-transition saves only (chapter2 → chapter3 → epilogue). At intermediate auto-save triggers (mid-chapter, post-chapter-1-completion variants?) the counters apparently diverge. Mechanism unclear; not blocking talent work, noted here for future investigation.

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
6. Base64 run-id blob decode + diff.
7. Cluster by `(type_tag, depth, body_size)` rather than size alone.
8. GUID-paired diff% across all unique-to-each records — max divergence 12%, no record is wholly different. (Caveat: GUID extraction is unreliable for container records whose offset 4..7 holds the nested-record start marker.)
9. Tier-homogeneity signature scan (A heterogeneous, B homogeneous) — zero hits.
10. All-distinct-IDs signature scan — every match resolves to a session counter with global offset between saves.
11. Anchor-based byte-level diff of the full saves — works in early file regions (header / type registry), breaks down once files go significantly out of sync mid-run-state.
12. **Herodef parse — the breakthrough.** Deciphered `Heroes/Geppetto.herodef.ot.DtHeroDefinition.gen` (path `Kqjjqiir.nqurtqh.ri.NiAqurNqhdzdidrz.yqz` from the cooked Steam install via `rerw decipher`), parsed all 28 `Skill Controller XXX` length-prefixed strings + their immediately-following 16-byte GUIDs.
13. **GUID search across both proof saves** — found exactly 5 controller GUIDs appearing TWICE in each save: once in the herodef-reference region near the hero record, once in a back-to-back block at the end of a tag=0x12 record. The 5 second-occurrences match each save's player-confirmed talent picks 1:1.
14. **Talent-pick block byte layout characterized** — sentinel anchor `[u32=0][u32=5]` precedes 5 × 16-byte GUIDs. Single-byte lab edit verified end-to-end.
15. **Tier byte hunt** — initially a near-miss false lead at body+0x35..+0x44 of the talent record (perfect statistical match to tier values, but lab edit had no in-game effect). Located at GUID+17 of each tag=0x10 first-occurrence record after re-examining the herodef-reference region. Single-byte lab edit (`0x00 → 0x03`) flipped Dummy Ball's display tier Common → Legendary, verified by player screenshot.

### Steam Cloud constraint affects byte-flip discrimination

When a candidate record region is identified, byte-flip experiments are the discriminator: modify a u32 in the candidate region, swap into game with player permission, observe whether displayed talent in slot N changes. Each experiment is single-session per the Steam Cloud overwrite-on-launch behavior. Plan accordingly — bundle multiple flips per session if possible, observe carefully before quit.

### `Heroes/<Hero>.herodef.ot` parsing — was the fallback, became the bridge

Originally listed as a worst-case fallback (decode the cooked OEngine binary to find a per-hero talent ID registry). Turned out to be much simpler than feared: the herodef stores Skill Controllers as length-prefixed `Skill Controller XXX` strings followed immediately by 16-byte GUIDs. Parsing them is a 30-line Python loop. All 12 hero herodefs were harvested and parsed; per-hero YAMLs at `tools/rerw-src/data/heroes/<hero>.yaml` ship 28 controller GUIDs each (336 GUIDs total).
