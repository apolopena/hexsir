[← Back to docs](README.md)

# Playbook

Directory structure, conventions, and workflow for Ravenswatch RE.

## Directory Structure

```
rw/
├── docs/                       # tracked
│   ├── README.md
│   ├── playbook.md
│   └── tools/
├── ref/                        # tracked — reference data
│   ├── tree-ciphered.txt       # game asset tree (source of truth)
│   └── tree-deciphered.txt     # deciphered, for human reading
├── harvested/                  # gitignored — raw game binaries copied for analysis
├── dumps/                      # gitignored — raw working analysis outputs
├── triage/                     # tracked — in-flight analysis docs (Sources header required)
├── key-findings/               # tracked — confirmed artifacts promoted from triage/dumps
└── saves/
    ├── proofs/                 # tracked — baseline original saves
    │   └── <hero>/<chapter>/<run-id>/Profile_1.ob
    ├── edits/
    │   ├── lab/                # gitignored — WIP test modifications
    │   └── golden/             # tracked — verified non-mint modifications
    │       └── <hero>/<chapter>/<run-id>/<mod-id>/Profile_1.ob
    └── mints/                  # tracked — verified saves built via `rerw mint savefile`
        └── <hero>/<source-chapter>/<run-id>/<mod-id>/{Profile_1.ob, info.md}
```

## What Goes Where

| Category | Folder | Tracked? | Examples |
|----------|--------|----------|----------|
| Reference data | `ref/` | Yes | Asset tree files |
| Raw game files | `harvested/` | No | `.gen` binaries, encoded assets |
| Raw analysis | `dumps/` | No | hex dumps, string extracts, raw tool output |
| In-flight analysis | `triage/` | Yes | Working analysis docs with Sources header |
| Confirmed findings | `key-findings/` | Yes | Curated facts extracted from triage |
| Original saves | `saves/proofs/` | Yes | Baseline `Profile_1.ob` snapshots |
| Test modifications | `saves/edits/lab/` | No | Experimental save edits |
| Verified non-mint mods | `saves/edits/golden/` | Yes | Save edits confirmed working in-game whose build chain does NOT include `rerw mint savefile` |
| Verified mints | `saves/mints/` | Yes | Verified saves whose build chain includes `rerw mint savefile`. The mint command zeros held currencies, per-run stats (damage, time, etc.), end-of-run score-page values + achievements, level/xp, and chapter; later chain steps may override specific fields. |

## Promotion Paths

Five flows:

1. **`dumps/` → `triage/`** — When raw analysis is worth a writeup, create a triage document. Use the `rw-triage-report` skill.
2. **`triage/` → `key-findings/`** — When findings firm up, extract them as curated artifacts.
3. **`saves/edits/lab/` → `saves/edits/golden/`** — When a verified lab's build chain does NOT include `rerw mint savefile`, promote here. The mod is "golden" (canonical, regression-stable).
4. **`saves/edits/lab/` → `saves/mints/`** — When a verified lab's build chain DOES include `rerw mint savefile`, promote here as a "mint." Mints are first-class artifacts, not refinements of goldens — the mint chain (proof → mint → customization) is the distinguishing property.
5. **`rw/scripts/` → `rerw` CLI** — When a hand-edit script's behavior is verified in-game via a lab save, lift its logic into the CLI. See "CLI Promotion" below.

Demotion is also fine. Something in `key-findings/` that turns out wrong moves back to `triage/` or gets deleted.

## Triage Documents

Working analysis writeups that may contain a mix of confirmed findings and open questions. They sit between raw `dumps/` and curated `key-findings/`, providing a tracked place for in-flight research with provenance back to source files. As findings firm up, the confirmed bits get extracted to `key-findings/`; the document shrinks or is deleted as its contents get absorbed.

Use the **`rw-triage-report` skill** to create them — invoke with "create a triage report for this..." or similar. The skill handles formatting and enforces the Sources header. Do not hand-write triage docs.

## File Naming

- **Save files always named `Profile_1.ob`** — the game expects this filename. Never rename. Encode the variant identity in the directory path (e.g., `level99/`, `max-shards/`).
- **Asset filenames preserve the `!` separator** — game uses `!` in filenames (e.g., `Hero_Geppetto!Hero_Geppetto.entity.ot.EntitySettingsResource.gen`). Keep it.

## Save Directory Conventions

All three save artifact types — labs, goldens, and mints — are organized by the **source hero** of the save (not the post-edit hero, even when the edit changes the hero). Source hero keeps lineage traceable.

### Definitions

- **Lab** — a work-in-progress save edit, gitignored. The arena for trying things.
- **Golden** — a verified save edit whose build chain does NOT include `rerw mint savefile`. Promoted from a lab once the in-game test passes. Goldens preserve some per-run state from the source proof (currencies, scores, etc.).
- **Mint** — a verified save edit whose build chain DOES include `rerw mint savefile`. The mint **command** produces a fresh chapter-1 starting state. It zeros: held currencies (Dream Shards, Stars of Fate, Raven Feathers, Nightmare Keys); per-run stats (damage dealt, time played, dream shards earned, feathers consumed); the end-of-run statistics page (score floats, chapter-progression banner, ActivityScore achievement records); level (→1) and xp (→0); and chapter (→1). Subsequent chain steps may override specific fields (e.g., a later `level 14` step overrides mint's level=1). The final artifact is called a "mint" because the chain *includes* the mint command, not because every stat in the file is necessarily zero. The label reflects the chain type, not a refinement step beyond golden.

### Path conventions

- **Lab:** `saves/edits/lab/<hero>/<run-name>/<descriptive-mod-id>/Profile_1.ob`
  - Lighter than golden (no chapter level — chapter is encoded in the mod-id when relevant, e.g. `level-downgrade-from-ch2/`).
  - The run-name mirrors the source proof's run-name exactly (don't normalize dash-vs-underscore inconsistencies across proofs).
  - Gitignored, so renames are free.

- **Golden:** `saves/edits/golden/<hero>/<chapter>/<run-id>/<mod-id>/Profile_1.ob`
  - `<chapter>` is the **post-edit** chapter the save loads to.
  - `<mod-id>` describes the post-edit flavor.
  - When the source proof's chapter differs from the post-edit chapter, encode the source in the mod-id (e.g., `mint__from-chapter3-laser_lenses_1-proof/`).

- **Mint:** `saves/mints/<hero>/<source-chapter>/<run-id>/<mod-id>/{Profile_1.ob, info.md}`
  - `<source-chapter>` is the SOURCE proof's chapter. Mints by definition output chapter 1, so source-chapter is the more informative axis.
  - `<mod-id>` describes the post-mint customization flavor (e.g., `romeo-pickscount0-all10-legendary`). No `__from-...` suffix — the source is encoded by the path.
  - Each mint dir contains both `Profile_1.ob` (the save) AND `info.md` (the recipe — what the mint is, plus the commented command list). The `info.md` is **required**, not optional.

### Examples

- A lab swapping Geppetto → Carmilla lives under `lab/geppetto/<run>/hero-swap-to-carmilla/`, because the file was *derived from* a Geppetto proof. Mod-id describes the change.
- A mint built from a chapter-2 Geppetto proof, customized to Romeo at level 14, lives under `mints/geppetto/chapter2/<run-id>/romeo-pickscount0-all10-legendary/`. The `<source-chapter>` is `chapter2` (proof's chapter), even though the mint's output is chapter 1.

### Hygiene

**Delete failed tests; don't preserve them as `<mod-id>-failed/`.** A polluted lab makes it impossible to tell verified-but-not-yet-promoted edits from known-broken ones across sessions. Capture failure outcomes in the relevant key finding (e.g., the "Misidentified" subsection in `save-binary-format.md`) and remove the lab artifact. Negative results live in docs, not in the lab tree.

## CLI Promotion

A code change to the `rerw` CLI requires in-game verification of the underlying edit primitive **before** the code change. The flow:

1. Author the edit as a one-shot script in `rw/scripts/<descriptive-name>.py` (committed; not `rw/dumps/`).
2. Use the script to build a lab save in `rw/saves/edits/lab/<hero>/<run>/<mod-id>/Profile_1.ob`.
3. User loads the lab save in-game and verifies intended behavior.
4. **Only after sign-off**, lift the script's logic into `tools/rerw-src/lib/<lib>.py` and expose via `tools/rerw-src/commands/<group>.py`.
5. Promote the verified lab save to `saves/edits/golden/` as a regression artifact.

Skipping step 3 (running script logic straight into the CLI without an in-game lab pass) is **not allowed**. The CLI is the contract surface — it ships changes that have been verified, not changes that look correct.

The same rule applies in reverse for CLI bug fixes: if the fix changes behavior, build a lab demonstrating the new behavior, verify in-game, then commit.

**Delete failed tests; don't preserve them as `<mod-id>-failed/`.** A polluted lab makes it impossible to tell verified-but-not-yet-promoted edits from known-broken ones across sessions. Capture failure outcomes in the relevant key finding (e.g., the "Misidentified" subsection in `save-binary-format.md`) and remove the lab artifact. Negative results live in docs, not in the lab tree.

## Tree Files

`tree-ciphered.txt` is the source of truth — game updates can change asset structure. Regenerate with Windows `tree /A /F` (the `/A` flag avoids encoding issues with box-drawing characters).

`tree-deciphered.txt` is derived for human readability. Regenerate from ciphered version using `rerw`.

## Workflow

1. Identify a target file in the deciphered tree.
2. Copy it from the game directory into `harvested/` (decode the path with `rerw decipher`).
3. Analyze. Raw outputs go to `dumps/`.
4. When analysis is worth a writeup, create a triage document (use the `rw-triage-report` skill).
5. As findings in triage firm up, extract them as curated artifacts in `key-findings/`.
6. For save modifications: edit in `saves/edits/lab/`, test in-game, promote successful results to `saves/edits/golden/`.

## External references

- **Ravenswatch wiki — Heroes:** [https://ravenswatch.fandom.com/wiki/Heroes](https://ravenswatch.fandom.com/wiki/Heroes) — canonical hero list with abilities, talents, and game-side names. Useful for cross-checking asset names from the deciphered tree against in-game terminology, and for resolving hero-specific terminology questions during save analysis.

## Documentation

Rules for files inside `rw/docs/`:

- **`README.md` is the index** for its directory. It contains a short intro and a TOC linking to siblings and subdirectory READMEs.
- **Every doc except `README.md` has a backlink** to its directory's README. Place it on the very first line, above the `# Title` header, formatted as `[← Back to <parent>](<path>)`.
- **Index entries (TOCs) state purpose, not contents.** Don't list specific commands, options, or section names of a doc in its TOC entry — that creates maintenance churn when the underlying doc changes.
- **Defer to skills and tools rather than duplicate their formats.** If a skill or tool defines a structure (like the triage doc format), reference it instead of restating it.
- **No paths to the host filesystem** (Windows game directories, Steam paths, etc.). Those are operator concerns, not documentation.
