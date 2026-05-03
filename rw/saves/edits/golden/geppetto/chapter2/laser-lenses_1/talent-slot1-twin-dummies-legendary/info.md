# talent-slot1-twin-dummies-legendary

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- **Lineage chain:** chapter-2 proof → slot 1 GUID swap (Special Creates Dummy → Trait Twins) + tier byte to Legendary
- **Edit name:** `talent-slot1-twin-dummies-legendary`

## Reproduction recipe

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
DST=rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/talent-slot1-twin-dummies-legendary

rerw write savefile talent --slot 1 --key trait_twins \
  --source "$SRC" --dest "$DST" --force
rerw write savefile tier --slot 1 --tier legendary \
  --source "$DST/Profile_1.ob" --dest "$DST" --force
```

Byte-level:

- 16 bytes at data offset `0xf130` (slot 1 GUID inside the picks block: Dummy Ball → Twin Dummies)
- 1 byte at data offset `0xebe1` (Trait Twins' tag=0x10 tier byte: Common → Legendary; offset = Trait Twins GUID at `0xebd0` + 17)
- 4 bytes at `0x0C` (CRC32 recompute)

## Verified in-game

- Date: 2026-04-27
- Loads cleanly.
- Twin Dummies tooltip shows "LEGENDARY" tag; Trait's Legendary-tier effect text active in tooltip.

Reference: `rw/findings/talent-records.md`.
