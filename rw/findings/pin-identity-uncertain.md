[← Back to findings](README.md)

# Pin Identity: What Are the Pinned Addresses Actually?

**Status:** in-progress
**Created:** 2026-04-26

## Sources

- rw/findings/oe-dynamic-listener-data.md (the doc whose pinned addresses are the subject of this triage)
- rw/findings/live-state-mirror-cascade.md (substantive observations from this session)
- .ai/scratch/postmortem-live-memory-investigation-20260426.md (process critique that prompted this triage)
- Live verification tests run 2026-04-26 against Ravenswatch PID 22768

## Confirmed Findings

### What the pinned addresses are NOT

The pinned addresses in `oe-dynamic-listener-data.md` (HP current, HP max,
Level, XP current, XP threshold, Dream shards listener, Stars of Fate
plain `int32`) are **not** the live source-of-truth for their associated
stats. Verified by:

- Game-driven trigger events (took damage, leveled up 5→6, spent 50 dream
  shards, spent 1 star of fate). In every case the pin held its prior
  value while the HUD displayed the new value.
- External writes (Level pin → 6, then → 10). HUD ignored both writes;
  pin memory held the modified value but the displayed Level remained 5.

The correlation between pin values and HUD values that originally
motivated the pinning workflow holds **only at specific past moments** —
the level-up snaps captured in MAINT-4. Outside those moments the pin
values do not correspond to live state.

### Live mirrors exist but are also not source-of-truth

For dream shards, value-progression scanning (intersect `int32==41` ∩
`int32==91`) returned 28 mirror addresses that *do* track HUD changes
(verified across the 91→41→91 transition). Sentinel writes to all 28
mirrors did not affect HUD. Detailed in
`rw/findings/live-state-mirror-cascade.md`.

## Unresolved

### What ARE the pinned addresses?

Multiple hypotheses fit the observed behaviour. None has been
discriminated from the others.

| Hypothesis | What it would predict | Discriminating test |
|---|---|---|
| Save-buffer mirrors (populated at save events; serializer reads from them) | Modifications written before a save event get overwritten by the engine's save-prep refresh, then the original-canonical value is serialized. Disk shows canonical, not modification. | Write to a pin, complete a chapter, save normally, reload, read pin. Player has predicted this would fail (refresh-then-serialize). Test never run. |
| Save-buffer mirrors (populated *for* save serialization, written by serializer to disk without canonical refresh) | Pre-save modifications persist to disk. Reload shows modification. Pins are a working save-edit surface. | Same test as above. Different prediction. |
| Allocation-time defaults / config copies | Values were set once when the listener was allocated and never refreshed by anything. Match to HUD at MAINT-4 capture moments was coincidental (or capture moments aligned with allocation-affecting events like level-up). | Snapshot pin values across multiple chapter starts of the same character. If they differ from session to session at game-start, this hypothesis is weakened. |
| Dead code / unused subsystem buffers | Allocated and updated by a subsystem the running game doesn't engage (network replication for an unused multiplayer mode, debug logging compiled out, achievement telemetry, a shipped-but-unwired feature). | Static analysis: find which functions write to these listener vtables in the EXE binary. If callers are in unreachable / disabled code paths, this hypothesis is strengthened. |
| Something else (UI cache, animation hint, save-game-list cache, ...) | Variable | Per-hypothesis structural inspection of the surrounding heap allocations. |

The most-natural-engine-architecture reading is the save-buffer hypothesis,
but "natural" is not evidence. The session did not produce evidence that
discriminates these.

### Why this question matters for the project

The pre-session promise — that live-memory analysis would yield structural
insight useful for save-file modification — depends on the pin identity.
Specifically:

- If pins are save-buffers in the "serializer reads them as-is" sense,
  writing to them might be a save-edit path. Untested.
- If pins are save-buffers in the "engine refreshes them at save event,
  then serializer reads" sense, writing to them is inert for save
  modification. Player's predicted outcome.
- If pins are anything else, the question of save-edit-via-pin is
  moot — they have nothing to do with save serialization.

Without knowing which hypothesis is correct, the connection between this
session's live-memory work and save editing remains speculative.

### Why this isn't worth running the cheap experiment for, yet

The save-write persistence test (write a pin, complete a chapter, save,
reload, read) has a player-predicted outcome (no persistence) backed by
an architecturally plausible model (refresh-then-serialize). Running the
test would either confirm the prediction (no new information beyond what
the prediction already implies) or refute it (one new datapoint, one
opened door). Player has elected not to spend the test on the
high-likelihood-confirmation outcome.

If the test is later attempted, it should target a stat that's:
- Easily recognizable post-reload (e.g., dream shards modified to a
  clearly-artificial value like 9999).
- Low-stakes if it persists wrongly (currency counter, not progression).
- Backed up beforehand (copy `Profile_1.ob` before modifying).

## Notes

### What discriminating among hypotheses would require

- Save-buffer-correct vs. save-buffer-refresh-first: the cheap test
  above. One chapter completion plus a reload.
- Save-buffer vs. allocation-time-default: snapshot pins at game-start
  across multiple sessions of the same character. If values change, the
  default hypothesis is weakened.
- Engine-internal vs. dead-code: static analysis of the EXE — find which
  functions write to these listener vtables, trace their callers,
  determine whether the call paths are live in single-player gameplay.

None of these are gated on access to Cheat Engine or external tools.
All are doable with the current `rs` CLI plus standard binary-analysis
techniques (e.g., reading `.text` segments via the shim and disassembling
locally, or using a free tool like Ghidra for static EXE analysis).

### What this triage is NOT

- Not a recommendation to continue the live-memory investigation. As of
  session end, the player has indicated the live-memory track has not
  yielded value against project goals.
- Not a closure of the question. The question is genuinely open — none
  of the hypotheses has been discriminated.
- Not a starting point for further exploration of pin identity unless
  the player explicitly authorises it. Future agents reading this should
  first re-anchor against the player's current project priorities before
  proposing work in this area.

### Relation to the other triage

`rw/findings/live-state-mirror-cascade.md` documents what we *observed*
(the 28-mirror cascade, refresh tiers, sentinel-discrimination behaviour)
and treats those observations as findings about live-state architecture.

This triage documents a different open question: **regardless of the
cascade structure, what are the doc's pinned addresses themselves?** The
cascade triage answers questions like "where does live state live?". This
triage answers (or rather, fails to answer) "what's at `0x27cdcfdcd60`
specifically and what reads/writes to it?". They're complementary.
