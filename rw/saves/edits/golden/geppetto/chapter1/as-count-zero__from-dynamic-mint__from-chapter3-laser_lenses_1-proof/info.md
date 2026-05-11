# as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof

> **SUPERSEDED 2026-05-01** by `mint__from-chapter3-laser_lenses_1-proof/` — same fix for activity-icon carryover, plus an additional fix for chapter-progression banner carryover, produced by the production `rerw mint savefile` CLI in one shot rather than the manual scratch-script chain.

## Provenance

- **Source path:** `rw/saves/edits/lab/dynamic-mint__from-chapter3-laser_lenses_1-proof/Profile_1.ob` (lab-side chapter-3 dynamic-mint output, 76,465 bytes)
- **Lineage chain:** chapter-3 proof → dynamic-mint (lab) → AS-count-zero
- **Edit name:** `as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof`
- **SHA-256 (full):** `1f3fefd5cf6d28498fef67b1baaa83af89bf4590e6fabd9817a599376efd68ad`
- **Size:** 75,065 bytes

## Reproduction recipe

Historical only — the AS-removal step is now applied automatically by `rerw mint savefile`. The equivalent today is the recipe under `mint__from-chapter3-laser_lenses_1-proof/info.md`.

The original edit, applied on top of the dynamic-mint lab: removed all 11 nested `ActivityScore` records under `oCDtCurrentRunProfileData` and set their parent count u32 to 0. Snipped 1400 bytes of AS frames from the CRP body (1944 → 544 bytes). CRC32 recomputed on encode.

## Verified in-game

- Date: 2026-05-01
- Loads cleanly, **no SaveCompat modal**.
- Game routes directly to Continue dialog (not fresh-account hero-select).
- Sandman Shop arena loads with chapter-1 baseline state (Stars of Fate=7, hero level=1, XP=0).
- Score-details panel: **no chapter-3 activity icons present** (the bug is gone).

The mechanism (count=0 means the loader's per-class deserialize never runs, so the silencer doesn't trip) lives in `rw/findings/save-silencer-mechanism.md`.
