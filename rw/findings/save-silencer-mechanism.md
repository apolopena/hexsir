[← Back to findings](README.md)

# Save silencer mechanism — definitive root cause
**Status:** confirmed


Status: **CONFIRMED via static analysis** (Ghidra, 2026-04-30 late session).

## Sources

- pre-policy — written before the Sources header was mandatory.

## TL;DR

Edited save files trip a "save compatibility" flag at `data_source + 0x19ac` on load. When that flag is set during session init, an event subscriber `on_event_19eadad1_disable_run_saves` is registered. From that moment, every dispatch of event ID `0x19eadad1` (the engine's save-orchestration event) sets `data_source + 0x1ef4 = 1` (the saves-disabled flag), and **every subsequent save call in the session — both profile saves and run-state saves — silently no-ops with no error, no log, no UI feedback**. Quitting and relaunching is the only way to clear it within the user's normal control.

This is the mechanism behind the user's lost EXPERIMENTAL-3 chapter-2 post-play save (and apparently every save attempt since).

## The chain

### 1. Session init runs `global_save_modal_init_dispatcher` (image+0x25d3b0)

Decompile-confirmed branch:

```c
bVar2 = *(byte *)(param_1 + 0x19ac);          // data_source + 0x19ac = save-compat flag
if ((bVar2 & 0xfd) != 0) {                    // any bit except bit 1 trips this
    // ... show SaveCompat modal (i18n keys 'SaveCompat_Title', 'SaveCompat_Desc')
    local_d8 = &on_event_19eadad1_disable_run_saves;  // ★ register the silencer
    FUN_140503df0(lVar14, &local_e8);
}
```

The mask `0xfd = 1111 1101` excludes bit 1 (`0x02`). All other bits trigger the SaveCompat modal AND register the silencer subscriber.

### 2. The silencer (`on_event_19eadad1_disable_run_saves` @ image+0x27c320)

Five-instruction event handler:

```
CMP dword ptr [RCX], 0x19eadad1   ; check event ID
JNZ skip
MOV RAX, qword ptr [R8]            ; load data_source
MOV byte ptr [RAX + 0x1ef4], 0x1   ; ★ set saves-disabled flag
skip: RET
```

Sets the byte-flag at `data_source + 0x1ef4` to 1 the first time event `0x19eadad1` fires. Once set, never observed cleared (no writer-of-0 found in static analysis).

### 3. Every save site checks `+0x1ef4` and silently skips if non-zero

Confirmed gates at all save trigger sites:

- **`session_finalize_and_save` (image+0x28d6a0)** — the run-state save called when user clicks "Save and Quit" on the boss-kill modal:
  ```c
  if (lVar6 == g_oCDtRootGs_typedesc) {
      if (*(char *)((longlong)puVar3 + 0x1ef4) == '\0') {  // ← gate
          save_request_sync(extraout_XMM0_Da, puVar3 + 0x325);
      }
      goto LAB_14028da95;  // emits chapter analytics, returns silently
  }
  ```
  No error path. No log line. The function's tail emits `map.name`/`map.chapter`/`map.difficulty`/`playtime.run` telemetry then `RET`.

- **`on_event_19eadad1_request_profile_save` (image+0x27c340)** — the periodic profile save handler:
  ```
  CMP byte ptr [RAX + 0x1ef4], 0x0
  JNZ skip                              ; ← gate — silently skips if set
  ... save_request_async(profile_save_struct + 8) ...
  ```

- **`global_save_modal_init_dispatcher` itself** — async profile save inside the same init function:
  ```c
  if (*(char *)(param_1 + 0x1ef4) == '\0') {     // ← gate
      save_request_async(uVar19, DAT_14140dd70 + 8);
  }
  ```

All save paths in the binary that we have mapped check this flag. Once set, **nothing in the normal save flow can write to disk for the rest of the session**.

## Why this matches the empirical observation

User symptoms (multiple playthroughs this session):
- Reaches chapter-2 boss kill, sees the save dialog
- Clicks "Save and Quit"
- Game accepts the input, exits cleanly
- Live `_Save/Profile_1.ob` mtime never advances
- No error message, no crash, no visible indication

Per the chain above: each playthrough started by loading an *edited* chapter-1 starting golden (the `4e0258ee775ba51f...` minted save). That edited save trips bit(s) in `+0x19ac` on load → SaveCompat init runs → silencer subscribed → first event-19eadad1 dispatch sets `+0x1ef4 = 1` → every later save silently no-ops.

The user's "Save and Quit" click DOES route through `session_finalize_and_save`, which DOES walk the linked list, find the data_source, check `+0x1ef4`, see it's non-zero, skip the `save_request_sync` call, and `RET`. Game-exit code (which lives outside this function) then runs normally. **That's the entire silent-failure path.**

## Why CLAUDE.md "false negative" wording fits

CLAUDE.md "Save-load error modal — read the actual outcome, not the modal" describes a "false negative" — the modal appears, user clicks OK, routed to Continue/New-Game dialog, save loaded successfully. User concludes "no problem." But under the hood, the SaveCompat flag was set by the loader before the user even saw the modal, and from that point all saves are silenced. The "false negative" outcome is **only false-negative for the load itself**; it's a TRUE positive for "your save edits will be lost this session."

## What this means for the lost EXPERIMENTAL-3 save

The chapter-2 post-play save the user worked ~20 minutes for — and tried again twice tonight — was **never written to disk on any of those attempts**. The silent-no-op path fires every time. The lost save is not in any directory because it never existed on disk. There's nothing to recover.

## ROOT CAUSE FOUND (post-investigation update)

The byte at `+0x19ac` is **NOT loaded from the save file**. It's the IO job's runtime result-code field (`save_io_job + 0x84`, per existing RE doc). Constructor sets it to `0x0A`. After load, the IO dispatcher writes the result code returned by `save_read_binary_stream`.

`save_read_binary_stream` returns:
- `0` = full success
- `2` = file not found (no save → start fresh)
- `3` = open/read IO failure
- `4` = `settings_post_load_processing(...)` returned 0
- (saves don't reach here → `0x6` = pre-write guard fail per orchestrator)

**Code 4 specifically traces to:** `settings_post_load_processing` → `save_load_parse_top_level` (.ob path) → `save_load_parse_object_section` → returns 0 if any class's deserialize returns 0.

**For our edited saves, the failing class is `ActivityScore`.** The mint recipe replaces each of the 6 ActivityScore bodies with a 25-byte zero-filled stub. The original ActivityScore body is ~115 bytes containing:
- u32 marker (=2)
- length-prefixed icon path string (e.g., `BookMenu\UI_Icon_ScoreActivity_Mission.png`)
- u32 (=3)
- length-prefixed `Text`
- length-prefixed localization file (`Common~GAM.xls`)
- length-prefixed marker (`MinimapMarker_Quest`)
- trailing float (e.g., 0.25)

When the deserializer hits an ActivityScore body of only 25 zero bytes, it can't read the expected fields → stream-read fails → returns 0 → cascades up → code 4 → silencer registered.

### Fix history — preserve-bodies → AS-removal (current production)

Two fixes have shipped against this mechanism. Both avoid the silencer; they differ in side effects.

**Fix 1 — preserve ActivityScore bodies verbatim (initial fix, EXPERIMENTAL-3, superseded).**

The original mint recipe replaced each ActivityScore body with a 25-byte zero stub, which caused the deserialize failure described above. The first fix was to preserve all AS bodies at their original size. This avoided the silencer (deserialize completed successfully) but left chapter-N icon paths in each preserved body, producing a separate **activity-icon carryover bug** on the score-details panel (the user's "compounding blanks" symptom).

Verified across three tests: SaveCompat modal absence on load, score-details cleanup after restart, and a full chapter-boss-kill + save-and-quit run that produced a real disk write at `rw/saves/mints/geppetto/chapter2/test3-silencer-fix-verified/Profile_1.ob` (hash `71f093f11484eae1`, 75977 bytes, mtime advanced).

**Fix 2 — REMOVE ActivityScore records and zero the parent count u32 (BREAKTHROUGH-1, current production, commit `52cff33`).**

The CRP body's u32 immediately preceding the first ActivityScore frame is the count consumed by the deserialize loop. With count = 0 and the AS frames snipped from the body, `ActivityScore_Serialize` (image+0x1da440) is never called. No deserialize → no error code 4 → no silencer registration. Side benefit: no chapter-N icons render on the score-details panel, fixing the activity-icon carryover bug that fix 1 left in place.

A second carryover bug surfaced and was fixed in the same session — the chapter-progression banner u32 in CRP body at `(first_AS_frame.start - 8)` encodes `3 × chapters_completed_before_death` and drives the end-screen banner display. The production mint zeros this u32. See `rw/findings/save-edit-pipeline.md` for the field documentation.

The production mint at `tools/rerw-src/lib/save_mint.py` applies fix 2; the unit-test regression at `tools/rerw-src/tests/unit/test_lib_save_mint.py` (`test_activity_score_records_removed` + `test_activity_score_parent_count_zeroed`) guards both pieces. Verified in-game on the chapter-3 mint with `mint__from-chapter3-laser_lenses_1-proof/` (chapter-1 golden).

**Bonus finding from test 3 save:** the test3 success save has `HC body+0x21 ingredient_vec_count = 1` — the first save ever observed with a NON-empty HeroIngredient vector. This unblocks the held-inventory location investigation (item 1 of `rw/findings/save-mint-status.md`). The earlier conclusion "held inventory is NOT in HC.HeroIngredient because the vector is always empty" needs revision; revisit with this new anchor.

### Bonus hypothesis: this also explains the compounding-blanks bug — VERIFIED

The "compounding blanks" symptom (leftover grey-diamond achievement slots interleaving on the score-details page) was indeed downstream of the AS records, but not via deserialize failure as originally hypothesized. The records' preserved bodies contained chapter-N icon paths and localization strings; the game rendered them on the score-details panel regardless of whether the player completed those activities in the current run. Removing the records (fix 2) makes the panel render empty. The hypothesis is confirmed in spirit: AS records and the silencer share the same root, and AS-removal fixes both.

### Verification chain

| Class | Proof body | Edited body | Length preserved? |
|---|---|---|---|
| oCDtGameProfile | 4128 | 3583 | NO (children differ) |
| oCDtPlayerProfileData | 17 | 17 | yes |
| oCDtCurrentRunProfileData | 1311 | 766 | NO (children differ) |
| oCEntityPersistentDataContainer × 2 | 144 / 8 | 144 / 8 | yes |
| **ActivityScore × 6** | **113-119 each** | **25 each** | **NO ← THE BUG** |
| HeroScoreData | 151 | 151 | yes |
| HC | 873 | 873 | yes |

Only ActivityScore got truncated. Only ActivityScore is the trigger.

## Original "what writes `+0x19ac`" investigation (superseded above)

Static byte-search for instructions writing the offset finds zero. Hypothesis: the field is loaded from the save file via the SerializeArchive pipeline (i.e., the flag is part of the on-disk state of `oCDtRootGs`), not set by code. If true, then:
- Every load of an edited save with the flag set → silenced session
- Saving from a silenced session would, if it actually wrote, propagate the flag forward (but nothing writes, so this is moot)

Discriminating tests:
1. Load a known-good UNEDITED proof save (e.g., `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob`, SHA `dec9f6f44b0c4fd6...`) and play to a chapter boss. If save fires, the flag wasn't set on that save → flag is in the on-disk format and the user's edited saves carry it.
2. Hex-inspect the save file at the byte position corresponding to data_source +0x19ac (offset within the SerializeArchive layout). Compare across edited vs original saves.

## Fixes / mitigations

### Immediate (within current session)
Live patch `data_source + 0x1ef4 = 0` via in-process edit — saves will start firing again until the next event-19eadad1 dispatch resets it. Requires runtime memory write capability we don't currently have wired up (WinDbg deferred per user).

### Per-session
- **Quit and relaunch the game between save edits.** The flag does not persist through process restart (it's loaded at session init only).
- For test playthroughs that need a save event, load only saves that don't trip `+0x19ac`. The chapter-2 PROOF (`dec9f6f44b0c4fd6...`) is a known-good gameplay save; verify it loads silenced or unsilenced before relying on it.

### Permanent (in `rerw write savefile`)
Once the on-disk byte position of `+0x19ac` is identified, add a clear-save-compat-flag step to the mint recipe. Any save we mint should write `0` to that byte so loaded saves never trip the silencer.

### Skip the silencer entirely (mod-level)
Patch the binary at `0x14025d6c8` (`LEA RAX, [on_event_19eadad1_disable_run_saves]`) to load a no-op handler instead. This permanently disables the silencer regardless of `+0x19ac` value. Risk: unknown — the SaveCompat flow may exist for a reason (preventing corrupt saves from overwriting good ones).

## Cross-references

- `rw/findings/save-subsystem.md` — full save subsystem RE; this finding extends the "open question" on `+0x1ef4` listed there.
- `rw/findings/save-event-not-firing.md` — the observation triage; this doc supersedes both hypotheses (mis-click, game-lies). The mechanism is structural.
- CLAUDE.md "Save-load error modal — read the actual outcome, not the modal" — same mechanism, observed from the UI side.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. The handful of RVAs in this finding live in the broader save subsystem.

### Symbols specific to this finding

| Symbol | Anchor |
|---|---|
| `on_event_19eadad1_disable_run_saves` (image+0x27c320) | Hash `0x19eadad1` is the registered named-event ID. Byte-pattern search for `ad da ea 19` returns the registration site and this handler. The handler is the one that writes to `+0x1ef4` (single-byte write of `1`). |
| `+0x1ef4` flag on `oCDtRootGs` | The "saves disabled" gate. Re-derive: find `oCDtRootGs` via RTTI (`.?AVoCDtRootGs@@`), then look for any function that writes a single byte to `[oCDtRootGs+0x1ef4]`. Should be exactly one. |
| `+0x19ac` save-result code on the IO job | See `save-subsystem.md` Tier 4 struct offsets (`+0x1928 + 0x84 = +0x19ac`). |
| Patch site at `image+0x25d6c8` (LEA to silencer handler) | Re-derive: xrefs from the silencer handler function, find the static-init site that LEAs to it. There's typically one such LEA in a registration table. |

### Hash anchor (content-derived, version-stable)

| Hash | Meaning |
|---|---|
| `0x19eadad1` | Named event ID for "SaveCompat / disable run saves" — registered as a string somewhere; survives recompiles unless the event is removed. |

### Cross-finding anchoring

Inherits from `save-subsystem.md` Tier 1-4 anchors.

## Ghidra annotations applied (2026-04-30)

| Address | Name | Note |
|---|---|---|
| `0x14027c320` | `on_event_19eadad1_disable_run_saves` | The silencer setter |
| `0x14027c340` | `on_event_19eadad1_request_profile_save` | Profile-save trigger (gated) |
| `0x14027c3d0` | `on_event_19eadad1_clear_data_source_20f0` | Sibling handler (clears unrelated flag) |
| `0x1407c5560` | `event_19eadad1_tag_setter_thunk` | Constructor that writes the event ID |
| `0x140eede10` | `i18n_key_SaveCompat_Desc` | Localization key string |
| `0x140eede20` | `i18n_key_SaveCompat_Title` | Localization key string |
| `0x1401d0430` | `i18n_resolve_string_by_index` | Localization registry accessor |
| `0x14025d3b0` | `global_save_modal_init_dispatcher` | (already named) Hosts the SaveCompat init branch |
