# romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` (canonical Geppetto chapter-2 proof — despite the source being Geppetto, step 1 swaps the hero to Romeo)
- **Lineage chain:** Geppetto chapter-2 proof → hero-swap to Romeo → chapter 1 → level 14 → xp 0 → all-talent-rarities legendary → clear-picks
- **Edit name:** `romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof`
- **File size:** 74,156 bytes

## Reproduction recipe

All steps are `rerw` CLI commands (no scripts). Order is significant: step 5 (`all-talent-rarities`) reads the source's per-slot rarity array and must run before step 6 deletes the picks block.

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

# Step 5 — all talent rarities = Legendary
#   (writes 28 tag=0x10 controller rarity bytes + the per-slot rarity u32 array)
uv run --project tools/rerw-src rerw write savefile all-talent-rarities legendary \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Step 6 — clear picks (count -> 0, delete the picks-block GUIDs)
uv run --project tools/rerw-src rerw write savefile clear-picks \
  --source "$DST/Profile_1.ob" --dest "$DST" --force

# Promote
cp "$DST/Profile_1.ob" rw/saves/edits/golden/romeo-ch1-level14-pickscount0-rarities-legendary__from-laser-lenses_1-proof/Profile_1.ob
```

Helper script: `rw/scripts/lab_build_romeo_all10_legendary.py` runs the same chain end-to-end.

## Verified in-game

- Date: 2026-05-02
- Loads cleanly, no SaveCompat modal.
- All 10 HUD slots show `?` placeholder.
- Level shows 14; hero is Romeo; chapter HUD reads chapter 1.
- Picker fires on first XP gain past level 14 → 15 (and continues on subsequent slot-unlocks).
- **Every picker proposal renders at Legendary rarity** (gold border / Legendary card frame) — verifies step 5 stamped both the per-slot u32 array and the 28 tag=0x10 controller rarity bytes.
- Subsequent in-game save advances `Profile_1.ob` mtime (silencer not tripped).

The all-10-slots-empty trick (count=0 + 80-byte GUID block deletion) and the dual-storage rarity behavior are documented in `rw/findings/talent-records.md` (§"All-10-slots-empty trick" and §"Other fields in the talent record"). The "tried and ruled out" recipe variants — zero the GUIDs in place leaving count=5; hero-swap + zeroed picks; slot-5 prewrite of valid Romeo ult; count=0 without deleting bytes — were captured in the same finding.
