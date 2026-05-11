[← Back to findings](README.md)

# Held Dream Shards — bytefield reference

**Status:** confirmed
**Status notes:** active reference. Verified in lab 2026-05-01.
**Field:** `oCDtEntityCpntHeroControllerPersistentData` (HC) body, offset `+0x1D`, **float32 LE** (byte-misaligned).

The HUD-displayed Dream Shards spendable count. Authoritative direct-read field — the HUD reads this value verbatim and does **not** recompute it from `earned − spent`.

## Sources

- pre-policy — written before the Sources header was mandatory.

## Storage

| Property | Value |
|---|---|
| Containing class | `oCDtEntityCpntHeroControllerPersistentData` (single instance per save) |
| Body offset | `+0x1D` |
| Width / type | 4 bytes, float32 little-endian |
| Alignment | byte-misaligned (offset is odd; not 4-aligned) |
| Front-anchored | Yes — same offset across all chapters (verified ch2 / ch3 / epilogue) |

The walker `lib/hc_walker.py` exposes this as the `held_dream_shards` field.

## Adjacent fields in the per-run float block

The four floats at HC body `+0x11`, `+0x15`, `+0x19`, `+0x1D` form one contiguous run-state block, zeroed wholesale by mint:

| Offset | Walker name | Meaning |
|---|---|---|
| +0x11 | `damage_float_1` | Per-run damage stat (likely damage dealt; not yet rigorously confirmed) |
| +0x15 | `damage_float_2` | Per-run damage stat (likely damage taken; not yet rigorously confirmed) |
| +0x19 | `dream_shards_earned` | Total Dream Shards earned this run (= held + dream_shards_spent) |
| +0x1D | `held_dream_shards` | **This field.** HUD spendable count. |

The related `dream_shards_spent` (Dream Shards already spent at the dream tree) lives further into the HC body at a chapter-shifting offset (`+0x35D` ch2, `+0x65D` ch3, `+0x79D` epilogue) past the HeroIngredient vector, HMO vector, and three guid16 vectors. Resolved dynamically by the walker as `dream_shards_spent`.

## Cross-check with adjacent fields

In observed saves the relationship `held = earned − dream_shards_spent` holds:

| Save | Held (+0x1D) | Earned (+0x19) | Spent (dynamic) |
|---|---:|---:|---:|
| `proofs/geppetto/chapter2/laser-lenses_1` | 101.0 | 1091.0 | 990.0 |
| `proofs/geppetto/chapter3/laser_lenses_1` | 21.0  | 2041.0 | 2020.0 |

**This is not an invariant the game enforces on load.** The HUD reads `+0x1D` directly. Editing only `+0x1D` changes the displayed spendable count even when earned and spent disagree. Verified in lab `held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof`: golden source had earned=0 / spent=0 / held=0; we patched held=99.0 only; HUD on load showed **99**.

If you also care about score-page consistency or end-of-run conversion to Stars of Fate, edit earned and spent to match.

## Editing

Set held shards directly:

```bash
rerw write savefile shards <float> --source <save> --dest <dir>
```

Programmatically:

```python
from lib import cooked
from lib.setters import set_held_dream_shards

cf = cooked.parse_file(open(src,'rb').read())
old = set_held_dream_shards(cf, 50.0)
open(dst,'wb').write(cooked.encode_file(cf))   # auto-recomputes CRC32
```

Mint zeros this field along with the rest of the per-run float block (via `setters.zero_per_run_damage`).

## Verification source

Lab promotion record: `rw/saves/edits/golden/geppetto/chapter1/held-shards-99__from-mint__from-chapter3-laser_lenses_1-proof/info.md`.

## Runtime memory layout (added 2026-05-04)

The save-file offset `+0x1D` is byte-packed (no padding). The **runtime in-memory** layout is different — the field lives at `HC + 0x1590` as a 4-aligned float32. This was found by decompiling `HC_change_dream_shards` (image+0x38c2b0) and verified live: a single `Memory.writeFloat` to `HC+0x1590` updates the in-game HUD shard counter in real time.

The canonical engine function for adjusting shards is:

```c
HC_change_dream_shards(HC*, float delta, oCCustomFlagList *src)
```

It writes `HC+0x1590 = max(0, current + delta)`, mirrors to `*(HC+0x1d48)`, fires `0x12e831f3` (gain) or `0x12e831f4` (loss) named events, fires global-value event `0x171c27b5`, and runs the subscriber list at `HC+0x15d8`. All 8 shard-source code paths (pickup, store, sandman, boss reward, sell, damage-loss, etc.) call this single function. Full plate comment in Ghidra at `0x14038c2b0`.

HC body runtime field map (4-aligned, distinct from the save-file byte-packed offsets above):

| Runtime offset | Field |
|---|---|
| `+0x1590` | held_dream_shards (float32, source of truth) ★ |
| `+0x1594` | animated/displayed value — lerps toward `+0x1590` over multiple frames |
| `+0x1598` | lerp speed (multiplied by deltaTime each frame) |
| `+0x15b8` | subscriber list head — field-change dispatch (fires on per-frame watcher detect) ★ |
| `+0x15d8` | subscriber list head — canonical-setter dispatch (fires from `HC_change_dream_shards`) |
| `+0x1d48` | stat tracker A* (cumulative-earned/spent mirror) |
| `+0x1d78` | stat tracker B* (per-run, may be NULL) |

### Per-frame watcher pattern

`HC_per_frame_update` (image+0x38e260, renamed in Ghidra from `FUN_14038e260`) is HC's per-frame Update method. It iterates all active HCs and on each performs (among other tick work) a field-change watcher for held_shards:

```c
fVar19 = HC[+0x1594];   // cached/animated value
fVar2  = HC[+0x1590];   // current actual
if (fVar19 != fVar2) {
    // lerp HC[+0x1594] toward HC[+0x1590] using HC[+0x1598] * deltaTime
}
dispatch_event_with_swap_remove(HC+0x15b8, (int)fVar19);
```

This is the BossTimer-equivalent pattern (`BossTimer_update` watching `elapsed` vs `boss_time`). **The watcher fires regardless of who wrote `+0x1590`** — natural code path or Frida raw write.

Implication: a raw `+0x1590` write does NOT trigger the named-event chain (`fire_named_event(scene, 0x12e831f3, &delta)` for GAIN_DREAM_SHARDS) which is reserved for the canonical setter. But it DOES trigger the per-frame field-change watcher's subscriber list at `+0x15b8`. Different subscribers fire on each:

- **Field-change subscribers (+0x15b8):** HUD smooth-interpolation, likely `ReplicaManager3` per-field replication. **Fires from raw write.**
- **Canonical-setter subscribers (+0x15d8) and named-event subscribers (`GAIN_DREAM_SHARDS` hash):** Hope Diamond bonus, Heal-on-gain, achievement counters, analytics. **Does NOT fire from raw write.** Requires the canonical setter `HC_change_dream_shards` to be invoked.

So `gainShards()` (path A, raw write) is enough for: HUD, peer replication in MP (subject to verification — see `multiplayer-host-authority.md`). It is NOT enough for: modifier ticks that subscribe to GAIN_DREAM_SHARDS event.

Live capture of HC during a chapter-2 Geppetto session:

```
[SHARDS] HC=0x11d61d4b1f8  held(+0x1590)=132.00  ratio(+0x1598)=42.4497  trkA=0x11d42f5e8f0 (*=132.00)  trkB=0x11cf0aca430
```

`trkA`'s first float at `*` mirrors held — confirming the engine's own `*(HC+0x1d48) = held` redundancy.

### Frida helpers

`tools/frida/rw_lab.js` exposes:

- `shardsHc()` — return live HC pointer (or null if not yet captured).
- `shardsStatus()` — dump held + ratio + tracker pointers.
- `gainShards(delta)` — write `HC+0x1590 += delta`. **Real-time HUD update verified.**

HC capture is reactive (entry hook on `HC_change_dream_shards`), so workflow is: launch game → load proof → trigger any natural shard event (enemy kill, crystal break, etc.) so the hook fires once → `shardsStatus()` to confirm → `gainShards(N)`. A startup-time heap scan would let users skip the priming step but is not yet implemented.

### What direct write does NOT cover

Path A (raw `+0x1590` write) skips the engine's natural event chain. Things bypassed:

- **Stat tracker mirrors** at `*(HC+0x1d48)+0x10` and `*(HC+0x1d78)+0xf4` (cumulative-earned counters). These re-sync on the next natural shard event but stay stale until then.
- **Subscriber loop at `HC+0x15d8`** — modifier ticks (Hope Diamond bonus, Heal-on-gain, Sandman price-modifiers) don't fire on a raw write.
- **`ReplicaManager3` propagation** in MP — peers' HUDs likely do not update when host writes raw. Untested as of 2026-05-04.

If those side effects matter, escalate to calling `HC_change_dream_shards(HC, delta, src_flags)` via `Frida NativeFunction`. The `src_flags` argument is an `oCCustomFlagList*` — passing NULL crashes on the unconditional `FUN_140651ec0` call. To wire safely, cache `args[2]` from the entry hook on a real shard event and reuse the captured pointer.

Cross-reference: `multiplayer-host-authority.md` covers the broader MP architecture and the rationale for the path-A vs. path-B distinction.

## Related

- `multiplayer-host-authority.md` — runtime architecture of shard gain in P2P MP, the canonical-function dig that produced the `+0x1590` finding.
- `save-edit-pipeline.md` — full HC body schema and the broader save-edit pipeline.
- `tools/rerw-src/lib/hc_walker.py` — runtime walker exposing `held_dream_shards`, `dream_shards_earned`, `dream_shards_spent`.
- `tools/rerw-src/lib/setters.py` — `set_held_dream_shards` setter and `zero_per_run_damage` zeroer used by mint.
- `tools/frida/rw_lab.js` — runtime hook + helpers (`shardsHc`, `shardsStatus`, `gainShards`).

## Locating these structures on a new build

Per `rw/docs/README.md` §"Locating <thing>" — both flavors apply: byte-stream for save-side fields, RE-side for the runtime HC offset.

### Save-side anchors (byte-stream)

| Structure | Anchor |
|---|---|
| `held_dream_shards` field in HC body | `tools/rerw-src/lib/hc_walker.py` walks the HC record by structural offsets. Re-derive from `save-edit-pipeline.md` §"Decoded class schemas" if offsets shift. |
| `dream_shards_earned` / `dream_shards_spent` cumulative fields | Sibling offsets within HC; same walker. |

### Runtime-side anchors (RE-side)

| Symbol | Anchor |
|---|---|
| `HC+0x1590` (raw shard wallet at runtime) | xrefs from `HC_change_dream_shards` (the canonical write path). See `multiplayer-host-authority.md` for re-discovery. |
| `HC_change_dream_shards` | 3-arg signature `(HC*, int, oCCustomFlagList*)`; xrefs from natural shard-gain UI events. |

### Assumptions

- HC body record layout stable across patch builds (verified to date).
- Runtime `HC+0x1590` offset stable; re-derive via `HC_change_dream_shards` decompile if engine refactors HC.

### Known failure modes

- **HC schema upgrade.** If the engine adds HC fields, downstream offsets shift. Re-derive the full HC schema via `save-edit-pipeline.md` and `hc_walker.py`.
- **Save-format upgrade.** Inherits from `save-binary-format.md` failure modes.

### Cross-finding anchoring

Inherits from `save-binary-format.md` (record framing), `save-edit-pipeline.md` (HC schema), `multiplayer-host-authority.md` (runtime HC offsets and shard-gain flow).
