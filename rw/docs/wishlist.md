[← Back to docs](README.md)

# Wishlist

Future-work ideas that come up mid-session and shouldn't drift into the void. Not commitments — just things to consider when the time is right. Add freely, no codes or headers required. When an item is picked up, move it to `.ai/TASKS.md` (with a task code) and delete it here.

---

## CLI surface

- **Per-stat individual setters.** `save_mint.setters` has primitives for editing playtime, score floats, damage-dealt, chapter-progression banner, ActivityScore records, dream-shards-earned, feathers-consumed, dream-shards-spent, etc. None are exposed as standalone `rerw write savefile <field>` commands — they only fire wholesale via `rerw mint savefile`. Open up surgical control for any of those if a use case arises.
- **`rerw mint savefile` flavor flags.** Right now mint zeroes everything. A flag like `--keep-playtime` or `--keep-scores` could selectively preserve fields. Useful if we ever want a partial mint.
- **Mint chain shortcut.** `rerw mint savefile --hero romeo --level 14 --rarity legendary --clear-picks` would collapse the current 6-step chain into one call. Worth it if Romeo-style mints become a frequent pattern.

## Investigations / digs

- **Continue-vs-new-game gate.** What marker the engine reads at title-screen time to decide whether to show "Continue" on the main menu. Blocks the clean-save splice path — without it `add-level-record` and any "build a save from scratch" workflow can't produce loadable saves. Tracked in `rw/findings/frida-pipeline-hardware-breakpoint.md` "Parallel investigation."
- **Master chapter seed location.** Test plan in `.ai/scratch/master-seed-test-steps.md`. Capture the displayed seed format, Frida-save, byte-search the dump for LE/BE/ASCII encodings, document offset.
- **Item picker / chest / Sandman shop RNG harness.** Clone `tools/frida/force_seed.js` for non-talent picker entry functions. Mechanical once each entry RVA is known. Per `rw/findings/random-seed-system.md`.
- **Save prep/serializer function (Frida).** Hook `oCMemoryBinaryStream::Write` (image+0x5257d0) with a counter, log `Thread.backtrace()` on call #1 only — captures the chapter-end serializer entry that Ghidra's static xrefs can't see. Per `rw/findings/frida-pipeline-hardware-breakpoint.md`.
- **Host-mutates-peer in-run state (MP).** With shards proven (host writes `HC+0x1590` raw, peer's per-frame `HC_per_frame_update` watcher detects + dispatches, replication propagates), generalize the pattern: which other peer-character state lives in host-authoritative replicated stat blocks the host can write? Concrete target: in-run effects of Stars of Fate (the buffs / extra slots / damage modifiers applied at chapter init from the peer's profile). If those effects land in a replicated structure host has write access to, host can grant "buffs as if SoF were unlocked" to all peers in-run. Untested. Investigation surface: trace where peer's chapter-init profile-load lands SoF-derived modifiers in HC's struct, identify whether they're in replicated regions, attempt host-side write + observe peer-side effect. (Persistence is out of scope — MP doesn't fire save events; in-run only.) Per `rw/findings/multiplayer-host-authority.md`.
- **GUID hash-tail reversal.** The 4-byte tails of save-record keys (Level: `5793e600`, etc.) are likely a hash. Crack the hash function so we can mint arbitrary save-record keys for asset paths. Per `rw/findings/save-guid-hash-tail.md`.
- **Live source-of-truth pin identity.** All known stat pins are mirrors, not authoritative. Trace `IDynamicValueListenerData` callback chain backwards from any listener instance. Per `rw/findings/pin-identity-uncertain.md`.
- **Remaining held resources.** Wood, bean, and other ingredient-type held resources don't have located fields. Walk HC/CRP serde to find them. Per `rw/findings/save-mint-status.md` item 2.
- **Per-hero verification of the talent record format.** Currently verified only for Geppetto. Run the lab-build / verification cycle on a non-Geppetto save to confirm the structure generalizes (talent-records.md notes this is presumed but unverified).
- **Boss-rush mod (live, Frida).** Stay in chapter 1, fight Map Bosses 1→2→3→(4) back-to-back with no chapter transitions. Architecture mapped end-to-end in `rw/findings/chapter-map-and-boss-spawn-architecture.md` — encyclopedia primitive (`findEntitySettings("Map_Boss_Spawner_<Chapter>")`), refcounted `Sc_RequestSyncLoadData`, swap the spawner's bound prefab handle, re-fire `0x17d8d901`. Three integration TODOs before it works: (i) resolve the encyclopedia type-tester vtable address at runtime, (ii) verify the bound-prefab field offset on a live `Map_Boss_Spawner_<Chapter>` instance (the universal pattern is `parent[+0x8C0][i]+0x1f0`), (iii) suppress chapter-end on non-final kills. Master pseudocode in the finding's "Master picture" section.
- **Encyclopedia name-key dump tool (Frida).** Two paths: hook `EntitySettingsEncyclopedia_registerByName @ 0x6eb7e0` to capture future registrations, or walk the Swiss-Tables hashmap directly at `encyclopedia + 0x28` (control bytes ptr at `+0x00`, entries at `+0x08` of stride `0x18`, count at `+0x10`, capacity-mask at `+0x18`; entry `+0x10` holds the `oCEntitySettingsResource*`). Layout fully decoded in the finding doc. Combine with `rw/ref/tree-deciphered.txt` (filter to `*.entity.ot.EntitySettingsResource.gen`) for ground-truth catalog cross-check. Generalizes well beyond bosses — heroes, enemies, items, melodies, cinematics all share the same encyclopedia.
- **Universal entity-spawn API surface (Frida).** Beyond boss-rush: the engine has 40 separate `oCTLibrary<T>` catalogs (heroes, enemies, items, melodies, maps, tiles, rewards, dream shards, …) and a uniform `oIEntityCpnt` reflection surface (`vtable[11] getMemberByHash`, `vtable[19] getMethodHandleByHash`). With the encyclopedia primitive plus `fire_named_event` / `Sc_*` family, a "developer console" mod surface is achievable — spawn any enemy, give any item, apply any melody. Out-of-scope for boss-rush but the foundation work is done; integration only.

## Tooling / GUI

- **Tauri v2 desktop app — Build Tester (default) + dev superpowers (gated).** Front end Vue + Vite, build targets Windows and Linux (Windows first). Two modes selected at build time:
  - **Default build (no flag).** Ships only the "Build Tester" mode — a wizard-style GUI for creating specialized mints by driving `rerw` under the hood. Stub for now; final feature set defined when picked up.
  - **Build with `SUPERPOWERS=true`.** Adds a developer console: an xterm/conpty-powered terminal that wraps either `rerw` or Frida, with the ability to load external Frida scripts (e.g., `tools/frida/rw_lab.js`). Internal/dev only — do not ship publicly.

  The flag-gating must be a true compile-time decision (no superpowers code paths in the default-build binary). Decide on the IPC boundary between Vue front and Tauri back early — the Frida-script-loading path will want streaming stdout/stderr, which constrains the bridge.

## Documentation / housekeeping

- **`add-level-record` shelving decision.** Currently a half-primitive (structurally inserts a GroupLevel record but engine ignores it because the run-in-progress marker isn't set). Either delete the command entirely or move it to a "deferred" subgroup until the Continue-gate dig unblocks it.
- **Skill-controllers YAML schema mismatch.** `data/heroes/<hero>.yaml` uses `controller_name`/`display_name`/`key`/`guid`; the loader in `lib/skill_controllers.py` expects `name`/`guid`. Pre-existing bug (not introduced by this session). Causes `rerw read savefile` to print "controllers[0] requires string 'name' and 'guid'" instead of resolving talent names. Either update the loader or the YAML.
- **`rerw experimental` cleanup.** `add-level-record` and `find-talent-seeds` are the only two experimentals. Decide whether to keep `experimental` as a long-running shelf or fold its contents elsewhere.
- **Test-suite drift.** A handful of pre-existing test failures in `test_game_assets`, `test_lib_game_assets`, and one `test_lib_save_fields::test_missing_keys` regex mismatch. Unrelated to active work but should get cleaned up at some point.
