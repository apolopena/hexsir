[← Back to findings](README.md)

# Wandering camps — anchor decoupled from enemies

**Status:** in-progress
**Created:** 2026-05-11

Player-observed: walking into a "wandering camp" location reveals no enemies, while walking into a typical (standard) camp does. Static analysis attributes this to a `CampType` enum distinction in the engine — wandering camps decouple the anchor from its enemy roster, so the enemies aren't co-located with the anchor at visit time.

## Sources

- `Ravenswatch.exe` Ghidra reads, 2026-05-11 — `CampType` enum-display-name table at `0x140eee8d0..0x140eee900` (`Standard camp`, `None`, `Sandman`, `Wandering camp`). No direct xref (string-pool-indexed access).
- User-observed runtime behavior — wandering camps appear empty on visit; standard hog camps do not.
- `rw/findings/dormant-entity-activation-wall.md` — context on the chapter-init-ctor / streaming-grid-activation model that this finding refines.
- `tools/frida/mods/poc_warp_enemy.js` — the mod that surfaces the issue (its `summon` flow scans active entities within a radius of the camp anchor, which fails when enemies aren't near the anchor).

## TL;DR

- Camps are typed via a **`CampType` enum** with at least four values: `Standard camp`, `None`, `Sandman`, `Wandering camp`.
- Standard camps ctor their enemies at chapter init **at the camp's tile-cell position**. The enemies sit dormant in that cell until the streaming grid activates them on player proximity. Walk in → cell activates → enemies engage.
- Wandering camps still ctor their enemies at chapter init (they show up in our `Warp._byName` capture), but the enemies are **not bound to the camp's static position**. They are driven by a wander/patrol AI state that paths them around the chapter map independently of the anchor.
- By the time the player visits a wandering camp's anchor, the enemies have likely pathed away. They're alive, active, and somewhere else — just not in the anchor's cell.

## Confirmed Findings

### 1. `CampType` enum exists

String-pool block at `0x140eee8d0..0x140eee900`:

```
140eee8d0  53 74 61 6e 64 61 72 64  20 63 61 6d 70 00 00 00  |Standard camp...|
140eee8e0  4e 6f 6e 65 00 00 00 00  53 61 6e 64 6d 61 6e 00  |None....Sandman.|
140eee8f0  57 61 6e 64 65 72 69 6e  67 20 63 61 6d 70 00 00  |Wandering camp..|
```

Layout: tight enum-display strings, fixed-width 16-byte slots, packed contiguously. Adjacency strongly suggests these are the four values of a single `CampType` enum (or similar — `CampCategory`, `CampBehavior`).

### 2. Standard vs. wandering — model

| Aspect | Standard camp | Wandering camp |
|---|---|---|
| Anchor position | Fixed at the camp's tile cell | Fixed at the camp's tile cell |
| Enemies ctored at chapter init? | Yes | Yes |
| Enemies bound to anchor position? | Yes (sit at camp coords until activated) | No (independent wander AI from the start) |
| Enemy state until player proximity | Dormant in anchor's cell | Already active and pathing, in some other cell |
| What player sees on first visit | Cell activates → enemies engage | Anchor location appears empty |
| Where the enemies are | At the anchor | Anywhere along their wander route |

### 3. Practical impact on `Warp` mod

`Warp.summon(campSubstr, filter)` finds the named camp anchor, warps the player to it, waits N seconds for the cell to activate, then `scanActive(radius=15)` captures enemies near the player. For wandering camps this is structurally wrong:

- The anchor is reachable by name search.
- Cell-activation on the anchor does nothing useful — enemies that belong to that camp are not in this cell.
- `scanActive` from the anchor finds nothing.

A correct wandering-camp summon would look up enemies **by camp-membership** (not by spatial scan) and warp them by name from the captured `_byName` map. The capture is already present; only the lookup-by-camp step is missing.

## Unresolved

### A. Confirm the model by live capture

Locate a wandering-camp anchor entity. Iterate its expected enemy roster (e.g., `Standard_Undead_Hog_*` names known to belong to wandering hog camps). Check `+0x324` positions: do they cluster (single wander group, all near each other but far from the anchor) or scatter (independent per-enemy AI, broadly distributed)? Either supports the model; the difference matters for how to formulate a "wandering" lookup.

### B. Find `CampType` field offset on settings

Need: the settings-asset offset that stores `CampType` for a camp anchor. Approach: xref the enum-name strings or find a typedesc that exposes `CampType` as a field. So far the strings have no direct code refs — the field is likely accessed via offset + enum-id, with display name resolved by indexing into the string block at runtime.

### C. Find the wander-AI controller class

The component (or behavior-tree node) that drives wander/patrol movement for the camp's enemies. Probably distinct from the EntitySpawner that owns standard-camp enemies. Likely surfaces as an `oCEntityCpnt*` class or an AI-state class. Candidates to grep: "Wander", "Patrol", "Roam", "Path", "AI", "Behavior".

### D. Implication for "summon any enemy" goal

If wandering-camp enemies use the same `oCEntityCpntCollisionGpn` dynamic body as standard-camp activated enemies (likely yes — they're active enemies, just not at the camp), then warping a wandering enemy to the player should work cleanly without the "invisible mesh" / rendering-cell issue documented in `dormant-entity-activation-wall.md` §"Renderer". The leash issue may still apply if wander AI has a route-anchor reference distinct from `+0x2e0`. Untested.

## Cross-references

- `rw/findings/dormant-entity-activation-wall.md` — parent context (streaming-grid model, collision-volume identification, leash unknown)
- `rw/findings/entity-spawner-mechanism.md` — how the camp anchor's EntitySpawner component holds the child enemy list
- `rw/findings/enemy-entity-list.md` — chapter-1 enemy catalog
- `tools/frida/mods/poc_warp_enemy.js` — the mod whose `summon` flow surfaces the issue
