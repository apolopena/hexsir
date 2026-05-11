[← Back to findings](README.md)

# Player setPosition reconciliation — controller-tick coupling and the snap

**Status:** confirmed
**Created:** 2026-05-08
**Last updated:** 2026-05-08 — diff-gate mechanism identified via runtime stack-trace probe; held-position primitive (`Transporter.expr_dropPlayerHard`) confirmed working live.

## Sources

- Live Frida-driven testing 2026-05-08 (chapter-1 / Dark Hills) including `tools/frida/mods/hero_move_probe.js` v0.1.0 stack-trace runs
- Ghidra decompile (this session): `oCEntity_setPosition` (RVA `0x6ca7f0`), `oCEntity_setRotation` (`0x6ca8d0`), `oCEntity_setScale` (`0x6ca9e0`), `oCEntity_VelocityUpdate_loop` (`0x6cce40`), `oCEntity_velocity_update_orchestrator` (`0x6dcc20`), `oCEntityCpntActor_ctor` (`0x39ffa0`), `oCEntityCpntGpnTraverser_ctor` (`0x2e1480`)
- `rw/findings/spawn-at-coord-recipe.md` — `oCEntity_setPosition` primitive; off-map free-fall observation from prior session
- `rw/findings/transporter-placement-primitive.md` — Transporter primitive verified live
- `tools/frida/mods/powers/Transporter.js` v0.7.0 — warp / drop / scale / rotate / expr_dropPlayerHard
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

## Mechanism — confirmed via stack-trace probe (2026-05-08)

The "controller tick" turns out to be the **`oCEntity_VelocityUpdate_loop`** (function entry RVA `0x6cce40`). Identified end-to-end via `tools/frida/mods/hero_move_probe.js` v0.1.0, which hooks `oCEntity_setPosition` with a player-only filter and dumps `Thread.backtrace` on every fire.

**Phase counts (5-second windows):**
- Idle, no input: **0 hits.** Engine does not write the player's position when no input is firing.
- Movement (left stick / W held): **2166 hits**, ~430/sec, ~7 per frame at 60Hz. 100% identical stack pattern across all hits.
- Frida warp + no input: **30 hits.** Resolve cascade fires after the warp, even with no input — engine's response to the position write.
- Frida warp + input held: **1391 hits.** Hit #1 has Frida-trampoline RVAs (high `0x2fa…`); all subsequent hits match the movement pattern. **No separate "snap cascade" code path** — the snap is the velocity-update loop continuing to fire while input is held.

**Movement-tick stack (every hit):**
```
0x6ccff6  in oCEntity_VelocityUpdate_loop (writes setPosition with target)
0x6dcdf5  in oCEntity_velocity_update_orchestrator
0x512ff9  in scheduler step dispatch (FUN_140512eb0)
0x446d15  ↑
0x446451  ↑
0x4461cc  ↑
0x50ec79  ↑
0xdd3ec   game loop / scheduler tick
```

### The diff-gate

`oCEntity_VelocityUpdate_loop` body wraps its setPosition call in a diff-gate:

```c
if (target.x != prev.x || target.y != prev.y || target.z != prev.z) {
    setPosition(entity, target);
}
```

Where:
- `prev`   = `entity+0x3d8..+0x3e0` (3 floats)
- `target` = `entity+0x3e4..+0x3ec` (3 floats)

The loop does **not** compute target — target is written upstream (movement intent / gravity / navmesh-snap producers, not yet fully traced). When player is idle and no upstream writes, target == prev, the loop is silent for that entity.

This explains the input-gating: no input → no upstream velocity producer firing → target stays stale matching prev → loop silent. The "controller is input-gated" model is mechanically: "the producer of `target` is input-gated."

### The hold-without-snap primitive

If we write `prev = target = pos = (x, y, z)` in one Frida turn, the diff-gate reads zero on every subsequent tick and the loop never overwrites the broadcast position field at `+0x324..+0x32c`. Result: player **holds** at any (x, y, z) including high Y, mid-air. Verified live 2026-05-08 with `Transporter.expr_dropPlayerHard(0, 50, 0)` — player hovers at Y=50, untouched, until any input fires (then upstream writes to target re-trigger the loop, which resolves to the navmesh surface — observed as the snap when user clicked attack).

Implementation in `tools/frida/mods/powers/Transporter.js` v0.4.0+: `expr_dropPlayerHard(x, y, z)` writes all three triplets (`prev`, `target`, position) atomically, then calls `setPosition` to broadcast to renderer/camera.

### What this rules out (and replaces)

- "The off-map prep recipe is the path to deterministic drops." → Replaced. The prep + gap recipe is non-deterministic by design (depends on whether controller ticks during the gap, which depends on player input). The diff-gate primitive sidesteps the recipe entirely for the hold case. For a **visible fall** (gravity-driven descent over multiple frames) the recipe is also wrong — what's needed is to clear/seed the upstream gravity input, which we haven't found yet.
- "Holding movement input + a 500ms gap fixes `Transporter.dropPlayer`." → Falsified. Even with input held + 500ms `setTimeout` between the off-map and in-map writes, the snap reproduces (live-tested 2026-05-08). The recipe that "worked" in earlier REPL sessions was timing-dependent on a state we couldn't reproduce.

## Component shapes — entity-side movement state

Two relevant components hung off `entity+0x5e8` (component hashmap, per `enemy-spawn-architecture.md`):

**`oCEntityCpntActor`** — 272 bytes (0x110). Ctor at `oCEntityCpntActor_ctor` (RVA `0x39ffa0`). Field map:
| Offset | Type | Likely role |
|---|---|---|
| +0x00 | vtable (`oCEntityCpntActor::vftable`) | — |
| +0x18 | `EntityCpntValueSignal<bool>` | bool flag #1 (grounded?) |
| +0x38 | `EntityCpntValueSignal<bool>` | bool flag #2 (airborne / moving?) |
| +0x80 | `EntityCpntValueSignal<int>` | state-machine state |
| +0xa0 | `EntityCpntValueSignal<oCVec3>` | vec3 #1 (velocity?) |
| +0xc0 | `EntityCpntValueSignal<oCVec3>` | vec3 #2 (target?) |
| +0xe0..+0x108 | misc | 48 bytes of state |

**`oCEntityCpntGpnTraverser`** — 256 bytes (0x100). Ctor at `oCEntityCpntGpnTraverser_ctor` (RVA `0x2e1480`). Field map:
| Offset | Type | Likely role |
|---|---|---|
| +0x00 | vtable (`oCEntityCpntGpnTraverser::vftable`) | — |
| +0x18 | `EntityCpntValueSignal<bool>` | bool flag #1 |
| +0x38 | `EntityCpntValueSignal<bool>` | bool flag #2 |
| +0xb0 | `oCEntityGpnTesterCombiner::vftable` | navmesh tester combiner — walkability queries |
| +0xe8 | u16 = 0x100 | flags? |

The traverser is the navmesh-side complement to the actor. The "snap to walkable surface" raycast almost certainly originates here. The pair of bool signals on each component is the most likely home for the grounded / airborne / moving flags — pinning which is which requires runtime byte-diffing the components in two known states (grounded standing vs `expr_dropPlayerHard` hovering); not done this session.

## Sibling transform primitives — confirmed working on any oCEntity

While digging this session also confirmed the full vtable transform-primitive set on the base `oCEntity` class:

| RVA | vtable slot | What it writes | Broadcast type |
|---|---|---|---|
| `0x6ca7f0` | `+0x50` | position vec3 at `+0x324..+0x32c` | 0 |
| `0x6ca8d0` | `+0x60` | rotation quat at `+0x308..+0x314` | 1 |
| `0x6ca9e0` | `+0x70` | scale vec3 at `+0x318..+0x320` | 2 |

All three follow the same dirty-flag + queue + broadcast plumbing (`+0x288` flag, `+0x270`/`+0x280` gates, `+0x3a8` handler list). All three work on **any** `oCEntity` — verified live with `Transporter.scalePlayer` (smaller = visibly faster), `Transporter.scaleEntity("noModel+2Cpnt", 3.0)` (hourglass scaled cleanly), and `Transporter.rotatePlayer(45)` (rotates the R-stick aim direction, not the body — the visible body rotation is animation-driven from L-stick velocity, separate path).

`Transporter.js` v0.7.0 surface (committed this session): `warpPlayer` / `dropPlayer` / `scalePlayer` / `rotatePlayer` (one-shot for player); `warpEntity` / `scaleEntity` / `rotateEntity` (with 500ms tick re-apply for non-player entities); `expr_dropPlayerHard` (the diff-gate primitive). Per-entity tick map (`Transporter._entityTicks`) added so re-calling `scaleEntity` / `warpEntity` / `rotateEntity` on the same entity replaces the prior tick instead of stacking loops.

## Open digs

- **Visible-fall variant.** The diff-gate primitive holds; it doesn't drop. For a real engine-driven fall from high Y to ground, we need either (a) the upstream gravity producer (whatever writes `entity+0x3e4..+0x3ec` from current pos + gravity*dt under "airborne" conditions), or (b) the grounded/airborne state flag so we can clear it. The Actor's `+0x18`/`+0x38` bools are the most likely home; runtime byte-diff probe is the cheapest way to identify them.
- **Body-rotation source.** `rotatePlayer` writes the entity's quaternion which controls AIM/R-stick direction, not the visible body facing. The body's render rotation is driven by the animation/movement system from L-stick velocity. Locate that path if you ever want to spin the body without input.
- **Pin the two bool signals on Actor and Traverser.** Each component has two `EntityCpntValueSignal<bool>` slots. Live byte-diff between grounded standing and hovering states would land the grounded bool in one observation. Probe sketch: capture component pointers via `entity+0x5e8` map walk, dump bytes in state A, dump in state B, diff.
- **Component hashmap traversal.** We need a Frida helper that resolves `actor` and `traverser` from a player entity ptr. The hashmap at `entity+0x5e8` is the entry point; the lookup key is the component class type-id (registered in `oCEntityCpntActor_typedesc_init` and `oCEntityCpntGpnTraverser_typedesc_init`).

## Cross-references

- `rw/findings/spawn-at-coord-recipe.md` — primitive (`vtable[+0x50]`, position field at `+0x324`); off-map free-fall observation.
- `rw/findings/transporter-placement-primitive.md` — placement primitive on encyclopedia map landmarks.
- `tools/frida/mods/powers/Transporter.js` — current implementation (v0.7.0) of warp / drop / scale / rotate / expr_dropPlayerHard.
- `tools/frida/mods/hero_move_probe.js` — the stack-trace probe used to identify the velocity-update loop as the per-tick caller.
- `tools/frida/util/EntitySpawners.js` — shared spawner-ctor capture util introduced this session (independent of this finding but relevant to the broader Map / Hourglass / SpawnerProbe consolidation arc).
