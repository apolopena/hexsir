# talent-slot1-to-twin-dummies

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- **Lineage chain:** chapter-2 proof → slot 1 talent GUID swap (Special Creates Dummy / Dummy Ball → Trait Twins / Twin Dummies)
- **Edit name:** `talent-slot1-to-twin-dummies`

## Reproduction recipe

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
DST=rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/talent-slot1-to-twin-dummies

rerw write savefile talent --slot 1 --key trait_twins \
  --source "$SRC" --dest "$DST" --force
```

Byte-level: 16 bytes at data offset `0xf130` (slot 1 GUID inside the picks block) + 4 bytes at `0x0C` (CRC32 recompute). Tier byte left unchanged → Twin Dummies displays at the source's slot 1 rarity (Common).

## Verified in-game

- Date: 2026-04-27
- Loads cleanly.
- Slot 1 displays Twin Dummies at Common tier (tier byte unchanged).

Reference: `rw/findings/talent-records.md`.
