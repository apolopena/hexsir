[← Back to findings](README.md)

# Enemy AI — target/focus field and the redirect question

**Status:** in-progress
**Created:** 2026-05-06

Sparse seed doc. We have one suggestive observation (an enemy entity holding a pointer to the actor that was actively damaging it) and one observation that conflicts with the simple "this slot is the AI target" reading. The headline question — *can we redirect an enemy's AI target to flip enemies onto each other?* — is wide open.

## Sources

- `rw/findings/enemy-spawn-architecture.md` — `+0x08`/`+0x10` observations originally captured here under the "engagement state" framing. This doc surfaces the AI-target reading that was buried there.
- `tools/frida/mods/spawn_capture.js` — the capture mechanism that produced the observations.
- Live REPL captures from a Cultist/Summoner cauldron fight on 2026-05-06 (Tentacle and Summoner `oCEntity` byte readings).

## Unresolved

### The seed observation

In a Cultist-cauldron fight on 2026-05-06, with the player playing Geppetto, the captured `Cultist_Summoner_Summoned_Tentacle` entity had `*(entity + 0x08)` pointing at the player's `Hero_Geppetto_Dummy` entity — the very actor that was hitting the Tentacle at the time of capture. That fits an "AI target / current focus" reading cleanly: an enemy locked onto a hostile-to-it actor that's damaging it.

If `+0x08` IS the AI-target field, then the redirect path is straightforward in shape: write a different entity pointer into that slot and observe whether the Tentacle reorients. Targets to try:
- Another enemy entity (to test enemy-vs-enemy combat).
- A neutral/unrelated entity (to test target-loss behavior).
- Null (to test target-clear behavior).

### The conflict

In the same capture, the `Elite_Cultist_Summoner` entity had `*(entity + 0x08)` pointing at one of its allied Snakes (Snake[0]), and `*(entity + 0x10)` pointing at Snake[1]. Cultists do not target their own snakes — they're allies — so a clean "current AI target" reading does not survive this observation.

Three candidate explanations, none verified:

1. **Multi-purpose slot.** `+0x08` decays to a different semantic (intrusive linked-list node — an "allies-list" pointer) when the entity has no current hostile target. Plausible but speculative.
2. **Two adjacent fields conflated.** `+0x08` and `+0x10` are actually two different concepts; we caught one entity in a state that wrote to one of them and the other entity in a state that wrote to the other. The Tentacle's Dummy-pointer at `+0x08` may live in field A; the Summoner's Snake-pointer may live in field B at the same offset by coincidence.
3. **Wrong offset.** The actual AI-target slot is at a different offset (a few qwords away on the same `oCEntity`, or on the `EnemyController` component rather than the entity itself). The Tentacle-vs-Dummy pairing was a coincidence.

### Headline question

Can we redirect enemy AI targeting at runtime — pointer-write into the right slot, or a function call that the engine respects — to make enemies fight each other (or to make them ignore the player)?

## Notes

### Where to dig next

The spawn-architecture finding doc concluded that *parent-spawned-by* relationships do not live on the entity wrapper (we scanned 1600 bytes of a Tentacle for any backref to its summoner — summoner pointer not present). It hypothesised the relationship lives on the `EnemyController` component instead. The same hypothesis applies to AI-target state: it may not live in `oCEntity`'s own bytes at all, but on the component pointed at from the entity's component hashmap (`+0x5e8`/`+0x5f0`/`+0x5f8`/`+0x600`). First dig: walk a captured Tentacle → its `EnemyController` component → scan the component bytes for the Geppetto Dummy address. If found, that's the field; if not, expand the search to the component's neighbours.

A complementary RE-side approach: search Ghidra for symbols/strings related to AI targeting (`Target`, `Aggro`, `setTarget`, `Aim`, `Focus`) and trace setters back to the field they write. This works static; no live-game required.

### Cross-references

- `rw/findings/enemy-spawn-architecture.md` — original site of the `+0x08`/`+0x10` observations under the "engagement state" framing. The byte observations there are still correct; this doc just promotes the AI-target interpretation.
- `rw/docs/game-rules.md` — the gameplay-level question ("can enemies fight each other?") is recorded there as a side tangent under the cauldron-and-waves entry's future-digs notes.
- `rw/docs/wishlist.md` — technical work items (locate field, attempt redirect) are tracked there.
