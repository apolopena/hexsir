[← Back to findings](README.md)

# Player setPosition reconciliation — controller-tick coupling and the snap

**Status:** in-progress
**Created:** 2026-05-08
**Last updated:** 2026-05-08

## Sources

- Live Frida-driven testing this session (chapter-1 / Dark Hills)
- `rw/findings/spawn-at-coord-recipe.md` — `oCEntity_setPosition` primitive (RVA `0x6ca7f0`, vtable `+0x50`); off-map free-fall observation from prior session
- `rw/findings/transporter-placement-primitive.md` — Transporter primitive verified live
- `tools/frida/mods/powers/Transporter.js` v0.3.0 — current `warpPlayer` / `dropPlayer` implementations
- `tools/frida/mods/powers/Map.js` v0.9.0 — chapter coordinate getters
- `tools/frida/util/EntitySpawners.js` v0.1.0 — shared spawner-ctor capture

## Headline

**`oCEntity_setPosition` writes are split across two systems with different update cadences.** The renderer / camera reads the new position from `player+0x324` immediately, so a warp visibly relocates the player on the next render. The player movement controller — which applies gravity, collision, and the **grounded-snap-to-walkable-surface** resolution — runs on its own tick, gated by player input and game-loop activation. Stacked writes within a single JS turn (e.g. an "off-map prep then in-map drop" pair) collapse from the controller's perspective into a single resolution against the latest write, defeating the prep.

The downstream effect: drops-from-above for the player are not deterministically achievable with the current setPosition-only primitive. Whether the player visibly falls or instantly snaps to the destination's grounded surface depends on whether the controller ticks between the prep and the drop, which depends on player input and other engine state we haven't fully isolated.

## Definitions

- **Snap.** When `setPosition(x, y, z)` is followed by a controller tick, the controller resolves the player's position to the nearest walkable surface at (x, z), discarding the requested Y in favor of that surface's elevation. Visible effect: instantaneous appearance at the destination's ground level, no fall animation.
- **Fall.** When the controller's grounded-flag is clear and a new airborne position is accepted, gravity carries the player down to a colliding surface over multiple frames. Visible effect: visible descent animation.
- **Off-map prep.** A `setPosition` write to coordinates outside the chapter's Gpn-bounds rectangle (e.g. `(-410, 2, 0)` when `xMin = -400`). Empirically clears the player's grounded state because no walkable surface exists nearby to snap onto. Documented free-fall behavior in `spawn-at-coord-recipe.md` §"Off-map teleport."
- **Drop recipe.** The two-step pattern of `setPosition(off-map)` then `setPosition(in-map at high Y)` — intended to clear grounded with the prep so the in-map drop respects Y and the player falls.

## Confirmed observations (this session)

1. **Naive in-map warp at high Y snaps.** `Transporter.warpPlayer(0, 50, 0)` from a grounded state lands the player at `(-11.2, 12.0, 5.7)` — the central platform's grounded surface. Y=50 is ignored. Same pattern at Y=10 / 15 / 30 / 50.
2. **Off-map free-fall reproduces.** Warping to `(-500, 0, 0)` (well past `xMin = -400`) triggers free-fall — Y decreases over time as gravity applies and no collision floor is found. Matches the prior-session observation in `spawn-at-coord-recipe.md`.
3. **Stacked off-map → in-map sometimes produces a fall.** `Transporter.warpPlayer(-410, 2, 0); Transporter.warpPlayer(50, 50, 50)` at one point in the session produced a visible fall onto raw terrain at (50, ?, 50). The same exact command later in the session produced a snap. Reproducibility is broken — at least one variable we haven't isolated controls the difference.
4. **Camera and physics decouple.** Warping to `(-148, 50, -53)` (the safe-zone teleporter plate at high Y) caused the camera to animate as if the player were falling — but the player position visibly held mid-air until the user clicked into the game window, at which point the controller ticked once and snapped the player to the plate's grounded Y. The camera renders the new `player+0x324` immediately; the controller does not apply gravity or snap until its tick fires.
5. **All five tested landmarks snap on warp.** Central platform `(0, *, 0)` → snap. Safe-zone plate `(-148, *, -53)` → snap. Hourglass `(-149, *, -65)` → snap. Cauldron minimap marker `(-130, *, 13)` → snap. Boss arena `(140, *, 26)` → snap.
6. **Empirical Y ceiling around 50.** When the off-map prep DID produce a fall, the in-map target Y was 50. Lower Y values with off-map prep have not been cleanly reproduced. Whether the threshold is exactly 50 or just "high enough to escape some snap-search radius" is unconfirmed.

## What this rules out

- **"Snap is a property of the destination prop type."** Earlier in the session the working hypothesis was "designer-walkable props snap; raw terrain doesn't." Five landmark snaps were consistent with that — but observation #4 (camera animates the fall, controller snaps on tick) shows the snap is a *post-hoc* resolution by the controller, not a property baked into the destination. The user's correction in this session: there's no snap-prop concept; the snap is purely the controller's grounded-resolve pass.
- **"Off-map prep deterministically clears grounded for the next write."** Observation #3 — same command, two outcomes — falsifies "the prep always works." The prep takes effect only when the controller ticks between the prep write and the drop write. Without that tick, the controller sees only the latest write and resolves it normally (snap).
- **"Window-focus is the only gating variable."** Earlier hypothesis was that the engine pauses entirely when unfocused. Observation #4 shows the renderer is NOT paused (camera animates). Only the controller / physics is gated. The user further observed that even with the window focused, the controller doesn't tick on a per-frame basis — it appears tied to player input.

## What's still unknown

1. **What exactly causes the controller to tick.** Player movement input is the strongest candidate (consistent with the user's observation that warps "took effect" only after they moved). Other possibilities: a periodic global update at lower frequency, a state-machine transition, an event-driven dispatch we haven't traced.
2. **The player controller's tick function.** `rw_lab.js` already hooks `0x38e260` for one-shot player-entity capture during chapter load. That may or may not be the controller's per-tick update — it's the function used to grab the HC pointer, not necessarily the per-frame movement tick. A separate Ghidra dig is needed to identify the actual controller update function for the player class.
3. **Whether the off-map prep recipe can be made deterministic.** If we can call the controller's tick function manually between the two `setPosition` writes, the recipe becomes reliable. Without that, drops are input-coupled and not automatable.
4. **The "arming stack" the user recalls from a working session.** During this session the user mentioned that a specific load-order sequence — "some combination" of `loadPower` calls and a hook arming — had previously produced reliable drops. That sequence isn't documented and couldn't be reconstructed in-session. May correlate with one of the variables above.
5. **Y ceiling exactness.** Whether absolute Y=50 is a hard threshold or just the highest value tested. Could be a render-cull boundary, a navmesh search radius, or a configured constant we haven't located.

## Implementation state

- **`Transporter.warpPlayer`** — direct setPosition. Works as-documented; visible behavior is "snap to grounded surface at destination XZ" because the controller's grounded-resolve runs on the next tick.
- **`Transporter.dropPlayer`** — implements the off-map prep + drop recipe. **Not deterministic** for the reasons in §"What this rules out" above. The docstring claims a working two-step that empirically doesn't hold across all controller-tick states. Marked as kept in code pending the controller dig; **users should treat the call as experimental** and expect inconsistent fall-vs-snap outcomes.
- **`Map.center` / `Map.point` / `Map.randomPoint`** — coordinate getters; unaffected by this finding. Compose with either `warpPlayer` (always snaps) or `dropPlayer` (sometimes falls, sometimes snaps).

## Open digs

- **Locate the player movement controller's per-tick update function.** Suggested entry points: trace from `RW.Player.entity`'s vtable (RVA `0xf4cc40` for `oCEntity`) for entries that read/write `+0x324` per frame; xref `oCEntity_setPosition` (RVA `0x6ca7f0`) callers to find the controller-side reader; check the player-component graph at `entity+0x5e8` (component hashmap, per `enemy-spawn-architecture.md`) for a movement-controller component class. Once located, hook it as a no-op pass-through to confirm it ticks on input, then explore whether calling it manually from Frida produces the desired tick.
- **Test absolute Y values lower than 50 with off-map prep, while moving.** If the user holds a movement key during the warp pair, the controller is presumably ticking. That should let us A/B the Y threshold cleanly under controlled tick conditions.
- **Pin the off-map threshold.** `(-410, 2, 0)` works; what's the smallest off-map distance that reliably ungrounds? May affect whether the prep is invisible to the user (large off-map = visible camera jump; small off-map = clean).

## Cross-references

- `rw/findings/spawn-at-coord-recipe.md` — primitive (`vtable[+0x50]`, position field at `+0x324`); off-map free-fall observation.
- `rw/findings/transporter-placement-primitive.md` — placement primitive on encyclopedia map landmarks.
- `tools/frida/mods/powers/Transporter.js` — current implementation of warp / drop.
- `tools/frida/util/EntitySpawners.js` — shared spawner-ctor capture util introduced this session (independent of this finding but relevant to the broader Map / Hourglass / SpawnerProbe consolidation arc).
