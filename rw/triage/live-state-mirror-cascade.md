# Live State Mirror Cascade

**Status:** triage
**Created:** 2026-04-26

## Sources

- rw/key-findings/oe-dynamic-listener-data.md (existing key-findings doc; updated this session with the cascade findings — most confirmed content has been folded in there directly)
- rw/docs/archive/oe-listener-mining.md (methodology playbook; updated with corrections; archived 2026-04-27 with the live-memory track tabling)
- Live Ravenswatch process verification (Geppetto, chapter 2, PID 22768; same heap state as MAINT-4 session1 captures)
- tools/rs-src/ (rs trainer CLI used to drive all read/write/find tests this session)

## Confirmed Findings

### All pinned addresses are decoupled from live state — identity beyond "not live" is undetermined

> **Note (closing this triage):** the original heading and prose below
> labelled the pinned addresses "save-buffer mirrors". That label was a
> hypothesis consistent with the observations, not a verified property.
> Multiple other hypotheses fit equally well (allocation-time defaults,
> dead-code subsystem fields, etc.). For the open hypothesis list and
> discriminating tests see `rw/triage/pin-identity-uncertain.md`. The
> verified content here is "not the live source-of-truth"; everything
> beyond that should be read as interpretation.

Live verification of every pin documented in `oe-dynamic-listener-data.md`:

| Pin (value addr) | Trigger event | Result |
|---|---|---|
| HP current `0x27cdcfe8848` (float32) | took damage in-game | stayed at `129.0` across 5 polls over 1.5 s |
| Level `0x27cdcfe8668` (int32) | leveled up 5 → 6 in HUD | stayed at `5` |
| XP current `0x27cdcfefaf8` (int32) | leveled up | stayed at `4583` |
| XP threshold `0x27cdcfef378` (int32) | level transition (HUD threshold rolled over) | stayed at `5000` |
| Dream shards listener `0x27cdcfdcd68` (int32) | spent 50, regained 50 (91→41→91) | stayed at `91` throughout |
| Stars of Fate plain `0x27cdcfe87f8` (int32) | spent 1 (HUD 4 → 3) | stayed at `4` |

All pins held their last save-checkpoint values, fully decoupled from running gameplay. Independently verified bidirectional decoupling for Level: writing 6 then 10 to the pin held in memory but had no in-game effect. The listener-wrapped vs plain-int32 distinction does not predict liveness — both are downstream mirrors.

### Multi-tier mirror cascade (verified for dream shards)

Value-progression scan against the 91→41→91 transition (intersect of `int32 == 41` ∩ `int32 == 91`) returned 28 candidate addresses. Sentinel writes (`-999`) discriminated them into tiers:

| Tier | Refresh cadence | Count | Sentinel persistence |
|---|---|---|---|
| Passive event-mirrors | written once per shard-change event | 22 | retained `-999` indefinitely until next event |
| Active high-frequency mirrors | refreshed from upstream within ~25–50 ms | 6 | overwritten back to `91` within ms |

Discrimination test: writing `-999` to **all 28** mirrors did not affect the HUD's displayed shards count. Within the 6 active mirrors, an isolated write to the slowest-refreshing one (`0x27cc71dced8`) did not propagate to the other 5 — ruling out an internal tier-2 → tier-3 chain. The canonical source the HUD reads from is upstream of every address surfaced by value-progression scanning.

### Stored-vs-computed domain rule

Per player gameplay knowledge:

- **Stored** (single live storage): XP, Stars of Fate, Keys, sibling progression/currency counters.
- **Computed-on-demand**: HP, armor, vitality, crit chance, crit damage, damage, move speed, attack speed, etc. — reconstructed per frame as `base + Σ(modifiers)`.
- **Base values for computed stats**:
  - Armor base = 0 (purely `Σ(modifiers)`, no base register).
  - Damage base = 0 (same).
  - HP base ≠ 0 (per-character class default).

Verified by failed armor base hunt: heap-wide scan for `float32 -5.0` (HUD pre-spend value) returned 15943 matches; 9 inside the player heap region `0x27cdcfd0000–0x27cdcffffff`; sentinel writes (`-999.0`) to all 9 left the HUD unchanged at 1. The `-5` was the displayed total, not a stored base — armor has no base to find.

### Snap-progression filter has a structural blind spot

The MAINT-4 mining workflow filtered listener instances for *value matches the L1..L5 HUD progression at every snap moment*. "Stable across snap moments" is consistent with values committed at a sparse-event tempo and held in between (one such pattern: save-event publication; other patterns also fit, see `pin-identity-uncertain.md`). Live high-frequency listeners would hold mid-combat or mid-XP-tick values at any non-checkpoint sampling moment and never match the progression. **The filter systematically excluded the live source-of-truth.** This explains why every pinned listener turned out to be decoupled from live state, regardless of what the pin's actual identity is.

## Unresolved

### Canonical source location for any stored stat

Unknown. Value-progression scanning consistently surfaces mirrors only. Possible reasons:

- Different data type than scanned (`int64`, packed struct, `__m128i`).
- Computed from component pair (e.g., `total_earned − total_spent`) where neither component equals the displayed value directly.
- Stored in a memory region not reached by the heap scan workflow (uncommitted at scan time, separate allocator, different heap segment).
- Accessible only via code-side analysis (function entry / write breakpoint on a known mirror to capture the upstream caller).

### Save-write persistence test

Untested. If a write to a pinned listener (e.g., `Level = 10` at `0x27cdcfe8668`) is followed by a chapter-end save and reload, does the modification persist to disk? Player-predicted outcome (see closing-session discussion): the engine likely refreshes pins from canonical at save-event start, then serializes — meaning external pre-save modifications would be overwritten before disk write. This prediction is unverified but architecturally plausible.

- If yes (modification persists): listener pins are write-persistable save-buffers — viable foundation for a save editor.
- If no (overwritten before serialization): listener pins are not a save-edit surface; the save serializer effectively reads from canonical via the engine's refresh step.

Test requires completing a Ravenswatch chapter, opting to save, then reloading the save and reading back. Player time-blocked from running this on demand.

### Live mirror sets for stats other than dream shards

Only dream shards has a discovered live mirror set this session (28 addresses). HP, Level, XP, Stars of Fate, Raven's Feathers, etc. would each need their own value-progression discovery: read HUD, scan for current value, controlled trigger event, scan for new value, intersect. Per-stat cost ~2–5 min given a viable trigger.

Player has flagged Raven's Feathers as a "static stat" likely behaving similarly to Stars of Fate (i.e., another decoupled-from-live pin candidate). Doc table at `oe-dynamic-listener-data.md` does not yet list Raven's Feathers.

### Cross-session durability of live mirror addresses

ASLR invalidates all discovered live mirrors on game restart. Three durability paths considered:

1. **Per-session re-discovery** — build `rs discover` (interactive value-progression workflow) + `rs watch-stats` (multi-address watch over a Session) + a catalog file scoped to the running PID. Achievable with current tooling. Per-session user cost ~5–10 min.
2. **Structural anchoring** — reverse-engineer the struct containing the live mirrors, derive their addresses each session from `module_base + RVAs + offsets`. Hours-to-days of structure analysis. No per-session user cost once analysis is done.
3. **Code hooking** — function-level hooks at fixed RVAs to capture write destinations in real time. Requires DLL injection / Cheat Engine integration; out of scope for the current memory-only shim.

Path 1 is the only one achievable without additional toolchain. Build cost ~2–3 hours for `rs discover` + `rs watch-stats` clean with tests. Tracked as proposed MAINT-7 (not yet created).

## Notes

- All experimental writes this session were restored cleanly before pause. Memory state on session pause: every tested address holds its original value.
- The `rs` trainer CLI gained `read`, `write`, `find`, `watch` primitives + a `Session` context manager + per-RPC stdout logging on the shim (toggle with `--quiet`) — shipped under MAINT-6.
- Value-progression scanning produces tens of thousands of matches for common values (`int32 == 1`: shim timed out; `int32 == 41`: 87,396 matches). Filtering by region (player heap range) or via two-step intersection narrows efficiently when the trigger value is non-trivial. Single-value scans for common integers are not workable without further filtering.
- Same Ravenswatch process (PID 22768) used for all tests this session and the MAINT-4 session; heap addresses preserved across shim re-attaches. ASLR-induced re-discovery has not been exercised within the cluster of tests reported here.
