# talent-slot1-tier-byte-to-legendary

Single-byte tier edit: Special Creates Dummy (Dummy Ball) tier `0x00` (Common) → `0x03` (Legendary). Talent GUID unchanged. Slot 1 Dummyball displayed at Legendary in-game with the Legendary stat scaling active.

**Source:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
**Bytes changed:** 1 byte at data offset `0xea97` (tier byte = Special Creates Dummy GUID at `0xea86` + 17) + 4 bytes at `0x0C` (CRC32 recompute).
**Verified:** 2026-04-27 in-game; Dummyball tooltip showed "LEGENDARY" tag and uplifted damage.
**Reference:** `rw/key-findings/talent-records.md`
