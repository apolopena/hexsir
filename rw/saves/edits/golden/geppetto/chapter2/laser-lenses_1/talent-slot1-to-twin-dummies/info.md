# talent-slot1-to-twin-dummies

Slot 1 talent GUID swap: Special Creates Dummy (Dummy Ball) → Trait Twins (Twin Dummies). Tier left unchanged → Twin Dummies displayed at Common in-game.

**Source:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
**Bytes changed:** 16 bytes at data offset `0xf130` (slot 1 talent GUID inside the talent-pick block) + 4 bytes at `0x0C` (CRC32 recompute).
**Verified:** 2026-04-27 in-game; Twin Dummies appeared in slot 1 (Common tier).
**Reference:** `rw/key-findings/talent-records.md`
