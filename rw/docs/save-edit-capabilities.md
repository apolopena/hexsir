[← Back to docs](README.md)

# Save-edit capabilities

Reference inventory of every Ravenswatch save modification this project can perform today. Three categories:

1. **CLI one-liners** — wrapped as `rerw <command>` subcommands. Run as-is.
2. **Proven save edits without a CLI** — mechanism fully decoded and verified end-to-end with at least one golden save under `rw/saves/edits/golden/`, but no `rerw` subcommand exists yet. Reproduction requires adapting the one-off recipe documented in the linked key-finding.
3. **Genuinely unmapped** — fields whose location or wire format is still unknown.

Two real-world gotchas at the bottom apply to every category.

---

## 1. CLI one-liners

| Save modification | Command |
|---|---|
| Held Dream Shards (HUD spendable) | `rerw write savefile shards <number>` |
| Held Raven Feathers (revives) | `rerw write savefile feathers <number>` |
| Held Nightmare Keys¹ | `rerw write savefile keys <number>` |
| Stars of Fate (talent reroll currency) | `rerw write savefile stars <number>` |
| In-run hero level | `rerw write savefile level <number>` |
| Accumulated XP | `rerw write savefile xp <number>` |
| Talent in slot 1–5 | `rerw write savefile talent --slot N --key <TalentKey>` |
| Talent tier (`common` / `rare` / `epic` / `legendary`) | `rerw write savefile tier --slot N --tier <name>` |
| Chapter (1, 2, 3, 4=epilogue) | `rerw write savefile chapter <1-4>` |
| Mint a clean chapter-1 starter from a chapter-boss save | `rerw mint savefile --source X --dest Y` |
| Swap a save into the live game slot | `rerw swap savefile --source X` |

¹ The `keys` subcommand updates an existing Nightmare Keys record's count. On a save with **zero** existing keys (no record present), `keys 0` is a no-op success but `keys N>0` errors — inserting a new record is in the deferred category below.

### Discovery commands

| Lookup | Command |
|---|---|
| All 12 playable heroes (display name + key + engine name) | `rerw game-assets inspect heroes` |
| Every talent for a given hero (e.g. 28 for Geppetto) | `rerw game-assets inspect talents --for-hero <hero>` |
| All 68 magical objects | `rerw game-assets inspect items` |

The discovery commands are the canonical source of valid `<TalentKey>` and `<ItemKey>` values for the writer subcommands. Display names and aliases are not accepted by the strict-key registry — keys are exact-match only.

### Run-state cleanup performed by `rerw mint savefile`

These changes are applied automatically by mint and require no separate command. Listed here for completeness because they are real save modifications:

- Score-page floats (damage dealt, damage taken, per-source breakdown) zeroed.
- Activity scoreboard records removed; parent count u32 zeroed. Suppresses the chapter-summary panel that would otherwise carry over icons from the source save's chapter.
- Chapter-progression banner u32 (the I / II / III markers and death-X displayed on the run-end screen) zeroed.
- Run playtime float zeroed.
- Dream Shards earned (HC body +0x19, float32) and Dream Shards spent (HC body, dynamic offset, float32) zeroed.
- Held Feathers (CRP body +0x15D, u32) zeroed.
- Held Keys (existing record's count u32) zeroed.
- Held Dream Shards (HC body +0x1D, float32) zeroed.
- Stars of Fate zeroed.
- Hero level set to 1; XP set to 0.

After mint, any of the CLI one-liners above can be applied to set per-field baselines (e.g. `rerw write savefile stars 7`).

---

## 2. Proven save edits without a CLI

These have at least one verified-working golden save in `rw/saves/edits/golden/`. The byte-level recipe is documented in the cross-referenced key-finding doc; reproducing the edit today requires adapting the one-off script that produced the golden.

### Hero swap

Replace the playable hero in a save (e.g. swap a Geppetto run for a Carmilla, Aladdin, Snow Queen, or Red run).

- **Status:** verified end-to-end across 4 swaps from a chapter-2 Geppetto proof. All 12 heroes are reachable; the engine tolerates body shifts across `−5` to `+2` bytes induced by name-length differences. Same-length names (Carmilla, Melusine vs Geppetto = 26 chars) are byte-for-byte drop-ins with no shift.
- **On-load behavior:** slot 1 auto-populates with the new hero's L5 ultimate; slots 2/3/4/5 are cleared. Health, run state, and chapter position carry over from the source.
- **Recipe:** `rw/key-findings/hero-swaps.md` (length-prefixed splice into the `Heroes\<Name>.herodef.ot` reference) + `rw/key-findings/hero-table.md` (per-hero name length + shift offset).
- **Goldens:** `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/hero-swap-to-{aladdin,carmilla,red,snow_queen}/`.
- **Ledger entry:** MAINT-8.

### Magical object — add

Insert a magical object (any of the 68 — Dragon's Hide, Vorpal Blade, Moonstones, etc.) into a run's held inventory.

- **Status:** 1 verified golden. Format fully decoded.
- **Recipe:** `rw/key-findings/magical-objects.md` (tag=0x1a active-item records nested in the tag=0x12 run-state record; 32 bytes per record: marker + tag + 16-byte runtime GUID + u32 sequence counter + close).
- **Goldens:** `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/item-add-fill-moonstone-stack-5of5/`.

### Magical object — swap or remove

Replace one magical object with another, or remove a record entirely.

- **Status:** format decoded but no proof-golden yet. Mechanism is the same record format as add.
- **Recipe:** `rw/key-findings/magical-objects.md`.

### Insert Nightmare Keys record into a zero-keys save

The CLI's `rerw write savefile keys <N>` errors for `N>0` on a save with no existing keys record. Implementing this requires inserting a 20-byte framed `oSDtHeroIngredient` record into the HC body's HeroIngredient vector, incrementing the vec count u32, and (for fully empty saves with no class entry) adding `oSDtHeroIngredient` to the class registry.

- **Status:** designed but not exercised. The class-registry insertion path is untested; risk of shifting class indices for unrelated records.
- **Workaround:** layer on a save that already has at least one keys record (e.g. test3-mint).

---

## 3. Genuinely unmapped

| Field | Notes |
|---|---|
| Random-seed system | Drives per-chapter room layout. Bytes not located. Triage doc: `rw/triage/random-seed-system.md`. Investigation deferred. |
| HC body +0x11 and +0x15 (two floats) | Sit adjacent to the dream-shards block. Likely damage-dealt and damage-taken per-run stats, but not rigorously confirmed. Mint zeros them as part of the 16-byte block at HC+0x11..+0x21. |
| Held wood, held bean, other ingredient-type held resources | Only Dream Shards (HC+0x1D), Raven Feathers (CRP+0x15D), and Nightmare Keys (HeroIngredient vec) are mapped. |
| Lifetime cumulative stats (total deaths, total runs, lifetime "Level reached") | Likely live in `oCDtHeroProfileData`. Not mapped. |

---

## Real-world gotchas

These do not limit *what* can be edited; they limit *when and how* edits stick on disk.

### Saves are only generated at chapter-boss kills

Ravenswatch writes a new `Profile_1.ob` only when a chapter boss is defeated and the player chooses to save. There is no autosave, no quicksave, no save-on-death, and no save-on-quit. Implications:

- "Edit → swap → play → save → re-inspect" round-trips are not possible mid-run. Mid-run state changes never make it back to disk.
- Verifying an edit means visually confirming the loaded HUD or score page reflects the edited value. There is no automated round-trip check beyond the parse-encode byte-equality test on the file itself.
- Reaching a new chapter-boss kill to generate fresh save data is roughly a 20-minute play investment. Existing proof saves under `rw/saves/proofs/` are scarce and should be treated as such.

### Steam Cloud and the swap-while-running clobber

Ravenswatch saves are subject to two distinct overwrite hazards:

1. **Cloud-sync on quit.** When the game exits, Steam syncs cloud → local, restoring whatever the cloud copy holds. Local edits made before or during a session get reverted on quit. Persistent edits require either disabling Steam Cloud sync for Ravenswatch (Steam → Library → Ravenswatch → Properties → uncheck "Keep games saves in the Steam Cloud") or accepting that swaps are session-scoped only.
2. **Mid-session swap clobber.** Swapping the savefile while the game is running has no effect on the active session — the game holds its own in-memory state and does not re-read `Profile_1.ob`. Worse: when the game later exits, it writes its in-memory state to disk, overwriting the swapped file with fresh-account defaults. **Always close the game fully before any swap.**

### The save-load error modal is sometimes a false negative

Clicking through the "Save Loading Error (Error code: N)" modal can route to either the fresh-account hero-selection screen (true failure — game treats the file as unreadable; quit immediately to preserve local) or the Continue / New Game dialog (false negative — the save loaded successfully, modal was a non-fatal warning). Always click through and observe the destination before concluding a test result.

---

## Cross-references

- `tools/rerw-src/lib/setters.py` — the pure setter functions backing both `rerw mint savefile` and `rerw write savefile <field>`.
- `tools/rerw-src/lib/save_mint.py` — mint orchestrator.
- `tools/rerw-src/lib/hc_walker.py` — runtime walker that resolves chapter-shifting offsets in the HeroController body.
- `tools/rerw-src/lib/game_registry.py` — strict-key registry over heroes / talents / magical items.
- `rw/key-findings/save-edit-pipeline-2026-04-30.md` — canonical pipeline reference.
- `rw/key-findings/held-dream-shards.md` — bytefield reference for HC+0x1D.
- `rw/key-findings/hero-swaps.md` — hero-swap byte recipe.
- `rw/key-findings/magical-objects.md` — magical-object record format.
- `rw/docs/playbook.md` — directory structure, lab naming convention, save-file taxonomy.
