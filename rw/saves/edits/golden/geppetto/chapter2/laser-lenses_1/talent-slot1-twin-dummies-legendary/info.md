# talent-slot1-twin-dummies-legendary

Combined talent swap + tier edit: slot 1 GUID Special Creates Dummy → Trait Twins, AND Trait Twins' tier byte `0x00` → `0x03`. Slot 1 displayed Twin Dummies at Legendary in-game with the Trait scaling active.

**Source:** `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`
**Bytes changed:**
- 16 bytes at data offset `0xf130` (slot 1 talent GUID inside the talent-pick block: Dummy Ball → Twin Dummies)
- 1 byte at data offset `0xebe1` (Trait Twins' tag=0x10 tier byte: Common → Legendary; offset = Trait Twins GUID at `0xebd0` + 17)
- 4 bytes at `0x0C` (CRC32 recompute)

**Verified:** 2026-04-27 in-game; Twin Dummies tooltip showed "LEGENDARY" tag and the Trait's Legendary-tier effect text.
**Reference:** `rw/key-findings/talent-records.md`
