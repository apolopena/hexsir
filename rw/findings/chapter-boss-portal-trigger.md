[← Back to findings](README.md)

# Chapter boss-arrival trigger — force the portal on demand

**Status:** confirmed
**Created:** 2026-05-03
**Verified:** 2026-05-03 (in-game, full success)

## Sources

- `Ravenswatch.exe` (Ghidra MCP — function decompile + byte-pattern hash xrefs)
- `rw/findings/save-mint-status.md` — context on save scarcity (saves only emit on chapter-boss kills)
- `CLAUDE.md` "Saves are only generated at chapter-boss kills" rule

## Goal

Reduce the iteration time on save-edit experiments. Per CLAUDE.md, the engine only writes a new `Profile_1.ob` on chapter-boss kill; there's no autosave/quicksave/save-on-quit/save-on-death. A new chapter-boss kill is ~20 minutes of focused play. If we can force the boss-arrival ("Boss time start") event on demand from Frida, the kill itself takes seconds and end-of-chapter testing collapses from minutes to seconds.

## Verdict — short version

**Confirmed end-to-end in-game 2026-05-03.** Single Frida write of `*(float*)(boss_timer + 0x12c) = *(float*)(boss_timer + 0x144)` — the engine's own per-frame Update fires named event `0x17d8d901` ("Boss time start" / "Triggered when boss awakens") on the next frame, and existing subscribers spawn the boss arena exactly as if the player had played the full ~21 minutes. End-of-chapter testing collapses from ~20 min to seconds. Mechanism is fully understood and trivially Frida-triggerable. The chapter-end boss timer is a per-frame Update on a single entity (the BossTimer). When `elapsed >= boss_time_budget`, the engine sets `is_boss_awaken = 1` and fires named event `0x17d8d901` ("Boss time start" / "Triggered when boss awakens"). Subscribers to that event do the actual portal-spawn / boss-arrival content work.

To trigger on demand: hook `BossTimer_update` at `image+0x1e9d50`, capture the `param_1` pointer (the BossTimer instance), and provide a REPL command that writes `*(float*)(timer + 0x12c) = *(float*)(timer + 0x144)` (elapsed = boss_time). On the next frame, the engine's own logic fires the same event as if the player played the full 20 minutes. **No need to reverse-engineer the spawn pipeline at all** — the engine fires its event, its subscribers spawn the content.

## Trigger architecture

Three boss-timer functions form the subsystem (all renamed in Ghidra):

| Function | RVA | Role |
|---|---|---|
| `BossTimer_update` (was `FUN_1401e9d50`) | `0x1e9d50` | Per-frame Update; ticks elapsed time, fires the three named events at threshold crossings, sets `is_boss_awaken` flag. |
| `BossTimer_publish_state_to_property_bag` (was `FUN_1401ea2b0`) | `0x1ea2b0` | Called from end of `BossTimer_update`; mirrors all timer state into the modifier-stat property bag using the registered hashes. Read-only mirror of the source-of-truth fields on the BossTimer instance. |
| `BossTimer_register_stats_and_events` (was `FUN_1401eab90`) | `0x1eab90` | Init-time registration of the modifier stats + named events listed below. |

Plus 4 helpers that call `BossTimer_publish_state_to_property_bag` (likely state-machine transition handlers): `FUN_1401e8d90`, `FUN_1401eaad0`, `FUN_1401ea750`, `FUN_1401ea6a0`. Not yet decoded individually.

### Named events fired by `BossTimer_update`

Each event is fired exactly once when its threshold is crossed (edge-triggered):

| Hash | Name (registered string) | Description string | Trigger condition |
|---|---|---|---|
| `0x17d8d900` | "Boss warning start" | "Triggered Y seconds before boss time, indicating it start awakening" | `elapsed >= boss_time - warn_offset (+0xbc)` |
| `0x1cd7928b` | "Boss overtime start" | (none observed in this dig) | `elapsed >= boss_time - overtime_offset (+0xc0)` |
| `0x17d8d901` | "Boss time start" | "Triggered when boss awakens" | `elapsed >= boss_time` — **THIS IS THE ARRIVAL EVENT** |

The fire path: `fire_named_event(scene_context_at +0x90, hash, [1.0])` — i.e., dispatched through the same named-event substrate used elsewhere in the codebase (e.g., the picker proposes events).

### BossTimer instance field map

Inferred from `BossTimer_update` and `BossTimer_publish_state_to_property_bag`:

| Offset | Type | Meaning |
|---|---|---|
| `+0x88`  | ptr   | scene context (modifier-stat property bag) — written each frame by `BossTimer_publish_state_to_property_bag` |
| `+0x90`  | ptr   | scene context for `fire_named_event` |
| `+0xac`  | float | day duration (seconds) |
| `+0xb0`  | float | night duration (seconds) |
| `+0xb4`  | float | extra timing field (published as `0x17d8d8a0`) |
| `+0xb8`  | int   | boss-arrival mode enabled (must be non-zero for boss-arrival logic to run) |
| `+0xbc`  | float | warning offset (sec before boss_time at which "warning" event fires) |
| `+0xc0`  | float | overtime offset (sec before boss_time at which "overtime" event fires) |
| `+0x129` | byte  | timer-enabled gate (Update no-ops if false) |
| `+0x12c` | float | **`elapsed` — total time progressed in current chapter (seconds)** |
| `+0x130` | float | speed multiplier applied to dt each frame |
| `+0x134` | byte  | day/night phase indicator (used for property-bag `0x17d8d89b/c` booleans) |
| `+0x138` | int   | half-cycle counter (incremented when phase timer expires) |
| `+0x13c` | float | current phase remaining (counts down each frame; on hitting 0, advance phase) |
| `+0x144` | float | **`boss_time` — total budget; when `elapsed >= boss_time`, boss awakens** |
| `+0x148` | byte  | **`is_boss_awaken` — set to 1 by Update when threshold crossed** |
| `+0x149` | byte  | `is_in_overtime` |
| `+0x14a` | byte  | "boss-just-awoke" pending flag (consumed by sibling state-handler) |
| `+0x14b` | byte  | boss-disabled / endless-mode flag |
| `+0x14c, +0x14d` | byte | other gates that pause cycle progression |

### Update logic in C-pseudo

```c
void BossTimer_update(BossTimer *this, float dt) {
    if (!this->timer_enabled || !this->plVar2_runtime_check())  return;

    this->elapsed += dt * this->speed_multiplier;     // +0x12c

    if (this->is_boss_awaken)  goto tail;             // +0x148

    // Cycle phase progression (+0x13c, +0x138, +0x134)
    if (!this->phase_paused_a && !this->phase_paused_b) {
        this->phase_remaining -= dt;
        if (this->phase_remaining <= 0) {
            this->cycle_count++;
            this->advance_phase();                    // FUN_1401c9440
            this->phase_remaining = (new phase duration);
        }
    }

    // Boss-arrival ladder
    if (this->boss_arrival_enabled && !this->boss_disabled) {
        // 1. Overtime threshold
        if (boss_time - elapsed_old > overtime_offset && boss_time - elapsed <= overtime_offset)
            fire_named_event(scene, 0x1cd7928b, [1.0]);

        // 2. Warning threshold
        if (boss_time - elapsed_old > warn_offset && boss_time - elapsed <= warn_offset)
            fire_named_event(scene, 0x17d8d900, [1.0]);

        // 3. THE BOSS-ARRIVAL TRIGGER
        if (this->elapsed >= this->boss_time) {
            this->is_boss_awaken = 1;
            this->boss_just_awoke = 1;
            fire_named_event(scene, 0x17d8d901, [1.0]);   // ← portal/arena spawn fires here
        }
    }

  tail:
    BossTimer_publish_state_to_property_bag(this);
}
```

## Frida trigger — proposed harness

This is **not yet implemented** — the field map and event hashes above are sufficient to write it; the work is mechanical.

Proposed REPL commands in `tools/frida/rw_lab.js`:

```js
// On first BossTimer_update entry, capture the instance pointer.
let bossTimerInstance = null;
Interceptor.attach(Module.findBaseAddress('Ravenswatch.exe').add(0x1e9d50), {
    onEnter(args) {
        if (!bossTimerInstance) {
            bossTimerInstance = args[0];
            console.log('[BossTimer] captured instance @', bossTimerInstance);
        }
    }
});

// REPL: forceBossSpawn() — write elapsed = boss_time. Next frame fires 0x17d8d901.
function forceBossSpawn() {
    if (!bossTimerInstance) { console.log('not captured yet — wait for first update tick'); return; }
    const elapsed_ptr = bossTimerInstance.add(0x12c);
    const boss_time_ptr = bossTimerInstance.add(0x144);
    const boss_time = boss_time_ptr.readFloat();
    elapsed_ptr.writeFloat(boss_time);
    console.log('[BossTimer] forced elapsed = boss_time =', boss_time);
}

// REPL: bossTimerStatus() — dump current timer state.
function bossTimerStatus() {
    if (!bossTimerInstance) { console.log('not captured'); return; }
    const t = bossTimerInstance;
    console.log('elapsed:        ', t.add(0x12c).readFloat());
    console.log('boss_time:      ', t.add(0x144).readFloat());
    console.log('warn_offset:    ', t.add(0xbc).readFloat());
    console.log('overtime_offset:', t.add(0xc0).readFloat());
    console.log('cycle_count:    ', t.add(0x138).readInt());
    console.log('is_boss_awaken: ', t.add(0x148).readU8());
    console.log('arrival_enabled:', t.add(0xb8).readInt());
    console.log('boss_disabled:  ', t.add(0x14b).readU8());
}
```

**Verification result (2026-05-03):**

Test save: `rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob` (chapter-3 proof, then started fresh chapter from hub).

`bossTimerStatus()` at T+43s of chapter play, before forcing:

```
[BOSS-TIMER] instance=0x1eb0c96a590 elapsed=3.05 boss_time=1260.00 remaining=1256.95s
             speedMult=1.00 warnOff=60.00 overtimeOff=180.00
[BOSS-TIMER] phase=1 phaseRemaining=86.95 cycleCount=0 dayDur=180.00 nightDur=180.00
             arrivalEnabled=6 timerEnabled=1 isAwaken=0 isOvertime=0 isDisabled=0
```

Confirms: 21-minute chapter budget (`boss_time=1260s`), 3-minute day + 3-minute night cycles, 60s warning offset, 180s overtime offset, `arrivalEnabled` non-zero, `isAwaken=0`. `arrivalEnabled` is an int, not a strict bool — the value `6` here works fine; non-zero is the gate.

`forceBossSpawn()` written; on the next frame the engine fired all three threshold events (overtime, warning, awakening — all crossed simultaneously since elapsed jumped from 3.05 to 1260), and the boss-arrival content spawned identically to natural progression. Killing the boss produced the normal chapter-end save dialog. **Full success — proof save scarcity is dead.**

## Why this is much faster than alternatives

- **Save-edit alone can't do this.** Per `random-seed-system.md`, the BossTimer's runtime state (elapsed, is_boss_awaken) is not save-resident — `BossTimer_publish_state_to_property_bag` writes to the modifier-stat property bag every frame, not to disk. The state lives in process memory only.
- **Reverse-engineering the spawn pipeline is unnecessary.** The clean intercept is one frame upstream of the spawn — at the engine's own decision point. Whatever the spawn does (portal entity, scene transition, post-arrival cinematic, etc.) executes via the engine's own code path, identical to natural progression. We don't risk drifting from "real" boss-arrival behavior.
- **No state corruption risk.** We're using the engine's own write path. The only operation is a single float write to a runtime field that's already advanced every frame. The engine reads it on the next frame and proceeds normally.

## Annotations applied this session

Renames in Ghidra (committed via `mcp__ghidra__rename_symbol`):

- `FUN_1401e9d50` → `BossTimer_update`
- `FUN_1401ea2b0` → `BossTimer_publish_state_to_property_bag`
- `FUN_1401eab90` → `BossTimer_register_stats_and_events`

Plate comments added at:

- `0x1401e9d50` — Update structure, the three threshold-crossing fire sites, and the Frida-trigger one-liner recipe.
- `0x1401ea2b0` — full property-bag-hash → field map (modifier stats published every frame).

## Unresolved / next steps

- **Identify the BossTimer's owner class.** `oCDtBossTimerUiControllerEntityCpnt` is the UI mirror; the actual stateful BossTimer entity is a different (currently unnamed) entity component. Cosmetic only — instance capture via the Update hook works regardless.
- **Cross-chapter generality.** Verified on chapter-3 only. The harness captures `args[0]` on every Update tick, so chapter transitions should auto-refresh the instance — but that hasn't been exercised yet. Worth a sanity pass on chapter-1 and chapter-2 once another save-edit experiment naturally exercises a different chapter.
- **Identify subscribers to `0x17d8d901`** (the actual portal/boss-spawn code). Not required for the trigger goal but would be useful for any future "spawn boss elsewhere" or "spawn the alternative boss" experiments.
- **Decode the 4 helper functions** that call `BossTimer_publish_state_to_property_bag` (`FUN_1401e8d90`, `FUN_1401eaad0`, `FUN_1401ea750`, `FUN_1401ea6a0`). Likely state-machine transitions (init, pause, resume, end-of-chapter). Not blocking anything.
- **`bossTimerSetElapsed(seconds)` for warning/overtime testing.** Implemented in the harness but not yet exercised. Setting elapsed to `boss_time - 65` should fire only the warning event (`0x17d8d900`); to `boss_time - 200` should fire only the overtime event. Useful as a discriminator if a future bug produces only one of the three threshold-crossing events.

## Notes on methodology

This dig started from the (unproductive) hypothesis that the trigger would be portal-named. No "Portal" string exists in the binary; the engine uses the day/night-cycle terminology ("Boss awakens", "cycles before awakening") instead. Lesson: when in-engine terminology fails, search for *gameplay-state* nouns ("Boss", "Awaken", "Cycle") rather than assumed implementation nouns. The chain string-search → modifier-stat hash registration → byte-pattern xref of the registered hashes was the same pattern that cracked the talent picker — re-applicable for any "find the function that writes/reads stat X" question.
