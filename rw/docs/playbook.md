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
    └── edits/
        ├── lab/                # gitignored — WIP test modifications
        └── golden/             # tracked — confirmed-working modifications
            └── <hero>/<chapter>/<run-id>/<mod-id>/Profile_1.ob
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
| Verified mods | `saves/edits/golden/` | Yes | Save edits confirmed working in-game |

## Promotion Paths

Three flows:

1. **`dumps/` → `triage/`** — When raw analysis is worth a writeup, create a triage document. Use the `rw-triage-report` skill.
2. **`triage/` → `key-findings/`** — When findings firm up, extract them as curated artifacts.
3. **`saves/edits/lab/` → `saves/edits/golden/`** — When a modified save runs successfully in the game, promote it.

Demotion is also fine. Something in `key-findings/` that turns out wrong moves back to `triage/` or gets deleted.

## Triage Documents

Working analysis writeups that may contain a mix of confirmed findings and open questions. They sit between raw `dumps/` and curated `key-findings/`, providing a tracked place for in-flight research with provenance back to source files. As findings firm up, the confirmed bits get extracted to `key-findings/`; the document shrinks or is deleted as its contents get absorbed.

Use the **`rw-triage-report` skill** to create them — invoke with "create a triage report for this..." or similar. The skill handles formatting and enforces the Sources header. Do not hand-write triage docs.

## File Naming

- **Save files always named `Profile_1.ob`** — the game expects this filename. Never rename. Encode the variant identity in the directory path (e.g., `level99/`, `max-shards/`).
- **Asset filenames preserve the `!` separator** — game uses `!` in filenames (e.g., `Hero_Geppetto!Hero_Geppetto.entity.ot.EntitySettingsResource.gen`). Keep it.

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

## Documentation

Rules for files inside `rw/docs/`:

- **`README.md` is the index** for its directory. It contains a short intro and a TOC linking to siblings and subdirectory READMEs.
- **Every doc except `README.md` has a backlink** to its directory's README. Place it on the very first line, above the `# Title` header, formatted as `[← Back to <parent>](<path>)`.
- **Index entries (TOCs) state purpose, not contents.** Don't list specific commands, options, or section names of a doc in its TOC entry — that creates maintenance churn when the underlying doc changes.
- **Defer to skills and tools rather than duplicate their formats.** If a skill or tool defines a structure (like the triage doc format), reference it instead of restating it.
- **No paths to the host filesystem** (Windows game directories, Steam paths, etc.). Those are operator concerns, not documentation.
