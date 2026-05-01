# Runtime Level address (Geppetto)

**Status:** triage
**Created:** 2026-04-25

## Sources

- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_analysis.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_struct_probe.txt
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_candidates.txt

## Conquered (moved out of this triage)

The class identification, vtable RVAs, instance layout, and per-snap census were folded into key-findings: see `rw/key-findings/oe-dynamic-listener-data.md`. Per the rule that triage holds only unresolved items, those findings are not duplicated here.

Summary of what's now confirmed (full detail in the key-finding):
- Runtime Level value held at offset +8 in `oe::DynamicCpntValueListenerData<int>` instances
- Vtable RVA, COL pointer, and template specialization map fully mapped
- 5 active instances at L=5 identified by address
- Survive chapter-1 → chapter-2 transition (continue to hold the current Level value)

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
