# Random seed system — locate and edit

Status: backlog. The held-inventory hunt is mostly resolved as of 2026-05-01 (keys, Raven Feathers, Dream Shards all mapped — see `rw/triage/save-mint-status.md` item 2 and `rw/triage/geppetto-save-analysis.md`). Only held wood/bean and other minor ingredient-type resources remain. This item moves up the queue once those finish or are deferred.

## Observation
Run randomization is **partially** deterministic per-seed. Replaying the same chapter, some elements repeat exactly while others differ — hard to perceive which is which. The game also exposes a "replay this exact run" capability, which is strong evidence the seed (or seed set) is persisted somewhere accessible. The game UI displays a seed number on screen during play — exact location TBD (note when next visible).

### Multi-seed hypothesis (now leading)
The mixed same/different replay behavior suggests there isn't a single master RNG. Likely structure: a top-level seed that drives some systems (encounter layout, talent offers?) plus independent sub-seeds for others (loot rolls? enemy AI? cosmetic effects?). Or: one master seed deterministically derives N sub-seeds for distinct subsystems, but only some subsystems consume the seed at run-start (others re-seed live from clock/entropy). Discriminating test deferred until after locating any seed at all.

## Goal
Find where the active run's seed is stored (memory and/or save file) and add an edit path. Setting seed = reproducible runs for testing AND deliberate scenario crafting (replay a known-good RNG sequence, share seeds, lock in a favorable talent-offer chain).

## Value
Estimated comparable to the Stars of Fate edit. Stars of Fate defeats RNG on talent picks; seed control defeats RNG everywhere else (encounters, drops, layout if applicable).

## Starting hints
- Seed is displayed in-game (capture exact UI location + format on next play session — is it hex? decimal? how many digits?)
- Search anchors to try once we have the displayed value:
  - Ghidra string-search the rendered seed format (`%08X`, `Seed:`, `Run Seed`, etc.) → caller is the renderer → walk back to source field
  - Live-memory search for the displayed integer once WinDbg/trainer is viable (currently deferred — WinDbg crashes on save event per user)
  - Save-file search: byte-search the displayed value across known proof saves; if it appears, the seed is persisted

## Open questions
- Is the seed per-run only, or persisted across the save? (If only per-run, a save edit can't set it — we'd need live-memory write.)
- Is there one seed per chapter, or one master seed that drives a deterministic per-chapter sub-seed?
- Does the seed change on chapter rollback (`rerw write savefile --chapter`), or is it preserved?

## Cross-references
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — Stars of Fate edit pattern (template for what a "set seed" edit might look like if persisted)
- WinDbg deferred per user (causes crashes during save event, attempted previously)
