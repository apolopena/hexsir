# as-count-zero__from-dynamic-mint__from-chapter3-laser_lenses_1-proof

**SUPERSEDED 2026-05-01** by `mint__from-chapter3-laser_lenses_1-proof/` — same fix for activity-icon carryover, plus an additional fix for chapter-progression banner carryover, and produced by the production `rerw mint savefile` CLI in one shot rather than the manual scratch-script chain.

**Promoted to golden:** 2026-05-01
**Hash (SHA-256, full):** `1f3fefd5cf6d28498fef67b1baaa83af89bf4590e6fabd9817a599376efd68ad`
**Size:** 75065 bytes

## Provenance

- **Source:** `rw/saves/edits/lab/dynamic-mint__from-chapter3-laser_lenses_1-proof/Profile_1.ob` (the chapter-3 dynamic-mint output, 76465 bytes)
- **Edit applied:** removed all 11 `ActivityScore` records nested under `oCDtCurrentRunProfileData` and set their parent count u32 to 0. Snipped 1400 bytes of AS frames from the CRP body (1944 -> 544 bytes).
- **Lineage:** `chapter-3 proof` -> `dynamic-mint` -> `as-count-zero`

## What this golden proves

**The activity-icon carryover bug is fixable via save edit alone**, with no runtime patching, no chapter-1 playthrough, and no risk of tripping the save silencer.

Carryover from the prior chapter-1 golden (`dynamic-mint__from-chapter3-laser_lenses_1-proof`): the score-details panel still showed 11 chapter-3 ActivityScore icons because the dynamic-mint preserved AS bodies verbatim. With AS records fully removed and the count u32 zeroed, the loader's per-class deserialize never runs (count=0 -> loop body executes 0 times), the panel renders empty, and Error code 4 / silencer is sidestepped entirely.

## Verified in-game (2026-05-01)

- Loads cleanly, **no SaveCompat modal**.
- Game routes directly to Continue dialog (not fresh-account hero-select).
- Sandman Shop arena loads with chapter-1 baseline state (Stars of Fate=7, hero level=1, XP=0).
- Score-details panel: **no chapter-3 activity icons present** (the bug is gone).
- Validation deemed sufficient without a chapter-1 playthrough — clean load + clean panel + no modal == confirmed working. The prior bug was not gated on actually playing through chapter 1; it surfaced immediately from any state where the score-details panel was viewable.

## Why this works (mechanism)

Per `rw/key-findings/save-silencer-mechanism.md`, the silencer trips when ActivityScore deserialize fails (returns 0 from the per-class wire-format read). Truncated AS bodies (the original mint bug) failed deserialize. The fix that landed in the prior golden was to PRESERVE bodies — but that left chapter-3 icon paths intact, producing the carryover.

Removing the records entirely and zeroing the parent's count u32 means:

- The loader reads `count = 0` from CRP body.
- The framed-sub-object loop runs 0 iterations.
- No `ActivityScore_Serialize` (`image+0x1da440`) call ever fires.
- No deserialize, no Error code 4, no silencer subscription.
- No icons to render on the score-details panel.

Confirmed by round-trip parse: 0 ActivityScore instances in the new file.

## Cross-references

- `rw/key-findings/save-silencer-mechanism.md` — why the prior approach (preserve bodies) was chosen and what code 4 trips
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — pipeline overview (recipe is now AS-removal, not preserve)
- `rw/saves/edits/golden/geppetto/chapter1/dynamic-mint__from-chapter3-laser_lenses_1-proof/breakthrough.md` — prior chapter-1 golden, superseded for clean-mint use by this golden
- `tools/rerw-src/lib/save_mint.py` — production mint, AS-removal step folded in this same session
- `ActivityScore_Serialize`: image+0x1da440 (the per-record deserializer that no longer runs for count=0 files)
