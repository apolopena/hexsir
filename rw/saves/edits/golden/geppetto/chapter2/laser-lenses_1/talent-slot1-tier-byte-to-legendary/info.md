# talent-slot1-tier-byte-to-legendary

## Provenance

- **Source path:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
- **Lineage chain:** chapter-2 proof → single tier-byte edit (Special Creates Dummy / Dummy Ball: Common → Legendary)
- **Edit name:** `talent-slot1-tier-byte-to-legendary`

## Reproduction recipe

```bash
SRC=rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob
DST=rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/talent-slot1-tier-byte-to-legendary

rerw write savefile tier --slot 1 --tier legendary \
  --source "$SRC" --dest "$DST" --force
```

Byte-level: 1 byte at data offset `0xea97` (tier byte = Special Creates Dummy GUID at `0xea86` + 17, where +17 = 16-byte GUID + 1 flag byte) + 4 bytes at `0x0C` (CRC32 recompute). Talent GUID unchanged.

## Verified in-game

- Date: 2026-04-27
- Loads cleanly.
- Slot 1 Dummyball tooltip shows "LEGENDARY" tag and uplifted damage values consistent with Legendary-tier scaling.

Reference: `rw/findings/talent-records.md`.
