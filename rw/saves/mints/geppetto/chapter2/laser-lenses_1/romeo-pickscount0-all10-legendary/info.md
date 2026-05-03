# romeo-pickscount0-all10-legendary

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` (canonical Geppetto chapter-2 boss-kill proof — step 2 of the chain swaps the hero to Romeo)
- **Lineage chain:** Geppetto chapter-2 proof → `rerw mint savefile` → hero=Romeo → level=14 → all-talent-rarities=Legendary → clear-picks
- **Edit name:** `romeo-pickscount0-all10-legendary`
- **SHA-256:** `3382e7b5392f3f2190757b904754b2b14ef6b0c9f5ac61bb35da98efc4c9d7e2`
- **Size:** 73,389 bytes

This is a **mint** (per `rw/docs/playbook.md` § Save Directory Conventions): the build chain begins with `rerw mint savefile`. Output is chapter-1 with all per-run state zeroed, then customized into a Romeo-at-level-14 fresh-pickset save where every picker fire arrives stamped at Legendary.

## Reproduction recipe

All steps are `rerw` CLI commands (no scripts). Order is significant — see "Order dependencies" below.

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
DSTDIR=rw/saves/mints/geppetto/chapter2/laser-lenses_1/romeo-pickscount0-all10-legendary
DST=$DSTDIR/Profile_1.ob
mkdir -p "$DSTDIR"

# Step 1 — mint: zero per-run state (currencies, score, level/xp, chapter)
#   Output: chapter-1 starting save, level=1, xp=0, all held inventory zeroed.
uv run --project tools/rerw-src rerw mint savefile \
  --source "$SRC" --dest "$DSTDIR" --force

# Step 2 — hero swap to Romeo
#   Splices the `Heroes\Romeo.herodef.ot` reference into the save.
uv run --project tools/rerw-src rerw write savefile hero --key romeo \
  --source "$DST" --dest "$DSTDIR" --force

# Step 3 — level 14
#   Sets the in-run hero level. xp stays at 0 from step 1.
uv run --project tools/rerw-src rerw write savefile level 14 \
  --source "$DST" --dest "$DSTDIR" --force

# Step 4 — all-talent-rarities legendary
#   Writes BOTH (a) the 28 tag=0x10 controller rarity bytes (each Romeo
#   skill controller stamped Legendary) AND (b) 9 of the 10 per-slot u32
#   rarity entries (slot index 4 = ult, skipped).
uv run --project tools/rerw-src rerw write savefile all-talent-rarities legendary \
  --source "$DST" --dest "$DSTDIR" --force

# Step 5 — clear-picks (LAST)
#   Picks-count u32 → 0; deletes the 80 bytes (5 × 16) of GUIDs left over
#   from the chapter-2 source proof. File shrinks 80 bytes; CRC recomputed.
uv run --project tools/rerw-src rerw write savefile clear-picks \
  --source "$DST" --dest "$DSTDIR" --force
```

## Order dependencies

- **Step 1 (mint) must come first.** Every later step operates on `$DST` (which mint creates).
- **Steps 2–4 are order-independent w.r.t. each other** — hero, level, and rarities live in disjoint regions of the save body. Any permutation among them produces the same byte-equivalent output.
- **Step 5 (clear-picks) must come LAST.** Reasons:
  - `all-talent-rarities` (step 4) reads the per-slot u32 array — the talent record body must still be at its post-mint offset. clear-picks shrinks the file by 80 bytes, shifting downstream offsets; running it earlier would force every later step to re-locate fields after the shift and is not how the CLI primitives are wired.
  - The picks-block trailer's timing float is zeroed by mint. The `find_picks_count` locator was patched (this session) to accept `f_val == 0.0` alongside the populated-run range — without that fix, clear-picks fails post-mint with `Could not locate picks-count u32 after talent record at 0x...`. See `tools/rerw-src/lib/talent_edit.py` § `find_picks_count`.

## Verified in-game

- Date: 2026-05-03
- Loads cleanly, no SaveCompat modal.
- HUD: hero is Romeo, level 14, chapter 1, all 10 slots show `?` placeholder.
- Picker fires on first XP gain past level 14 → 15 and continues on subsequent slot-unlocks.
- Every picker proposal renders at Legendary rarity.

## Generalization to other chapters

The chain works on chapter-3 and epilogue proofs unchanged — only `--source` differs. Each step is chapter-agnostic:

- `mint savefile` — chapter-aware since BREAKTHROUGH-1.
- `hero` / `level` / `all-talent-rarities` — operate on chapter-stable byte regions.
- `clear-picks` — uses the universal `find_picks_count` locator (post-bug-fix) which handles N=5/8/10 and pre-mint vs post-mint trailers.

Example for chapter-3:

```bash
SRC=rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob
DSTDIR=rw/saves/mints/geppetto/chapter3/laser_lenses_1/romeo-pickscount0-all10-legendary
# ...same five steps as above
```

The output is structurally identical regardless of source chapter — clear-picks deletes all GUIDs and zeros the count, so post-output saves are uniform.

## Cross-references

- `rw/findings/talent-records.md` — picks-block universal locator, dual-storage rarity model, all-10-slots-empty trick.
- `rw/findings/save-mint-status.md` — mint scope (what it zeros, what it leaves).
- `rw/docs/playbook.md` § Save Directory Conventions — mint definition, path convention, required `info.md`.
- `tools/rerw-src/lib/talent_edit.py` — `find_picks_count`, `clear_picks`, `write_all_slot_rarities`, `write_all_rarity_bytes`.
