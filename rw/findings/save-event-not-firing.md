[← Back to findings](README.md)

> **ARCHIVED 2026-05-03** — save-event subsumed by silencer mechanism.
> Subsumed by [`save-silencer-mechanism.md`](save-silencer-mechanism.md). The boss-kill save-disk-write failure was a manifestation of the save silencer being tripped by malformed ActivityScore deserialization, not an independent failure mode.
> Preserved for historical detail. Some claims here may be stale or contradicted by later work — consult the canonical findings cited above.


# Boss-kill save dialog — disk write not occurring
**Status:** archived


Status: **RESOLVED 2026-04-30 late session via static analysis in Ghidra.**

**See `rw/findings/save-silencer-mechanism.md` for the definitive root cause.**

Summary: edited save files trip `data_source + 0x19ac` (a save-compat severity flag) on load. That triggers registration of a handler that, on the next event-`0x19eadad1` dispatch, sets `data_source + 0x1ef4 = 1`. From that point every save call (run-state and profile, sync and async) silently no-ops with no error or log. Quitting and relaunching is the only way to clear it. Both prior hypotheses (mis-click, game-lies) are subsumed by this structural mechanism. The original triage content below is kept for reference / historical context.

---

## Sources

- pre-policy — written before the Sources header was mandatory.

## Original symptom and hypotheses (now resolved)

## Symptom
Played a chapter-1 → chapter-2 run forward to the boss kill. User reports clicking "save and exit" in the post-boss dialog. Result: game did not exit, and the live `_Save/Profile_1.ob` mtime did not advance — bytes remained the chapter-1 starting golden (`4e0258ee775ba51f...`, mtime Apr 30 21:03).

## Update 2026-04-30 23:21 — Hypothesis 2 evidence

Second playthrough conducted with live mtime watcher (`stat -c %Y` polled 1s, baseline at 23:02:56). User completed run, clicked save-and-exit, game exited per user report. **Watcher logged zero CHANGE events over 18 minutes.** Final state: mtime still `1777608222` (2026-04-30 21:03:42), hash still `4e0258ee775ba51f` — identical to baseline, identical to the chapter-1 starting golden bytes.

The game exited without writing. This is consistent with Hypothesis 2: the save subsystem has a silent failure path that accepts the user input, returns normal control flow (game exits), but produces no disk artifact. Same subsystem fragility as the WinDbg-induced crash, manifesting as a silent no-op when not under a debugger.

Hypothesis 1 not fully ruled out — possible the dialog has a third button that looks like save-and-exit but isn't, and user picked that twice. Mitigation for next attempt: screenshot the dialog before clicking, log button label exactly.

## Two hypotheses, currently indistinguishable

1. **Mis-click**: user clicked "continue" instead of "save and exit." Game continues run in-memory, no disk write, no exit. Plausible but user reports they would not have made this error.
2. **Game lies about save**: clicking save-and-exit produces an acknowledgment but the game never actually writes the file or exits. Possibly related to the WinDbg-during-save crashes previously observed (different failure mode of the same save subsystem). User favors this hypothesis.

Both produce identical observable outcome: file unchanged, game still running (or at least not exited).

## Discriminating test for next playthrough
Before reaching the boss, in a side terminal:
```bash
watch -n 1 'stat -c "%Y %n" /mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save/Profile_1.ob'
```

At the boss-kill dialog, click save-and-exit. Three possible outcomes:

- **mtime ticks AND game exits** → real save fired, `cp` immediately to proofs dir. Hypothesis: neither — system worked.
- **mtime does NOT tick AND game exits** → user picked the wrong button. Hypothesis 1 (mis-click).
- **mtime does NOT tick AND game does NOT exit** → game lied about saving. Hypothesis 2 (game bug). This is the high-value finding if it reproduces — means the save subsystem has a silent failure path.

## Lost-data postmortem
- Pre-21:03: chapter-1 starting golden was the live save bytes
- ~19:50–21:00: user played the round-trip (per their report: collected 2 keys, defeated chapter-2 boss, attempted save)
- 21:03: the live save mtime ticks, but content is still chapter-1 starting golden — meaning whatever wrote at 21:03 wrote those bytes (most likely a `swap savefile` operation putting the starting golden back in place; possibly an agent action, possibly the user verifying something)
- The post-play state never reached disk in any directory. Recycle bin, project tree, and Steam dir all checked.

## Cross-references
- CLAUDE.md "Saves are only generated at chapter-boss kills" — current rule states the trigger but does not document silent-failure mode
- WinDbg deferred (crashes during save) — possibly the same subsystem fragility manifesting differently
