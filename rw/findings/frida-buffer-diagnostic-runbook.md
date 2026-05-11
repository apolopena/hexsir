[← Back to findings](README.md)

# Frida buffer-diagnostic runbook

**Type:** operational runbook (not a findings doc — keep open during the test).
**Companion to:** [`frida-pipeline-hardware-breakpoint.md`](frida-pipeline-hardware-breakpoint.md).
**Created:** 2026-05-04.

## What this tests

Whether the save buffer at `data_source+0x1948` is populated **incrementally** during gameplay (many small `oCMemoryBinaryStream::Write` calls per state change) or **all at once** during Save-and-Quit. Outcome decides whether mid-run Frida saves are achievable.

Approx **20 minutes** of focused chapter-1 play. Single chapter run. No replay needed.

## Pre-flight

- Steam-installed Ravenswatch running.
- Frida set up per CLAUDE.md "Frida: WSL → Windows interop workflow".
- Log file path: `C:\Users\KidSqid\AppData\Local\Temp\frida_seed_diag.log` (referred to below as "the log").

## Step-by-step

1. **Launch & attach.**
   - Start Ravenswatch, get to the main menu.
   - In WSL: launch Frida with `tools/frida/rw_lab.js`. Confirm `[diag] ready.` line in the REPL banner.

2. **Start a chapter-1 run.**
   - Pick character → Play → enter chapter 1.
   - Wait until you have full control (player is in the first room, can move).

3. **Cache the buffer.**
   - In the Frida REPL: `findSaveBuffer()`
   - Wait for the result. You should see:
     ```
     [findSaveBuffer] cached data_source = 0x...
     ```
   - **If it says "MULTIPLE candidates" or "no oCDtRootGs found":** stop and report back. Don't continue the run.

4. **Take checkpoint #1.**
   - `logSaveBuffer("chapter1-start")`
   - Look for `[BUFFER/chapter1-start]` line in the log. Confirm `size=N` shows a number (could be 0, that's fine).

5. **Play room 1 to completion** (kill all enemies, exit room).
   - After the room-clear screen but before entering room 2:
   - `logSaveBuffer("chapter1-room1-clear")`

6. **Continue through 2–3 more rooms.**
   - After at least one shop and one combat room:
   - `logSaveBuffer("chapter1-mid")`

7. **Reach the boss room. DO NOT enter yet.**
   - Standing right at the boss-room door:
   - `logSaveBuffer("chapter1-pre-boss")`

8. **Fight & kill the boss. DO NOT click any save dialog yet.**
   - Boss-die animation is playing or the post-kill chest is open:
   - `logSaveBuffer("chapter1-post-boss")`

9. **Arm the probe.**
   - `probeForBossKillSave()`
   - Confirm you see `=== PROBE-BOSS-KILL-SAVE armed: ... ===` in the log.

10. **Click "Save and Quit" on the modal.**
    - The probe fires once. You should see in the log:
      ```
      [PROBE/sfas] enter session=0x...
      [PROBE/sfas]/buffer ds=0x... bufPtr=... size=N capacity=N pend=N done=N result=0x0 flag=0
      [PROBE/sfas] session+0xa5 (saves-enabled gate) = 0x1
      ...
      ```

11. **Game exits. Don't relaunch.**
    - Quit Frida.
    - Capture the log contents.

## Captured time series — 6 lines expected

The relevant lines look like this:

```
[T+...] [BUFFER/chapter1-start]       ds=0x... bufPtr=0x... size=N1 capacity=...
[T+...] [BUFFER/chapter1-room1-clear] ds=0x... bufPtr=0x... size=N2 capacity=...
[T+...] [BUFFER/chapter1-mid]         ds=0x... bufPtr=0x... size=N3 capacity=...
[T+...] [BUFFER/chapter1-pre-boss]    ds=0x... bufPtr=0x... size=N4 capacity=...
[T+...] [BUFFER/chapter1-post-boss]   ds=0x... bufPtr=0x... size=N5 capacity=...
[T+...] [PROBE/sfas]/buffer           ds=0x... bufPtr=0x... size=N6 capacity=...
```

Compare `N1 → N6`.

## Interpretation

| Pattern in the `size` field | Verdict | Implication |
|---|---|---|
| Monotonic growth start→post-boss (`N1 < N2 < N3 < N4 < N5`), probe matches `N5` | **Incremental** | Mid-run Frida saves are fundamentally impossible. Pivot Frida focus to runtime patches that influence naturally-triggered saves. |
| Near-zero or constant until probe (`N1 ≈ N2 ≈ N3 ≈ N4 ≈ N5`, then `N6 ≫ N5`) | **Single serializer** | A single big serialize call exists inside `session_finalize_and_save`. Hook the call site (visible via `oCMemoryBinaryStream::Write` xrefs filtered to this `data_source`) and build `saveNow()`. |
| Mostly flat with a big jump at "post-boss" only (`N1 ≈ N2 ≈ N3 ≈ N4 ≪ N5`) | **Hybrid** | Final serializer triggered by boss-kill. Hooking that serializer enables chapter-end Frida saves (which is when you'd want them anyway). |

## Failure modes & response

| Symptom | Action |
|---|---|
| `findSaveBuffer()` reports "MULTIPLE candidates" | Stop. Paste the candidate lines back. |
| `logSaveBuffer()` says "read FAIL (heap may have changed)" | Re-run `findSaveBuffer()` once, retry the log. |
| `logSaveBuffer()` says "no cached data_source" | Forgot step 3. Run `findSaveBuffer()` first. |
| `[PROBE/sfas]/buffer no oCDtRootGs found` | Probe-walker missed it. Manual `logSaveBuffer` data still works. |
| `flag=1` on any line | Silencer tripped — save won't fire to disk regardless. Stop and report. |
| Save-Compat modal appears on next launch | Silencer was tripped; future saves silently no-op. Don't keep playing this profile. See `save-silencer-mechanism.md`. |
| Frida REPL eats backslashes when reloading the script | Don't reload from REPL. Exit Frida fully and re-attach. Per CLAUDE.md "Frida: WSL → Windows interop workflow". |

## After the run

Paste the 6 `[BUFFER/...]` + `[PROBE/sfas]/buffer` lines into the "Captured size series" section of [`frida-pipeline-hardware-breakpoint.md`](frida-pipeline-hardware-breakpoint.md) and update its Status field based on the interpretation above.
