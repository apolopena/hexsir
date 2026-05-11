# Session 1 — HUD log

Raw HUD readings, one column per snap. Manually transcribed from in-game
HUD screenshots taken at each paused moment (matching the corresponding
`session1_snap_L<N>.snap` capture). Source data only — analysis lives in
`session1_level_analysis.md` and `session1_stat_pin.txt` /
`session1_float_stat_pin.txt`.

| Stat                  | L1     | L2      | L3     | L4     | L5     | L5_ch2  |
|-----------------------|-------:|--------:|-------:|-------:|-------:|--------:|
| Level                 | 1      | 2       | 3      | 4      | 5      | 5       |
| XP (current / max)    | 0/400  | 48/1100 | 13/1800| 431/2500| 26/5000| 4593/5000|
| Health (cur / max)    | 80/80  | 108/88  | 97/97  | 106/106| 117/117| 129/129 |
| Vitality              | 0      | 0       | 0      | 0      | 0      | 100     |
| Damage                | 0      | 0       | 11     | 17     | 26     | 45      |
| Armor                 | 0      | 0       | 0      | 0      | 0      | -5      |
| Crit chance (%)       | 5      | 5       | 9      | 9      | 9      | 27      |
| Crit damage (%)       | 50     | 50      | 50     | 50     | 50     | 50      |
| Dream shards          | 0      | 0       | 37     | 1      | 1      | 91      |
| Stars of fate         | 3      | 3       | 4      | 2      | 7      | 4       |
| Ravens feather        | 2      | 2       | 2      | 3      | 3      | 3       |
| Key                   | 0      | 0       | 0      | 1      | 0      | 0       |

## Notes

- **L2 health 108/88**: current HP exceeds max — game allows current to exceed
  cap, likely from a heal/overheal effect just before the paused snap.
- **L5_ch2**: snapshot taken at the start of chapter 2 (after beating chapter
  1), still at Level 5. Used as the chapter-transition verification sample —
  many stats jump because chapter 2 grants buffs / picks up items / scales.
- **Crit chance**: stored internally as a float percent (`5.0` / `9.0`), not
  as a fraction. Confirmed by `session1_float_stat_pin.txt` matching `(5,5,9,9,9)`.
- **Damage**: progression `0,0,11,17,26` does NOT match any stable int32 or
  float32 listener — confirmed computed at display time, not stored.
  See `session1_raw_progression_pin.txt`.
- **Stars of fate**: progression `3,3,4,2,7` matched a plain int32 (not a
  listener) at `0x27cdcfe87f8`.

## Source provenance

Per-snap correlated screenshots:

- `session1_snap_L1.png` ← (if captured separately; HUD numbers above)
- `session1_snap_L2.png`
- `session1_snap_L3.png`
- `session1_snap_L4.png`
- `session1_snap_L5.png`
- `session1_snap_L5_ch2.png`

If image files weren't archived, this `.md` is the canonical record for
session 1 HUD state.
