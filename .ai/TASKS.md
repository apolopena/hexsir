# TASKS.md — Running Ledger

> **Task Codes:** POST-IMPL-X for substantial implementations | MAINT-X for maintenance (fixes, tweaks, refactoring)
>
> **Ordering:** Newest entries at top.
>
> **Scope:** Describe work, not results. Keep test/lint pass counts and coverage totals out. Mention tests only when the work is authoring or refactoring them.

---

## In Progress
<!-- IN_PROGRESS_START -->
- *(empty)*
<!-- IN_PROGRESS_END -->



## Done
<!-- DONE_START -->
- [x] MAINT-2: Scaffold Ravenswatch RE workspace and rerw tool (2026-04-25) — relaxed scafcli naming to make `cli` suffix optional; renamed `hexsircli` → `hexsir`; created `rerw` tool with `cipher`, `decipher`, and `harvest` (group stub) plus shared `lib/cipher.py`; established `rw/` workspace (`ref/`, `harvested/`, `dumps/`, `triage/`, `key-findings/`, `saves/{proofs,edits/{lab,golden}}`) with `.gitignore` rules; wrote `rw/docs/{README,playbook,tools/}` documenting structure, promotion paths, workflow, and doc conventions; added `rw-triage-report` skill; migrated `interim/` content into `rw/`; converted `ANALYSIS_SUMMARY.txt` into `rw/triage/geppetto-save-analysis.md`; marked `.ai/docs/rw/` deprecated; registered `rerw` in `prime-full-tooling.md` and `scripts/run-tests.sh`
- [x] MAINT-1: Initial hexsircli and repo branding (2026-04-23) — added `tools/hexsircli` and `tools/hexsircli-src/` with commands (basic, header, scan, verify); registered in `scripts/run-tests.sh`; updated README.md with Hexsir branding; configured `.claude/commands/prime-full-tooling.md` and `prime-quick-tooling.md` (Tool Suite: hexsircli, scafcli; Indexed-only: scripts/run-tests.sh); updated `.gitignore` with Python build artifact patterns; removed project-specific scafcli tests
<!-- DONE_END -->
