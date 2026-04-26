# Runtime Level address (Geppetto)

**Status:** triage
**Created:** 2026-04-25

## Sources

- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_analysis.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_struct_probe.txt
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_candidates.txt

## Confirmed Findings

- The runtime in-run **Level** value is held at offset **+8** in instances of
  the C++ class **`oe::DynamicCpntValueListenerData<int>`** — a templated
  observable-int wrapper from OEngine (Passtech Games' engine).
- Class name recovered from intact MSVC RTTI walk:
  - Mangled: `.?AV?$DynamicCpntValueListenerData@H@oe@@`
  - Base class: `oe::IDynamicValueListenerData<int>`
  - 8 virtual methods.
- Vtable for this specialization:
  - File RVA in `Ravenswatch.exe`: `0xef4ad0` (in `.rdata`)
  - Runtime address in capture session: `0x00007ff60c8e4ad0`
    (Ravenswatch.exe loaded at base `0x00007ff60b9f0000`)
- COL pointer at `[vtable - 8]` -> RVA `0xfcef78`, walked to type descriptor
  at RVA `0x134b9b0`.
- Five active instances of this class held value 5 at L=5 capture:
  - `0x0000027cdcfe8668`
  - `0x0000027cdcfebfe8`
  - `0x0000027cdcfee6f8`
  - `0x0000027cdd006c58`
  - `0x0000027cdd38d1d8`
- All five survive the chapter-1 → chapter-2 transition and continue to hold
  the current Level value.
- Object layout for `oe::DynamicCpntValueListenerData<int>`:
  - `+0`: vtable* (8 bytes) — points to RVA `0xef4ad0`
  - `+8`: int value (held value = 5; upper 3 bytes zero, consistent with int32
    storage)
  - `+16`: heap pointer (likely sub-object / source binding)
  - further fields: component / sub-struct chain (see `session1_struct_probe.txt`)

## Unresolved

- Which of the 5 `<int>` instances is the "source" (vs. listener mirrors).
  Likely one is the originating value-holder and the others receive updates
  via the engine's `IDynamicValueListenerData` callback chain. Determining
  the source-of-truth requires runtime trace (write to one and observe what
  propagates to the others).
- Which `<int>` listener instances bind to which game stat. Level is one
  instance; other `<int>` instances are likely HP, mana, gold, score, etc.
  Correlate by reading value at +8 and matching to HUD screenshots from L5.
- Identity of fields beyond `+8` in the struct probe — the further heap
  pointers and sub-vtables represent the listener's internal binding and
  callback infrastructure, not stat fields per se. Worth resolving only if
  we want to walk listener → source binding directly.

## Resolved (during this triage)

- Class identification: `oe::DynamicCpntValueListenerData<int>` via MSVC RTTI
  walk. RTTI is intact in the binary.
- Full template specialization map: 10 `<T>` specializations exist in
  `Ravenswatch.exe` covering `int`, `float`, `bool`, `oCVec2`, `oCVec3`,
  `oCColor`, `oCTStr<char>`, `oCTypedPtr`, and resource pointers for material
  and texture. See `rw/key-findings/oe-dynamic-listener-data.md` for the
  complete RVA table and locating procedure.
- Sibling vtable `0x00007ff60c8e5f58` (mentioned earlier as a "Group B"
  candidate at runtime address `0x0000027c86c0aa68`) is NOT one of the 10
  `DynamicCpntValueListenerData<T>` specializations. It is a different OEngine
  class — relationship not investigated, but the value=5 at offset +8 in that
  instance is plausibly an unrelated coincidence or a different listener
  family.
- Full `<int>` listener population census across L1..L5 snaps: 14,121
  instances stable across all five snaps. Pattern classification revealed 5
  Level mirrors (strictly +1 per level), 5 other monotonic counters (notably
  one with progression `400, 1100, 1800, 2500, 5000` — almost certainly the
  XP threshold for the next level), 11,186 constant fields (caps / config),
  and 2,925 fields changing in non-monotonic ways (combat-affected stats).
  Census saved at
  `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_int_listener_census.txt`.

## Notes

- **Method:** within-process `find-progression`. Five memory snaps captured
  inside one Ravenswatch process, level-up between each (L1 → L2 → L3 → L4 →
  L5). Diffs auto-generated against L1 baseline. `find-progression` intersects
  the diffs and filters to addresses whose byte progresses `[1, 2, 3, 4, 5]`
  across the snaps.
- **Initial yield:** 11 candidates from the byte progression filter.
- **Chapter-2 verification:** A separate `session1_snap_L5_ch2.snap` was
  captured after beating chapter 1 (still at L=5). Cross-checking each
  candidate's byte: 8 still read 0x05, 2 had random values (coincidence,
  dropped), 1 was in a region freed at chapter load (gone). The L5_ch2 diff
  was *not* included in the intersection — chapter loading reshuffled ~48% of
  memory regions, and including its diff risked excluding the Level address
  itself.
- **vtable grouping:** 5 of the 8 surviving candidates share an identical
  pointer at offset −8, indicating instances of the same C++ class. The byte
  progression filter alone could not distinguish them; vtable analysis was the
  decisive disambiguator.
- **Why cross-process failed (preserved as `old_data/` in the source dir).**
  Ravenswatch requires a process restart between save loads, which means
  cross-save snaps are from different ASLR layouts. The Level virtual address
  shifts and cannot be cross-referenced. The within-process method sidesteps
  this by capturing all snaps inside one running process.
- **Tooling:** `rw/scripts/windows/mem_snapshot.py` subcommands `grab`,
  `find-progression`, `read`. The first two run on Windows (need pymem +
  admin); analysis steps run on WSL via `/mnt/c/ravensmith/snaps/`.
