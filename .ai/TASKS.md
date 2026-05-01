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
MAINT-17: `write savefile keys` + deprecation labels on parent flags (2026-05-01)
  - Added `rerw write savefile keys <int>` for held Nightmare Keys count. Updates existing keys record's count u32; empty-vec insertion (creating a new record on a save without one) deferred.
  - `lib/setters.py` gains `set_held_keys`; mint zero-sequence calls it (no-op for empty-vec proofs, zeroes count u32 for saves with an existing record like test3-mint).
  - Parent-level deprecated flags on `write savefile` now carry `[DEPRECATED]` help labels pointing to their replacement subcommands.

MAINT-16: Strict-key game registry + `game-assets inspect` discovery surface (2026-05-01)
  - New `lib/game_registry.py` exposes `heroes()`, `hero_talents(hero_key)`, `magical_items()` with strict-key lookup (no aliases / no fuzzy / no display-name fallback). Validates `schema_version` (major-version match) and `registry_id` per file.
  - New `rerw game-assets inspect heroes|talents|items` discovery commands. Default: NAME / KEY (+ DESCRIPTION for items/talents). `-n` omits description; `-v` adds developer fields (GUID, EFFECT/CONTROLLER, etc.).
  - Migrated `rerw write savefile talent --key` from fuzzy `resolve_talent_id` to strict `registry.hero_talents(hero).lookup(key)`. Display names and aliases now error; only canonical keys accepted.
  - Legacy `rerw write savefile --talent-id` (deprecated parent flag) still errors via the legacy loader's outdated YAML schema expectations — not regressed in this commit; tracked under YAML schema migration.

MAINT-15: Refactor mint + write savefile CLI into per-field subcommands (2026-05-01)
  - Mint becomes a pure transformation; semantic flags removed (`--chapter`/`--stars`/`--level`).
  - New `lib/setters.py` exposes pure setter functions; mint and write savefile share the same library so their behavior can't drift.
  - `rerw write savefile` is a Click group with per-field subcommands: chapter, feathers, level, stars, xp, talent, tier. Single-value edits are positional (e.g. `feathers 6`); multi-value use named flags (`talent --slot 1 --key X`).
  - Legacy parent flags (`--chapter`/`--level`/`--talent-*`) preserved with a deprecation warning; will be removed in a future release.
  - `$RERW_SAVEFILE` env var supplies `--source` default for both mint and write savefile.
  - 1-based user-facing indices (chapter 1..4 where 4=epilogue; talent slot 1..5; tier slot 1..4).
  - Held Raven Feathers (CRP body+0x15D, identified earlier this session) is now zeroed by mint and editable via `write savefile feathers`.
  - Subcommands `hero`, `keys`, `shards` deferred (next iteration).

MAINT-14: Sync key-findings + triage docs to BREAKTHROUGH-1 (2026-05-01)
  - `save-silencer-mechanism.md`: noted AS-removal as current production fix, preserve-bodies marked superseded, compounding-blanks hypothesis marked VERIFIED.
  - `save-edit-pipeline-2026-04-30.md`: documented the chapter-progression banner u32 in CRP body; Known-gaps section updated to reflect resolved items.
  - `save-mint-status.md`: activity-icon carryover marked RESOLVED; chapter-2-only mint gate noted as removed.
  - `mint-hardcoded-offsets.md`: marked RESOLVED (option C implemented via `lib/hc_walker.py`).

BREAKTHROUGH-1: Mint carryover bug fixes; mint goes chapter-agnostic (2026-05-01)
  - Bug fix: chapter-N ActivityScore icons carrying into derived mints' score-details panel.
  - Bug fix: chapter-progression banner carrying source-proof run history into derived mints' end-screen.
  - Folded dynamic HC body walker into production (`lib/hc_walker.py`); lifted chapter-2-only mint gate.
  - Tests parametrized over discovered `rw/saves/proofs/**/Profile_1.ob` fixtures.
  - New chapter-1 golden `mint__from-chapter3-laser_lenses_1-proof/` (production-CLI output); two prior chapter-1 goldens marked SUPERSEDED.

EXPERIMENTAL-3: Save mint POC — zero every per-run stat we could find + Stars of Fate edit + chapter-1 round-trip (2026-04-30)
  - **Full per-run zero-out recipe (the mint)** — chapter-2 proof was zeroed across every per-run record we know: HeroController damage region (4 floats at body+0x11/+0x15/+0x19/+0x1d), HeroController body+0x35d (originally 990 — turned out to be dream-shards-collected, accidentally zeroed thinking it was a damage stat), `ActivityScore × 6` nested under `oCDtCurrentRunProfileData` replaced with synthesized 25-byte minimum bodies, `HeroScoreData` 28 score floats zeroed in place (cached snapshot), `oCDtCurrentRunProfileData` body+0xe5 (playtime float = 1409s = 23:29 → 0). **Only one per-run stat we couldn't zero**: HeroController body+0x25 ("Raven Feathers consumed" stat — score-page row stays stuck at the written value, mirror-cascade behavior, writing 0 doesn't take). Plus body+0x2d (unknown stat — same stuck behavior). Both deferred.
  - **Hero level + accumulated XP zeroed together** to keep the per-run "Level reached" stat from being inflated by leftover XP. `oCDtEntityCpntGroupLevelPersistentData` body+0x11 = 1 (in-run hero level via `rerw write savefile --level 1`); body+0x15 = 0 (accumulated XP, byte-misaligned u32, sat next to the level field). Empirically established the formula `effective_level = hero_level + XP / xp_threshold`: ch2 proof showed 5.54 (lvl=5, XP=2690), `--level 1` alone produced 7.73 on defeat (= 1 + ~6.73 from leftover XP), `--level 1` + XP=0 produced the correct ~5.x baseline. Per-hero lifetime sum that aggregates each run's effective level across runs still TBD — likely in `oCDtHeroProfileData`; deferred. Per-run input to the sum is now fully controllable.
  - **Stars of Fate live edit (the major player-facing hack)**: discovered live spendable Stars-of-Fate count at HeroController body+0x29 (u32, byte-misaligned). Verified spendable in-game with edited baseline=7. This is arguably the most important save-edit win to date — Stars of Fate are the talent-reroll consumable, so editable count = defeat RNG on talent picks.
  - **Promoted three goldens** (chained — each is a stage in the mint round-trip): `golden/geppetto/chapter2/laser-lenses_1/zero-scores-and-level1/` (the v4 zeroed chapter-2 golden, CRC `0xDA0EFBA5` — the zeroed-at-chapter-2-position state); `golden/geppetto/chapter1/zero-scores-stars7-ch1/` (the chapter-1 minted starting save, CRC `0xC14F2CBB` — built with v4 zero-out + Stars=7 + `rerw --chapter 0`); `golden/geppetto/chapter2/2for1-thru-with-inventory/` (the chapter-2 follow-on after playing the chapter-1 minted golden through to chapter-2 boss kill, with held inventory keys/feathers/bean/extra dream-shards). All three have `breakthrough.md` + relevant screenshots. The chapter-1→chapter-2 round-trip is the proof the mint pipeline actually works end-to-end.
  - **Three things still uncontrolled** (documented as known limitations in the goldens' breakthrough docs and consolidated in new triage `rw/triage/save-mint-status.md`): (1) held-inventory byte location unmapped despite empirical persistence (keys carry through save → restart cycles per user test, but no record we diffed shows the bytes), (2) "Raven Feathers consumed" stat stuck at 4 — `body+0x25` writes don't take, mirror-cascade pattern, (3) chapter-achievement records source unmapped — drives a compounding-blanks bug on the score-details page where leftover invalid achievement slots interleave between chapter-1 and chapter-2 active icons.
  - **Ghidra deep dive — ingredient subsystem**: identified + named `oSDtHeroIngredient_Serialize` (vtable[3] @ 0x14037c100), `hero_ingredient_add_or_remove` (FUN_14038c900 — adds/removes by `param_2` int type-id), `find_hero_ingredient_definition_by_id` (matches `*(int *)(*plVar1 + 0x290)` against caller's int), `oCDtIngredientDefinition_ctor`/`_typedesc_init`/`_Serialize` (vtable[3] @ 0x140318cb0), the hash-derivation chain `FUN_1404e73f0` → `FUN_140506950(0, CRC32(string))` that populates the IngredientDefinition's +0x290 type_id from a string at load time. Multiple `serde_vec_*` generic vector serializers named for clarity. Defined `oSDtHeroIngredient` C++ struct in Ghidra. ~20 function/data renames + 20 variable renames + 1 plate comment all persisted in the Ghidra DB. Ingredient wire format = u32 type_id + u16 count (8 bytes per record) — but the type_id values for "Key" / "Bean" / etc. could not be calibrated without a non-empty ingredient vector to anchor on, so add-ingredient editing is blocked until we get a save with non-empty inventory.
  - **Documentation + recipes**: added "Edit recipes" section to `rw/key-findings/save-edit-pipeline-2026-04-30.md` — copy/paste Python scripts for (a) Stars of Fate edit, (b) full mint chain (zero every per-run stat we know how to), (c) diff two saves, (d) splice/insert into a body; documents the gaps in the mint recipe explicitly. Added new CLAUDE.md rules: "Saves are only generated at chapter-boss kills" (with the ~20-min real-time-play cost ceiling), "Ghidra: annotate findings on the spot" (rename functions / data / params / locals / structs / equates immediately, narrative WHY belongs in key-findings not Ghidra comments). Also accepted parallel-agent's CLI design rules + cipher-position confirmations.
  - **Triage cleanup pass**: created new `rw/triage/save-mint-status.md` consolidating the three open mint-recipe questions with hypothesis lists + discriminating tests; cross-references `live-state-mirror-cascade.md`. Trimmed conquered-content out of `rw/triage/geppetto-save-analysis.md` (CRC32, XP, Level, Chapter counters, Stars of Fate all moved out — now in key-findings) and `rw/triage/level-runtime-address.md` (vtable + class layout already in `oe-dynamic-listener-data.md`). Archived `rw/triage/talent-record-discovery.md` to `rw/key-findings/archive/` (was CLOSED).

EXPERIMENTAL-2: Save-edit pipeline + decoder/encoder + nested-body editing (2026-04-30)
  - built `tools/rerw-src/lib/cooked.py`: bidirectional decoder/encoder for the oEngine "Cooked" binary serialization format (used by every `.gen` file in `_Cooking/` and, with a header variant, by `Profile_1.ob` save files); round-trips byte-for-byte across all test corpora (Modal_Save_Or_Quit 2.8 KB, Geppetto herodef 18.9 KB, Hero_Geppetto entity 620 KB, Profile_1.ob saves)
  - identified file structure: 16-byte header (variant: `.gen` carries `"Cooked"` magic, `.ob` carries 4-byte CRC) → `0xAABB1111` class registry → `0xAABB2222` → object section. Per-class metadata is 16 bytes after name: `m_uId` u32, `m_uVersionMaj` u16, `m_uVersionMin` u16, `schema_version` u32, `m_uParentId` u32. `schema_version` (initially mislabeled `field4`) is the version gate Serialize methods compare against
  - confirmed save-file CRC is standard zlib CRC32 over body bytes from offset 0x10 to EOF; verified empirically (`zlib.crc32(data[0x10:]) == stored_hash`) and identified loader's verification path (`save_load_parse_top_level` image+0x64aa50 returning error 4, `crc32_zlib` image+0x505cc0). Encoder auto-recomputes on edit
  - discovered two-tier object structure: top-level instances listed in the leading instance index table + nested sub-objects embedded inside parents' bodies via inline `0xAABB1111`/`0xAABB2222` markers. The wrapper `oCDtGameProfile` lives AFTER the 1199 top-level frames. Most user-visible runtime classes (`oCDtPlayerProfileData`, `oCDtCurrentRunProfileData`, `ActivityScore`, `HeroScoreData`, `HeroMOPersistentData`, all 649+ event listeners) are nested, not top-level
  - reverse-engineered Serialize methods for `oCDtPlayerProfileData`, `oCDtCurrentRunProfileData`, `ActivityScore`, plus the two helper sub-serializers `FUN_1401c5e30` (read 2 strings) and `FUN_140670af0` (read u32 + 2 strings + u32 + optional string). Documented per-field offsets and version gates
  - built recursive `parse_object_tree` walker exposing the nested structure as a `TreeNode` tree with `find_class_in_tree` for class-aware traversal; added `--tree` and `--tree-class` CLI flags
  - confirmed empirically that cross-save record transplant is impractical: object references are u32 indices (`uOjbectId`) into the per-load object pool; `oCBinaryLoader_ReadObjectRef` (image+0x4e7f50) reads them with sentinels `0xFFFFFFFF`=null / `0xFFFFFFFE`=self. Clean and chapter2 saves have different orderings AND different class registries (clean=26 classes, ch2=39), so neither save's bodies hold valid indices in a reassembled file. Naive append-at-end, full-class-replace, and index-aligned strategies all fail. Genuine cross-save migration would require per-class schema knowledge to remap every embedded index — deferred
  - proved nested-body editing works as the actual mechanism for path B (scenario crafting via save edit). Two patterns: (a) replace a nested body with a synthesized minimum that exactly matches the wire format the parser will read (proven on `ActivityScore` with a 25-byte minimum body), (b) zero specific scalar/float fields in place while preserving structural counts and length-prefixed strings (proven on `HeroScoreData` and `HeroController`)
  - mapped the actual storage of every user-visible end-of-run stat by edit-and-test: damage dealt + damage taken + per-source breakdowns live in `oCDtEntityCpntHeroControllerPersistentData` at byte-misaligned body offsets `+0x11`, `+0x15`, `+0x19`, `+0x1d`, `+0x35d`; playtime float lives in `oCDtCurrentRunProfileData` own body at `+0xe5` (also byte-misaligned); `HeroScoreData` and `ActivityScore` are cached snapshots that don't drive the display but are good practice to zero for consistency. Verified end-to-end by build → install → load → abandon → observe; runtime correctly accumulates from zero on next play
  - integrated with existing `rerw write savefile` GUID-locator pipeline (`tools/rerw-src/data/save-fields.yaml`); produced combined edits (zeroed stats + level set to 1 via `--level 1`) that load cleanly with HUD reflecting the new hero level
  - documented the modal-error-4 false-negative gotcha in `CLAUDE.md`: clicking OK on the error modal can route to the Continue/New-Game dialog (load succeeded despite the modal warning) OR to fresh-account hero selection (true failure, quit before next save event clobbers local). All previous test reports stating only "got the error modal" were ambiguous; we re-tested several to discover several "failures" were actually false negatives, and at least one (`transplant_indexed`) was a true failure that wiped local unlocks
  - identified the cumulative "Level reached" stat as a separate, lifetime-accumulating field NOT in any record we touched — likely lives in `oCDtHeroProfileData` per-hero data; deferred
  - new Ghidra renames (persisted): `oCDtPlayerProfileData_Serialize` (0x1401da580), `oCDtCurrentRunProfileData_Serialize` (0x1401da9a0), `ActivityScore_Serialize` (0x1401da440), `oCBinaryLoader_ReadObjectRef` (0x1404e7f50), `save_load_parse_top_level` (0x14064aa50), `save_load_parse_object_section` (0x1404e8690), `save_load_read_header_flags` (0x1404e7c50), `crc32_zlib` (0x140505cc0), plus typedesc init functions and vtable / typedesc data labels for the three reversed classes
  - new key-findings docs: `rw/key-findings/decoder-work-2026-04-30.md` (decoder build plan), `rw/key-findings/save-edit-pipeline-2026-04-30.md` (canonical session findings + `lib.cooked` tool reference + verified stat-source mapping + critical gotchas)
  - cipher.py fix: confirmed and applied position 40 (uppercase `O`) as identity (was `#` unknown), via empirical filename match on `Hrtgl_Fgkq_Ou_Pwdi.qzidis.ri` ↔ `Modal_Save_Or_Quit.entity.ot`; new path-aware helpers `encipher_path` / `decipher_path` and `transform_cooked_path` added to handle full filesystem paths
  - new harvested files for format work: `rw/dumps/modal_save_or_quit/Modal_Save_Or_Quit.entity.ot.EntitySettingsResource.gen` (decoded), `rw/dumps/geppetto/Geppetto.herodef.ot.DtHeroDefinition.gen`; lab edits exercising the pipeline: `rw/saves/edits/lab/{transplant_test,transplant_test_player,transplant_selective,transplant_full,transplant_indexed,edit_test_player,min_activity_scores,zero_activity_scores,zero_scores,zero_scores_v2,zero_scores_v2_level1,remove_activity_scores}/Profile_1.ob`

EXPERIMENTAL-1: Frida save-trigger pipeline + save subsystem RE (2026-04-29)
  - mapped the save subsystem end-to-end via static analysis: `save_request_sync` (image+0x6797b0), `save_request_async` (+0x679760), `save_atomic_orchestrator` (+0x678f30) on the worker thread, single ring queue at `DAT_14143ffc0` semaphore-signaled, atomic write via Temp+CopyFileW (no rename); function map and field offsets captured in the new key-finding
  - identified `oCDtRootGs` as the run-state class, with the embedded IO job at `instance+0x1928`; vtable[0] (= image+0x1c6830) is the unique discriminator used to find heap-allocated instances at runtime
  - built Frida pipeline (`tools/frida/save_now.js`) that locates the live `oCDtRootGs` via vtable-signature heap scan and calls `save_request_sync(NULL, instance+0x1928)` from outside the game; pipeline mechanically works (Profile_1.ob mtime updated, CRC valid, in-game "Now Saving" overlay confirms the trigger goes through the real save path) but produced output is content-incomplete — engine refuses the file as resumable on relaunch
  - root cause: `save_request_sync` does not introspect run state — it queues a write of bytes already at `job+0x30`/`+0x38`. A separate prep/serializer step (location TBD) populates that buffer in the natural save chain. Three-save model surfaced via parallel static work: GameSessionGs root job + profile-manager async at `profile+0x50` + global async at `DAT_14140dd70+8`. Continue-gate may depend on profile-manager / global metadata in addition to the run payload
  - identified the save dialog hook: `FUN_14027fde0` loads `DAT_141410b38` (`Modal_Save_Or_Quit.entity.ot`), stores it at `session+0xf8`, wires a callback pair, and sets UI/game flags — the upstream entry point for the natural save chain
  - debunked the "saves are account-locked" hypothesis: account ID does not appear in any save in any encoding; the cross-account lock is Steam Cloud sync, not in-game logic; documented in `rw/key-findings/save-account-binding.md`
  - new key findings: `rw/key-findings/save-subsystem.md` (architecture, function map, queue ABI, job struct fields), `rw/key-findings/save-account-binding.md` (Steam Cloud as the lock)
  - new tooling: `tools/frida/save_now.js` (save trigger), `tools/frida/diagnose_save.js` (owner-discovery + job-buffer inspection without recursive ref scans), `tools/frida/repl.js` (interactive REPL toolkit), `tools/frida/README.md` (WSL→Windows interop, Frida 17.9.3 API gotchas), `tools/frida/HANDOFF.md` (active-investigation operational doc)
  - new setup doc: `rw/docs/ghidra-windbg-mcp-for-wsl.md`; new top-level config `.mcp.json` registers Ghidra (127.0.0.1:8080) and WinDbg (127.0.0.1:8000) MCP servers
  - new triage docs: `rw/triage/ghidra-rule-c-investigation.md`, `rw/triage/items-add-primitive-cap.md` (engine-validation ceiling for item slot 5)
  - new artifacts: `rw/saves/proofs/geppetto/chapter1/frida-trigger-1/` (Frida-triggered Profile_1.ob + PROVENANCE with byte-level analysis vs chapter-2 known-good), `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/item-add-fill-moonstone-stack-5of5/` (item-add primitive cap test golden)
  - updates: `rw/key-findings/magical-objects.md` (run-state body layout, items count at body+0x59, trailing block structure), `rw/docs/README.md` (linked tools/frida/HANDOFF.md as active investigation marker)
  - next: WinDbg session with hardware watchpoints on the three job buffer pointers + BPs on `FUN_14027fde0` and the chapter-end orchestrators to capture call stacks during a natural Save & Quit click; goal is identifying the prep function(s) and the dialog-trigger chain so the natural save can be invoked without finishing a chapter run

MAINT-12: items-record decode + hero/item YAML schema migration (2026-04-29)
  - decoded the magical-object item record format: tag=0x1a records nested inside the tag=0x12 run-state record, each 32 bytes (marker + tag + 16-byte runtime GUID + u32 sequence counter + close); cataloged 114 entries (68 magical objects + 46 powerups) via `oCDtMagicalObjectProfileData` tag=0x05 records
  - lab-verified items mechanism end-to-end: chapter-2 Save A Vorpal Blade swap (`Kill_Low_Life_Enemies` runtime GUID `cf7d88d6…` → `Avoid_Death_Once_Per_Chapter` runtime GUID `1cc781a5…`); in-game display changed (Vorpal Blade → Water of Life) and the on-revive label flashed during follow-up lethal-damage test, confirming the swapped runtime GUID drives both display and effect resolution
  - identified the Mortar migration ghost: pre-rework Baba Yaga's Mortar entity (`Avoid_Death_Once_Per_Chapter`, Legendary folder) is rerouted via inheritance to `Full_Heal_At_Day_Night.entity.ot` (Water of Life), with the legacy revive effect retained alongside Water of Life's vitality bonus — sole confirmed hybrid in the catalog; new-Mortar effect lives in Cursed/`Destroy_Legendary_To_Damage`
  - runtime-GUID extraction recipe for any item entity file: 16 bytes immediately preceding the `[u32 strlen=22]"Dt Magical Object Data"` anchor; verified against 114-of-114 entity files (5 cross-checked against active save records)
  - new key-finding: `rw/key-findings/item-table.md` (canonical 114-item catalog with effect filename, icon, name-key, catalog GUID, runtime GUID, rarity per row; ghost migration history; verified aliases section)
  - new key-finding (in-flight): `rw/key-findings/save-catalog-flag-bytes.md` (7 distinct 12-byte flag patterns across 114 catalog records; hypothesized MO/Powerup distinction via byte-3 = `0x03` vs `0xff`; per-row attribute interpretation pending)
  - new registry: `tools/rerw-src/data/magical-items.yaml` (68 entries; 67 clean + 1 Mortar ghost block with `displays_as` / `inherits_from` / `meta_notes`; 9 legacy upgrade-pair bases share canonical's `display_name` + `key`; 59 entries fully aliased from Ravenswatch wiki tables (Common/Rare/Epic/Legendary/Cursed))
  - new registry: `tools/rerw-src/data/powerup-items.yaml` (46 entries; `key:` field present, alias values pending helper curation)
  - migrated all 12 hero YAMLs to new schema: `display_name` (player-facing) + `key` (PascalCase, no spaces/punct) + `controller_name` (engine `Skill Controller XXX`) + `guid` + at-most-one marker (`is_start: true` for the 4 starting talents per hero | `is_ult: true` for the 2 base ults | `ult_upgrade_for: "<UltKey>"` for the 4 upgrades) + `desc: |` block (verbatim wiki effect text + `Changes per rarity:` line + rarity changes)
  - dropped the `hero: <Name>` top-level field from hero YAMLs (filename is sufficient)
  - documented the `ult_upgrade_for` derivation rule: SUFFIX number M in `Skill Controller Ultimate N Upgrade M` determines the parent ult (Upgrade M → `Ultimate Power M`'s key), NOT the prefix N — fixes an incorrect presumption in `talent-records.md` that paired by the prefix
  - all 12 hero files populated from Ravenswatch wiki tables (28 talents per hero × 12 heroes = 336 entries); display_name + desc + rarity_changes verbatim from wiki
  - rerw CLI integration deferred: registry YAMLs ready for `rerw read savefile --items` and `rerw write savefile --item-slot N --item-id <id>` but not yet wired in `commands/{read,write}_savefile.py`

PRP-2: rerw talent + tier edit primitives (2026-04-28)
  - decoded the talent record (tag=0x12) and tier byte (tag=0x10) for Geppetto saves: 5×16-byte talent GUIDs at the talent-pick block (anchored by `[u32=0][u32=5]` sentinel), plus a u8 tier byte at offset GUID+17 of each first-occurrence tag=0x10 record
  - verified end-to-end with 3 lab swaps on the chapter-2 Geppetto proof — talent swap (slot 1: Special Creates Dummy → Trait Twins, displayed as Common), tier edit (Dummy Ball Common → Legendary), combined edit (slot 1 → Trait Twins at Legendary); all three landed as goldens at `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/talent-slot1-*` with `info.md` per mod
  - tier-value mapping: `0=Common, 1=Rare, 2=Epic, 3=Legendary, 4=ult-marker` (slot 5 ult uses ult-marker, no real tier)
  - extended the YAML field registry with a new `talent_picks` field type (record_guid + sentinel + slot_count + skills_data_dir); `lib/save_fields.Field` now carries an `extra` dict for type-specific metadata
  - new `lib/talent_edit.py` with `find_talent_record`, `find_picks_anchor`, `read_picks`, `write_pick`, `find_tag10_record`, `read_tier`, `write_tier`, `parse_tier`, and `detect_hero` (parses `Heroes\<Name>.herodef.ot` from the save body)
  - new `lib/skill_controllers.py` loader for per-hero YAMLs with case/punctuation/prefix-insensitive resolver (`_normalize` strips "Skill Controller " prefix and collapses whitespace/dashes/underscores), defensive alias cleanup at load time (skips empty/null/duplicate/redundant-with-canonical entries)
  - `rerw write savefile`: new `--talent-slot N`, `--talent-id <name|alias|guid>`, `--tier <name|0..3>` flags; combined edits run atomically (one CRC pass); slot 5 rejects `--tier`; talent + tier edits route to the *current* slot occupant's tag=0x10 record (so swapping a slot's talent + tier in one invocation works correctly)
  - `rerw read savefile`: new `--talents` flag printing slot picks with hero auto-detected, alias-preferred display, tier name + hex byte
  - harvested all 12 hero herodef binaries from the cooked game install (`Heroes/<Name>.herodef.ot.DtHeroDefinition.gen` after substitution-cipher decode), generated `tools/rerw-src/data/heroes/<hero>.yaml` for each — 28 skill-controller GUIDs per hero (336 total); Geppetto YAML has 7 verified player-facing aliases from gameplay (Twin Dummies, Family Meeting, Clockwork Medicine, Sharp Noses, Overclock, Dummy Ball, Laser Lenses), other heroes ship with empty alias lists pending external curation
  - new key finding `rw/key-findings/talent-records.md` (full byte layout, GUID encoding, tier mapping, the L1–L10 leveling table, all 28 Geppetto controllers); updated `save-binary-format.md` to point to it; consolidated talent-name reference at `rw/key-findings/talents.md`
  - investigation history at `rw/triage/talent-record-discovery.md` (covers ruled-out hypotheses including the body+0x35 u32 false lead and the base64 run-id blob)
  - new chapter-2 proof save `rw/saves/proofs/geppetto/chapter2/twin-dummies-all-legendary-talents/Profile_1.ob` (Twin Dummies / Family Meeting / Clockwork Medicine / Sharp Noses / Overclock, all 4 tiered talents at Legendary)
  - verified scope: slots 1–5 only on Geppetto saves; slots 6–10 (L6–L9 regular picks + L10 ult upgrade) and cross-hero generality are unverified — flagged as follow-ups in the key-finding doc

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
