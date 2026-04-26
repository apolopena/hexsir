# Session 1 — runtime Level address analysis

## Verdict

The runtime in-run **Level** value is held at offset **+8** in instances of
**`oe::DynamicCpntValueListenerData<int>`** (a templated observable-int
wrapper from OEngine). The class vtable lives at runtime
`0x00007ff60c8e4ad0` (RVA `0xef4ad0` in `Ravenswatch.exe`, `.rdata`). Class
name was recovered from intact MSVC RTTI:
`.?AV?$DynamicCpntValueListenerData@H@oe@@`, base class
`oe::IDynamicValueListenerData<int>`.

Five active instances of this class exist in heap memory holding the value 5
at L=5 capture, and all five survive the chapter-1 → chapter-2 transition.
The five are likely listener instances observing the same Level value via
the engine's data-binding system (each consumer — UI, save serializer,
replication, etc. — holds its own current copy).

Any of the five Group A addresses below reads the current Level. Modifying
Level via the runtime path probably requires writing to all five, or finding
the "source" via runtime trace.

## Method — within-process find-progression

Five memory snapshots within ONE Ravenswatch process, level-up between each.
Avoids the ASLR shift that broke the cross-process test (see `info.md` and
`old_data/` for the prior approach).

- Snaps: `session1_snap_L1.snap` through `session1_snap_L5.snap`. Baseline = L1.
- Auto-diffs: each snap diffed against L1 → 4 diff files (~50M addresses each).
- `find-progression` subcommand: intersects diffs, filters intersection by
  byte progression `[1, 2, 3, 4, 5]` across the 5 snaps.

Command:

    py mem_snapshot.py find-progression \
      --progression 1,2,3,4,5 \
      --snap session1_snap_L1 ... --snap session1_snap_L5 \
      --out session1_level_candidates.txt \
      --snap-dir C:\ravensmith\snaps

## Initial result — 11 candidates

See `session1_level_candidates.txt`. All in heap range `0x0000027c...` /
`0x0000027d...` — exactly where dynamic run state lives.

## Chapter-2 verification

After beating chapter 1 (still at L=5), grabbed `session1_snap_L5_ch2.snap`.
Read each candidate's byte and classified:

| Address               | L5     | L5_ch2     | Verdict                |
|-----------------------|--------|------------|------------------------|
| 0x0000027c2d5a6d53    | 0x05   | 0x09       | DROP — coincidence     |
| 0x0000027c2d5a6e5b    | 0x05   | 0x09       | DROP — coincidence     |
| 0x0000027c2e04467c    | 0x05   | 0x05       | KEEP                   |
| 0x0000027c86c0aa68    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdcfe8668    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdcfebfe8    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdcfee6f8    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdd006c58    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdd042d34    | 0x05   | 0x05       | KEEP                   |
| 0x0000027cdd38d1d8    | 0x05   | 0x05       | KEEP                   |
| 0x0000027d10828638    | 0x05   | NOT MAPPED | GONE — region freed    |

**Notable:** chapter transition reshuffled ~48% of memory regions (4000+
in-chapter → 2160 shared with L1). Pre-existing risk of Level moving on chapter
load was real, and confirms the decision to exclude the L5_ch2 diff from the
intersect.

## Struct context (from L5.snap)

Reading 16 bytes before + 16 after each surviving candidate revealed three
groups, distinguished by the 8 bytes at offset -8 (the vtable pointer slot for
typical C++ objects).

### Group A — five instances of vtable `0x00007ff60c8e4ad0`

Same module address in every instance → same C++ class.

    0x0000027cdcfe8668
    0x0000027cdcfebfe8
    0x0000027cdcfee6f8
    0x0000027cdd006c58
    0x0000027cdd38d1d8

Class identified via RTTI walk:
`oe::DynamicCpntValueListenerData<int>` — a generic observable-int wrapper.
Five instances exist because multiple consumers each hold their own listener
copy (likely UI cards, save serializer, network replication, etc.).

Analysis of the 384-byte block at struct base `0x0000027cdcfe8660`
(`session1_struct_probe.txt`) shows a component-style layout:

    +0    vtable*       0x00007ff60c8e4ad0
    +8    Level int32 = 5    *** LEVEL FIELD ***
    +12   padding (4 bytes)
    +16   heap ptr*     0x0000027cdc3ed9a0   (sub-object)
    +24   zeros (8 bytes)
    +32   vtable*       0x00007ff60c1ce3c0   (different class — component?)
    +40   heap ptr*
    +48   heap ptr*
    +56   heap ptr*
    +80   vtable*       0x00007ff60c8e4cb0
    +88   float = 1.0   (candidate stat — unverified)
    ...

The structure repeats every ~48-80 bytes — an array of components or
sub-structs. Floats at +88 (1.0) and +328 (3.5) are plausible game stats but
require correlation with HUD screenshots to identify (HP / mana / damage /
etc.).

### Group B — one related instance (different vtable)

    0x0000027c86c0aa68  →  vtable 0x00007ff60c8e5f58

Different but adjacent vtable in the same module — possibly a derived class,
a UI mirror with its own type, or a specialized variant.

### Group C — two zero-buffer candidates (likely save / serialization staging)

    0x0000027c2e04467c  — preceded by 12 bytes of zeros, then int32=161
    0x0000027cdd042d34  — surrounded by zeros

Both look like serialization / staging buffers (heap allocations zeroed at
acquisition, with the Level value written into otherwise-empty memory). Not
the master Level.

## `<int>` listener census (L1..L5)

Scanning all 5 snaps for instances of vtable `0x00007ff60c8e4ad0` (the `<int>`
specialization) yielded a per-instance progression for every observable int in
the running game.

- L1: 14,121 listeners. L5: 16,785 (game allocates more during the run).
- 14,121 listener objects are present in all 5 snaps.

Pattern classification (per progression L1..L5):

| Pattern | Count | Notes |
|---------|------:|-------|
| Strictly +1 per level | 5 | the Level mirrors |
| Strictly increasing, other rates | 5 | XP threshold + 2 mirrored counter pairs |
| Constant all 5 snaps | 11,186 | caps / config / weapon base stats |
| Nonzero changing, non-monotonic | 2,925 | HP / mana / ammo / RNG / combat counters |

Notable monotonic-but-not-+1 progressions:

```
0x0000027cdcfef370  L1..L5: (400, 1100, 1800, 2500, 5000)   ← XP threshold
0x0000027cbc933500  L1..L5: (0, 3, 10, 14, 20)              ← counter pair
0x0000027cbc938320  L1..L5: (0, 3, 10, 14, 20)              ← (mirror)
0x0000027c86992f80  L1..L5: (0, 1, 5, 7, 8)                 ← counter pair
0x0000027c869938e0  L1..L5: (0, 1, 5, 7, 8)                 ← (mirror)
```

The 5000 at L5 is the XP needed to reach L6 — verifiable against HUD screenshot.

Full census written to `session1_int_listener_census.txt`.

## Stat-pin results (from HUD-progression matching)

After scanning both `<int>` (vtable `0x...4ad0`) and `<float>` (vtable
`0x...4cb0`) listener instances across L1..L5 and matching each instance's
value progression against HUD-derived target progressions:

| Stat | Type | Listener address | Match count |
|------|------|------------------|------------:|
| Level | int | `0x27cdcfe8660` (+4 mirrors) | 5 |
| XP threshold | int | `0x27cdcfef370` | 1 |
| XP current | int | `0x27cdcfefaf0` | 1 |
| Dream shards | int | `0x27cdcfdcd60` (+5 mirrors) | 6 |
| Health current | float | `0x27cdcfe8840` | 1 |
| Health max | float | `0x27cdcfe8890` | 28 (one per player listener) |
| Crit chance (percent) | float | `0x27cdcfd91b0` (+4 mirrors) | 5 |

Player's main stat-listener block: heap range `~0x27cdcfd0000–0x27cdcffffff`.

Stats NOT findable via the listener pattern (raw heap scan results in
`session1_raw_progression_pin.txt`):

- **Damage** (HUD: 0,0,11,17,26) — confirmed not stored as int32 or float32 at
  any stable address with this exact progression. Computed at display time.
- **Stars of fate** (HUD: 3,3,4,2,7) — found as **plain int32** at
  `0x27cdcfe87f8`, in the player main stat block but NOT wrapped in a
  listener. The player struct mixes listener-wrapped fields with raw integer
  fields.

Full per-stat candidate lists in:
- `session1_stat_pin.txt` (int listeners)
- `session1_float_stat_pin.txt` (float listeners)

## Files in this directory

- `session1_level_candidates.txt` — raw 11 candidates from `find-progression`
- `session1_struct_probe.txt` — 384-byte hex + interpretation around Group A
  candidate `0x0000027cdcfe8668`
- `session1_int_listener_census.txt` — per-instance progression for all 14,121
  stable `<int>` listeners across L1..L5
- `session1_stat_pin.txt` — `<int>` listener candidates per stat
- `session1_float_stat_pin.txt` — `<float>` listener candidates per stat
- `session1_raw_progression_pin.txt` — raw heap (non-listener) candidates for
  damage and stars-of-fate
- `session1_level_analysis.md` — this file
- `info.md` — original test description (cross-process, superseded for this
  goal but preserved for context)
- `old_data/` — cross-process intersect artifacts (failed approach, kept for
  reference)

## Next steps

1. ~~Disassemble `Ravenswatch.exe` at vtable `0x00007ff60c8e4ad0`~~ DONE.
   Class is `oe::DynamicCpntValueListenerData<int>`. RTTI intact, walked from
   COL at `[vtable - 8]` through type descriptor.
2. Search EXE for OTHER `oe::DynamicCpntValueListenerData<*>` template
   specializations — `<float>`, `<bool>`, `<unsigned int>`, etc. — each has
   its own vtable. Mapping these gives us a way to find HP, mana, and other
   live game stats without per-stat byte hunting.
3. Use HUD screenshots from L5 to identify which specific listener instance
   is bound to which stat (correlate value at +8 with HUD numbers).
4. Confirm "source" vs "mirror" relationship between the 5 Level listeners
   by writing a non-Level value to one and observing in-game behavior.
