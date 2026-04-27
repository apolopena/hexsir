# Changelog

All notable changes to this package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.2.0] - 2026-04-27

**FEAT:** *save-file editing*

- `read savefile --source FILE [--chapter] [--level] [-v]` — print registered field values from a save. No field flags prints all; field flags filter to specific fields. Reports `<not present>` for fields whose GUIDs don't appear in the save (e.g. clean profiles).
- `write savefile --source FILE --dest DIR [--chapter N] [--level N] [-f] [-v]` — edit one or more fields atomically: locate all GUIDs, write all values, recompute CRC32 once, write `Profile_1.ob` into `--dest`. Prompts before overwriting unless `--force` / `-f`.
- Default output prints `Source savefile: <path>` header on both commands, plus per-field `<name>: <old> -> <new>` and `CRC32: <old> -> <new>` lines on write. `--verbose` / `-v` adds a load summary (`<size> bytes, CRC=0x...`) and, on write, per-GUID locate + write detail (`GUID <hex> located at 0x... -> writing int32 LE <N> at 0x... (was <M>)`).
- New top-level Click groups `read` and `write` mirror the existing `swap` group; the `savefile` subcommand is registered under each via `cli.add_command()`.
- New YAML field registry at `data/save-fields.yaml` maps field name to (type, GUIDs), top-level grouped by shape (`scalar:` populated with `chapter` and `level`; `array:` and `ref:` reserved for future inventory / item-id work). Adding fields to the registry does not auto-expose CLI flags — flags are wired explicitly in code.
- `lib/save_fields.py` loads and validates the registry (`Field` dataclass, `SaveFieldsError`); `lib/save_edit.py` carries the pure read / write / CRC primitives (no Click).
- REPL hooks for the new commands deferred (TODO marker placed near the existing `swap-savefile` builtin).

**CHORE:** *deps*

- Add `pyyaml` dependency (registry loader).

---

## [0.1.0] - 2026-04-25

**FEAT:** *initial-release*

Initial scaffolded tool.

**FEAT:** *swap-savefile*

- `swap savefile --source PATH [--dest PATH]` — install a save as `Profile_1.ob` in `$RERW_SAVEGAME_DIR` (default: WSL path to Ravenswatch's `_Save`).

**FEAT:** *interactive-repl*

- `interactive` launches a `repl-lib` REPL.
- Built-in `swap-savefile` enters `rerw:swap-savefile>` sub-mode (flag-only input) or runs inline when flags are supplied.
- `exit` is context-aware: leaves the sub-mode first, then quits the REPL.

**CHORE:** *polish*

- Description set to "Ravenswatch reverse engineering tool".
- 35 unit tests, 83% coverage (commands and lib at 100%).
