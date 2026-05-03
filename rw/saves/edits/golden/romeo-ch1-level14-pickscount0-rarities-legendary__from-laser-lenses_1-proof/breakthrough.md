# Romeo all-10-slots-empty golden — recipe

Verified-good golden: `Profile_1.ob` (74,156 bytes) in this directory.

## What this save is

Romeo, chapter 1, level 14, xp 0, all-rarities=Legendary, picks-block count = 0 with the 5-GUID block deleted. On load: every HUD slot 1–10 shows `?` and the picker fires on each level-up. **Every picker proposal — across all 10 slots, including the ult — arrives stamped at Legendary tier.** No auto-ult-insertion, no error-4 modal, no silencer trip.

## Source

`rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` — the canonical Geppetto chapter-2 proof. Despite the source being Geppetto, the chain swaps to Romeo as step 1.

## Recipe (apply in this exact order)

All steps are `rerw` CLI commands (no scripts). Order is significant only because step 5 (`all-talent-rarities`) reads the source's per-slot rarity array — must run before step 6 deletes the picks block.

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
DST=/tmp/romeo-build

mkdir -p "$DST"

# Step 1 — hero swap to Romeo
uv run --project tools/rerw-src rerw write savefile hero romeo \
  --source "$SRC" --dest "$DST" --force

# Step 2 — chapter 1
uv run --project tools/rerw-src rerw write savefile chapter 1 \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Step 3 — level 14
uv run --project tools/rerw-src rerw write savefile level 14 \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Step 4 — xp 0
uv run --project tools/rerw-src rerw write savefile xp 0 \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Step 5 — all talent rarities = Legendary (writes 28 tag=0x10 controller
# rarity bytes + 9 of the 10 per-slot rarity u32 entries — the ult slot at
# index 4 is skipped by index, not by value, so slots 6-10 are covered)
uv run --project tools/rerw-src rerw write savefile all-talent-rarities legendary \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Step 6 — clear picks (count -> 0, delete the picks-block GUIDs)
uv run --project tools/rerw-src rerw write savefile clear-picks \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Promote to golden
cp "$DST/Profile_1.ob" rw/saves/edits/golden/romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof/Profile_1.ob
```

What step 6 (`clear-picks`) does, in bytes:
1. Locate the talent record by its 15-byte GUID (`bfe7f6604385cb4887f6b4b79f6812`) prefixed with tag `\x12\x00\x00\x00`.
2. Walk back from the run-state-record close marker `22 22 bb aa` past the `[8 zero][float][8 zero]` trailer to find picks-block end. Back-fit `[u32 N][N × 16 bytes]` ending there.
3. Patch the picks-count u32 from N → 0.
4. Delete the N × 16 bytes of picks-block GUIDs. File shrinks accordingly.
5. Recompute the body CRC32 and write it at body offset `+0x0C`.

## Gotchas (each one cost time)

- **Step 5 reads the rarity array; step 6 destroys it.** `all-talent-rarities` reads the per-slot u32 array to know which entries to write. After `clear-picks`, the picks-block bytes are gone but the per-slot rarity array (at record body offset `+0x35`, separate region) is preserved. Order: step 5 before step 6.
- **`--force` after step 1.** The hero-swap CLI bumps a header marker; subsequent commands need `--force` to accept the modified-source state.
- **Source is Geppetto, not Romeo.** Don't try to start from a Romeo proof. The Romeo proofs we have aren't chapter-2 — the laser-lenses_1 Geppetto save is the only one with the right structural shape for this chain.
- **Game must be closed before swapping** the live `_Save/Profile_1.ob`. See `CLAUDE.md`.
- **Don't skip step 5.** Without `all-talent-rarities legendary`, the picker stamps rarities from whatever the dual-storage state happens to be (likely Common). Step 5 sets BOTH the per-slot u32 array (slots 1-4 + 6-10, skipping the ult at slot 5) AND the 28 tag=0x10 controller rarity bytes — the picker reads from both depending on the slot's compatibility state. See `rw/key-findings/talent-records.md` § "Other fields in the talent record."
- **Failure modes that look like success.** If any step writes wrong-length data, the load may show fresh-account fall-through (no save listed at all) instead of an error modal. The silencer mechanism (`rw/key-findings/save-silencer-mechanism.md`) can also disable saves silently if a deserializer trips. Always verify by loading the save AND checking that a subsequent in-game save actually advances `Profile_1.ob` mtime on disk.
- **Why level 14?** Level 14 is high enough to fire all 10 slot pickers on level-up (1 ult at 5 + 9 normal slots at 1–4 / 6–14). Lower levels gate fewer slots.
- **Why count=0 needs the delete.** Engine reads count, then expects whatever field follows the picks block. With count=0 but 80 bytes still present, structural desync → hard-fail error 4 → fresh-account fall-through. Deleting the 80 bytes keeps the file structurally consistent.

## Tried and ruled out (recipe variants)

- **Zero the GUIDs in place, leave count=5.** Engine substitutes the FIRST talent from the hero pool for every slot. All 10 slots show same talent.
- **Hero-swap + zeroed picks.** Same fallback — first-talent-in-new-hero's-pool fill.
- **Slot-5 prewrite of valid Romeo ult (WildWaltz).** Engine packed the ult into HUD slot 1 anyway. Pool index ≠ HUD slot in the recovery path.
- **Count=0 WITHOUT deleting bytes.** Hard-fail error 4 → fresh-account fall-through.
- **Add a `GroupLevelPersistentData` record to a clean save** (`rerw experimental add-level-record`). Save loaded but engine routed through new-game init regardless. Clean saves lack a "run-in-progress" marker that we haven't located yet.

## Verification

In-game checks after loading this golden:
- All 10 HUD slots show `?` placeholder.
- Level shows 14.
- Hero is Romeo.
- Chapter HUD reads chapter 1.
- Picker fires on first XP gain past level 14 → 15 (and continues on subsequent slot-unlocks).
- **Every picker proposal renders at Legendary rarity** (gold border / Legendary card frame). Verifies step 5 worked — both the per-slot u32 array and the 28 tag=0x10 controller rarity bytes are stamped.
- Subsequent in-game save advances `Profile_1.ob` mtime (= silencer not tripped).

## References

- `rw/key-findings/talent-records.md` § "All-10-slots-empty trick" — structural recipe.
- `rw/key-findings/save-silencer-mechanism.md` — what NOT to trip in this chain.
- `rw/scripts/inspect_picks_block.py` — the dig script that decoded the linear-append picks-block format across chapter-2 / chapter-3 / epilogue (used to verify the new generalized locator).
