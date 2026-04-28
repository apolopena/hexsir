# TASKS.md — Running Ledger

> **Task Codes:** POST-IMPL-X for substantial implementations | MAINT-X for maintenance (fixes, tweaks, refactoring)
>
> **Ordering:** Newest entries at top.
>
> **Scope:** Describe work, not results. Keep test/lint pass counts and coverage totals out. Mention tests only when the work is authoring or refactoring them.

---

## In Progress
<!-- IN_PROGRESS_START -->
*(empty)*
<!-- IN_PROGRESS_END -->



## Done
<!-- DONE_START -->
MAINT-8: Hero-swap edit primitive + save-format consolidation (2026-04-27)
  - verified hero record format: length-prefixed ASCII path `Heroes\<Name>.herodef.ot`; locate via `data.find(b'Heroes\\<name>')`, length prefix is `u32 LE` immediately preceding
  - verified hero swap end-to-end across 4 swaps from chapter2 proof: Carmilla (8-char, no shift), Aladdin (7-char, −1 byte), Snow_Queen (10-char, +2 bytes), Red (3-char, −5 bytes); all loaded with full identity + run-state preserved; engine tolerates body shifts across `−5..+2` byte range
  - observed: slot 1 auto-populates with new hero's L5 ultimate on swap; slots 2/3/4/5 cleared; resolver picks per-hero ult index (3× ult #1, 1× ult #2)
  - level-downgrade test (chapter2 proof, L5 → L1): engine accepts inconsistent state (low-level char + high-level talents); per-ability damage couples to level field (Geppetto hammer strike 23 @ L1, 34 @ L5, same talents); XP value preserved, threshold tracks level
  - disproved `ProfileDreamShards` identification (`b43eeb58…`): writes don't affect displayed profile shards (verified 9999 → in-game still showed 21); pulled from verified-fields table; relabeled `_unknown_b43eeb58` in `mod_save.py`
  - empirically confirmed Steam Cloud sync constraint: cloud restores on game launch following any session that loaded a save; each in-game test is single-session
  - new key findings: `rw/key-findings/save-binary-format.md` (canonical), `rw/key-findings/hero-swaps.md`, `rw/key-findings/hero-table.md`; archived `oe-dynamic-listener-data.md`, `save-chapter-counter.md`, `oe-listener-mining.md` under `key-findings/archive/` and `docs/archive/` with superseded-banner headers
  - new goldens: 4 hero-swap variants + `chapter-rewind-from-ch3-level99` under `rw/saves/edits/golden/geppetto/`
  - updates: `CLAUDE.md` swap-op rule + cloud-sync guidance, `rw/docs/playbook.md` lab directory convention (`<hero>/<run-name>/<mod-id>/`) + failed-test deletion rule + Ravenswatch wiki reference, generated `rw/ref/tree-deciphered.txt` from ciphered tree

PRP-1_save-chapter-edit-primitive (2026-04-27) — extended `rerw` with `read savefile` and `write savefile` commands backed by a YAML field registry; rerw 0.1.0 → 0.2.0
  - `read savefile --source FILE [--chapter] [--level] [-v]`: print field values; no field flags prints all, flags filter to specific fields; reports `<not present>` when a GUID isn't in the save
  - `write savefile --source FILE --dest DIR [--chapter N] [--level N] [-f] [-v]`: edit fields atomically (one read, all writes, single CRC32 recompute, one output file); `--force` / `-f` bypasses overwrite prompt
  - New top-level `read` and `write` Click groups in `cli.py` mirroring the existing `swap_` group; `savefile` registered under each via `cli.add_command()`; REPL builtins deferred (TODO marker)
  - Default output prints `Source savefile: <path>` header on both commands; write also shows `<field>: <old> -> <new>` and `CRC32: <old> -> <new>` plus `Wrote <path>`; `--verbose` / `-v` adds load summary and per-GUID locate+write detail
  - New YAML registry at `tools/rerw-src/data/save-fields.yaml` top-level grouped by shape (`scalar:` populated with chapter and level; `array:` / `ref:` reserved for future inventory / item-id work); each field has `type`, `guids` list, `description`
  - `lib/save_fields.py` (loader, `Field` dataclass, `SaveFieldsError`); `lib/save_edit.py` (CRC + GUID-locate + `read_field` / `write_field`, no Click)
  - Added `pyyaml >= 6, < 7`; workspace lock sync via `just tool-sync-all` (rerw-src for pyyaml resolution, rs-src for stale 0.1.0 → 0.2.0 lock from MAINT-6)

MAINT-7: Save chapter-counter edit primitive (2026-04-27)
  - verified the in-run chapter is stored as two parallel int32 LE records keyed by GUIDs `13fa8e2c...` (opaque) and `6661756c74...` (All_Chapters GameMode reference; ASCII tail `faultdef.ot&`)
  - both progress in lockstep across the chapter2/chapter3/epilogue Geppetto proofs
  - encoding is "chapters completed" — chapter1=0, chapter2=1, chapter3=2, epilogue=3, with the records absent entirely in clean saves
  - chapter3 save edited to chapter=0 (both GUIDs in lockstep, CRC32 recomputed) loaded into chapter 1 with full chapter-3 run-state intact (level, gear, currency, items preserved)
  - produced verified golden at `rw/saves/edits/golden/geppetto/chapter1/laser_lenses_1/chapter-rewind-from-ch3/Profile_1.ob`
  - wrote `rw/key-findings/save-chapter-counter.md` (GUIDs, value semantics, edit procedure: find GUID + 15, write int32 LE, recompute CRC32 at offset 0x0C, install via `rerw swap savefile`)
  - deciphered GUID B's asset path as `All_Chapters.gamemodedefaultdef.ot.GameModeDefaultDefinition.gen` via `rerw decipher`
  - trailing 4 bytes `26 ba 45 19` are plausibly part of the same hash family used for other save-record GUIDs (Level, ProfileDreamShards) — reversing it is the proposed path to programmatic item editing
  - edit performed via existing `rw/scripts/mod_save.py`
  - promoting editor surface to `rerw save` (or alternative shape under discussion) is planned follow-up

MAINT-6: rs read/write/find/watch primitives + shim verbose logging (2026-04-26)
  - added `rs read <addr>`, `rs write <addr> <value>`, `rs find <hex>`, and `rs watch <addr>` Click commands at `tools/rs-src/commands/`, scaffolded via `scafcli tool add command` so the auto-wiring markers in `cli.py` stayed authoritative
  - all four commands follow the existing convention (default single-line output, `--verbose`/`-v` for the `tree-lib` tree)
  - `read`/`write`/`watch` accept a typed `--as` (hex|int32|uint32|int64|uint64|float32|float64|bool) with addresses parsed from `0x...` hex or decimal
  - `find` defaults to a summary (count + first 20 inline) with `--all` and `--out FILE` escape hatches
  - `watch` opens one TCP socket via the new `lib/shim_client.Session` context manager and multiplexes polls over it
  - introduced `lib/value_codec.py` as the single source of truth for the type table (sizes, struct formats, encode/decode, address parsing)
  - kept `lib/shim_client.call` semantics unchanged so existing one-shot commands and tests are untouched, but extracted a `_parse_response` helper shared between `call` and `Session`
  - updated `rw/scripts/windows/rs_shim.py` to log each RPC to stdout (method + param summary + result summary; long hex payloads truncated; addresses rendered as hex), default on with a `--quiet` flag to suppress
  - refreshed `rw/docs/tools/rs.md` with shim stdout-logging behaviour and the persistent-connection model
  - bumped `tools/rs-src/CHANGELOG.md` to 0.2.0
  - tests cover the new commands' quiet/verbose paths, error translation, encode/decode round-trips for every supported type, persistent-session reuse and exit semantics, and the find summary/truncation/file-dump output modes

MAINT-5: rs trainer scaffold and Windows-side shim (2026-04-26)
  - introduced `rs` Click CLI at `tools/rs-src/` with `attach`/`detach`/`status`/`dev sync-shim` commands and prompt-syncing REPL via `repl-lib`
  - auto-detach on `exit` when attached
  - verbose attach mode renders four-step tree via `tree-lib`
  - new `lib/{config,errors,paths,shim_client}.py` with typed `ShimError` hierarchy, env-var override chain (CLI flag > env > default), WSL2 gateway auto-detect, and WSL→Windows path display conversion
  - introduced `rw/scripts/windows/rs_shim.py` (pymem RPC server: ping/attach/detach/modules/regions/read/write/find over line-delimited JSON/TCP, idle until rs calls `attach`)
  - env vars `RS_SHIM_HOST` / `RS_SHIM_PORT` / `RS_SHIM_LOC` documented in the bash wrapper
  - wrote `rw/docs/tools/rs.md` (architecture, deps for Ubuntu/Debian + Void, smoke-test recipe)
  - added session1 HUD log at `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_hud_log.md` preserving raw per-snap stats
  - tests cover command flows, RPC error translation, config resolution, REPL dispatch + exit hook, and path conversion

MAINT-4: OEngine listener-data RE; pin Geppetto runtime stats (2026-04-25)
  - identified `oe::DynamicCpntValueListenerData<T>` as the engine's observable-value pattern via intact MSVC RTTI walk (vtable → COL → TypeDescriptor → mangled name)
  - mapped all 10 `<T>` template specializations and their vtable RVAs in `Ravenswatch.exe`
  - pinned Geppetto runtime stats (Level, XP threshold, XP current, dream shards, HP current/max, crit chance) from a within-process L1..L5 capture, with chapter-2 transition verification narrowing candidates
  - confirmed stars-of-fate as a plain int32 field (not listener-wrapped) and damage as computed-on-demand (no stable storage)
  - added `mem_snapshot.py` subcommands `read`, `find-progression`, `modules` plus `bytes_at_sorted` helper
  - produced `rw/docs/oe-listener-mining.md` techniques playbook, `rw/key-findings/oe-dynamic-listener-data.md` (RVA table + per-session workflow), `rw/triage/level-runtime-address.md`, and session1_* artifacts under `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/`
  - cross-process intersect artifacts moved to `old_data/`

MAINT-3: Memory diff workflow, rerw save swap, REPL (2026-04-25)
  - added `rerw swap savefile` command (with `--source`/`--dest` flags, `RERW_SAVEGAME_DIR` env var, default WSL path to Ravenswatch's `_Save`) and `rerw interactive` REPL backed by `repl-lib`
  - REPL has a custom `swap-savefile` built-in (bivalent: bare enters sub-mode, with flags runs inline) and a context-aware `exit` (leaves sub-mode if in one, else exits REPL)
  - reworked `rw/scripts/windows/mem_snapshot.py` from A/B-pairs into a baseline+diffs+intersect workflow with sequential or labeled grabs (`grab` = next `grabNNN`, `grab <label>` = custom name), strict no-overwrite, `.baseline` marker file, `--out-dir` flag, expanded capture filter (PRIVATE/IMAGE/MAPPED), and live progress counter
  - wrote `rw/docs/tools/mem-snapshot.md`
  - produced golden modded saves at `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/{level5,level8,level14,level17}/Profile_1.ob` with `info.md` describing the level-detect test
  - reorganized Python scripts (`scripts/python/rw/{analyze_save,mod_save}.py` → `rw/scripts/`, removed `caesar_crack.py`)
  - relaxed `scripts/run-tests.sh` CLI-name regex from `^[a-z]+cli$` to `^[a-z]+$`
  - added rerw tests (REPL dispatch and built-ins, swap_savefile env/flag/fallback precedence, lib/paths)
  - ignored REPL history files

MAINT-2: Scaffold Ravenswatch RE workspace and rerw tool (2026-04-25)
  - relaxed scafcli naming to make `cli` suffix optional
  - renamed `hexsircli` → `hexsir`
  - created `rerw` tool with `cipher`, `decipher`, and `harvest` (group stub) plus shared `lib/cipher.py`
  - established `rw/` workspace (`ref/`, `harvested/`, `dumps/`, `triage/`, `key-findings/`, `saves/{proofs,edits/{lab,golden}}`) with `.gitignore` rules
  - wrote `rw/docs/{README,playbook,tools/}` documenting structure, promotion paths, workflow, and doc conventions
  - added `rw-triage-report` skill
  - migrated `interim/` content into `rw/`
  - converted `ANALYSIS_SUMMARY.txt` into `rw/triage/geppetto-save-analysis.md`
  - marked `.ai/docs/rw/` deprecated
  - registered `rerw` in `prime-full-tooling.md` and `scripts/run-tests.sh`

MAINT-1: Initial hexsircli and repo branding (2026-04-23)
  - added `tools/hexsircli` and `tools/hexsircli-src/` with commands (basic, header, scan, verify)
  - registered in `scripts/run-tests.sh`
  - updated README.md with Hexsir branding
  - configured `.claude/commands/prime-full-tooling.md` and `prime-quick-tooling.md` (Tool Suite: hexsircli, scafcli; Indexed-only: scripts/run-tests.sh)
  - updated `.gitignore` with Python build artifact patterns
  - removed project-specific scafcli tests
<!-- DONE_END -->
