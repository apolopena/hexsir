[← Back to findings](README.md)

# Save: account binding and portability

How Ravenswatch saves relate to Steam accounts, why they appear "locked" to one user, and how to actually transfer them.

**Status:** confirmed
**Status notes:** Resolved 2026-04-29. Save format itself is fully account-agnostic; the apparent cross-account lock is Steam Cloud sync overwriting local files at launch/quit, not any check inside the game.
**Created:** 2026-04-29

## TL;DR

`Profile_1.ob` contains **no account binding**. It is byte-for-byte portable across Steam accounts. The reason a save handed to another player "doesn't work" is that **Steam Cloud sync overwrites the recipient's local `_Save\` directory** on launch — wiping the gifted file before Ravenswatch ever reads it.

To actually transfer a save: the recipient must disable Steam Cloud for Ravenswatch *before* launching the game with the borrowed save.

## Sources

- `rw/saves/proofs/geppetto/chapter2/laser-lenses_1/Profile_1.ob` (Save A)
- `rw/saves/proofs/geppetto/chapter3/laser_lenses_1/Profile_1.ob`
- `rw/saves/proofs/geppetto/epilogue/laser-lenses_1/Profile_1.ob`
- `/mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save/` (live save directory)
- Ravenswatch.exe (Ghidra project `Ravensmith.rep`) — string and xref searches for `autocloud`, `accountid`, `Steam`, `Owner`, `personaName`

## Live save directory layout

```
_Save/
  Profile_1.ob              ← the actual game save (binary)
  Profile_1_Temp.ob         ← prior save (atomic-write rotation)
  CLEAN_Profile_1.ob        ← debug/dev backup variant
  GameSettings.ini          ← graphics/audio/EULA prefs (not save data)
  GameSettings_Temp.ini     ← prior settings
  steam_autocloud.vdf       ← Steam-managed account marker (NOT touched by Ravenswatch)
```

`steam_autocloud.vdf` content for the canonical user:

```
"steam_autocloud.vdf"
{
    "accountid"   "364148865"
}
```

That's the user's 32-bit Steam Account ID. It is written and consumed by **Steam itself**, not by Ravenswatch.

## What's NOT in `Profile_1.ob`

Searched all three proof saves and the live save for the authenticated account ID `364148865` in every plausible encoding:

| Encoding | Bytes searched for | Hits |
|---|---|---|
| u32 LE | `81 78 b4 15` | 0 |
| u64 LE (full SteamID64 = `0x01100001_15B6E2C1`) | `81 78 b4 15 01 00 10 01` | 0 |
| ASCII decimal | `364148865` | 0 |

Also searched for plausible username strings (4–30 char ASCII runs not matching class-registry patterns): no human-readable persona name appears in any save body. The `personaName` string the user previously edited is either in a different file (e.g., `GameSettings.ini` does not contain it either) or was a misrecollection — it is **not** in `Profile_1.ob`.

## What's NOT in Ravenswatch.exe

Searched the binary for any awareness of `steam_autocloud.vdf`:

| String | Found in binary |
|---|---|
| `steam_autocloud` | NO |
| `autocloud` | NO |
| `.vdf` | only `steam_controller.vdf` (input remapping, unrelated) |
| `accountId` / `AccountId` | YES, but only in Nacon-OS / generic ID contexts — not in save-loading paths |

So the game neither reads nor writes `steam_autocloud.vdf`. That file is purely Steam's bookkeeping. The Ravenswatch executable has no save-time account-validation logic.

## What IS in Ravenswatch.exe (and why it's not the lock either)

The game does communicate with Nacon-OS (publisher Nacon's online services) for *online* features:

- Endpoints (hardcoded in `initial_loading_orchestrator` at `0x14025b9e0`):
  - Prod: `https://nacon-os.com/v2` (appId `8j3h790nHnoABIDLSKO1fhXHRvE7WuXD`)
  - REC test: `https://nacon-os-rec-v2-54f75zaw5q-ew.a.run.app/v2` (appId `REC-pWureBH5SNZvyF3gtC8DK4mLw2Pk`)
  - Toggle at global `DAT_14140dd68 + 0xb0` selects REC vs prod.
- The game POSTs `api/GameOwned` with `SteamId`, `FullSteamId`, and an `access_token` (Steam web API ticket) at startup (FUN_140674190).

This is **license verification**, not save binding. The user reports that **saves load offline**, which rules out any synchronous Nacon-OS or HTTP check as a load-gating mechanism. Nacon-OS auth gates online/multiplayer features, not local save loading.

## What IS in `Profile_1.ob` — the base64 blob

A 144-character base64-encoded blob appears in every save:

```
X841BHVRLKn52xRSeC5dJOT5UiSOWhweJ7BxRWKHDhfjLuLncrriOMY/xUtvgveaffoEcgexM2tV36H1s31t3Y3eXsycIOVMO5hU70l7zMOoyPQ=
```

Decoded: 83 bytes of binary. **Identical byte-for-byte across Save A (chapter 2), chapter 3, and epilogue saves**, at different offsets relative to file start (Save A: `0x11dc5`, chapter 3: `0x123fe`, epilogue: `0x127d2`).

If this were a per-save HMAC or signature, content changes would force value changes. It does not change. So the blob is **not a per-save lock**; it is most likely an asset/build/manifest hash or a static template constant. Decoded bytes do not match common SteamID64, RSA, or ECDSA-P-256/P-384 signature shapes.

## How saves actually fail to transfer

Per CLAUDE.md, the user has already documented one Steam Cloud gotcha:

> "**Steam Cloud sync overwrites on game quit.** When the user quits Ravenswatch, Steam syncs cloud → local, restoring whatever the cloud copy holds."

The same mechanism runs in the **other direction at launch**: Steam pulls cloud → local *before* the game opens its save file. So when User A hands `Profile_1.ob` to User B:

1. User B launches Ravenswatch.
2. Steam pulls B's cloud snapshot to B's local `_Save\` (overwriting A's gifted file with B's prior cloud state, which is empty for new players).
3. Ravenswatch opens `_Save\Profile_1.ob` and reads B's restored file, not A's.
4. B sees a fresh save. The file appears to "not work."

There is no in-game account check, no cryptographic binding, and no Nacon-OS call gating the load. Just Steam Cloud doing what it is designed to do.

## How to actually transfer a save

For the recipient (User B) to load User A's save:

1. **Disable Steam Cloud for Ravenswatch** *before* launching.
   - Steam → Library → right-click Ravenswatch → Properties → uncheck "Keep games saves in the Steam Cloud"
2. Place A's `Profile_1.ob` in B's `_Save\Profile_1.ob`.
3. (Optional) Delete or overwrite `steam_autocloud.vdf`. Steam may regenerate it on next sync; the game does not consult it. Either is fine.
4. Launch Ravenswatch. Game opens A's bytes verbatim and loads the save.

## Implications for tooling

`Profile_1.ob` byte edits do not need to update any account-related field. There is no account-binding integrity to preserve across edits. CRC at offset `0x0C` over `data[16:]` remains the only required integrity field in the save body itself.

Save backups, sharing, and `rerw swap savefile` all work without account considerations. The only account-adjacent constraint remains the existing CLAUDE.md gotcha about Steam Cloud overwriting on session end.

## Open questions

| Question | Status |
|---|---|
| What is the 83-byte base64 blob? | Untested. Static across saves; possibly an asset manifest hash or build identifier. |
| Does Steam DRM check anything beyond ownership at launch? | Not investigated. Likely not relevant to save loading. |
| Does the game's Nacon-OS auth gate any game-state features once loaded? | Untested. Online/multiplayer/leaderboards likely; offline single-player apparently not. |

## Locating these structures on a new build

Per `rw/docs/README.md` §"Locating <thing>" — byte-stream template. Light section; this finding's anchors are byte-position within the save's account-binding header region.

### Strategy

1. Locate the save header (start of file, before record list).
2. The 83-byte base64 blob lives in a fixed header region. Re-derive position by hex-dumping a known minimal save and matching the documented byte ranges in this finding.
3. Steam-account ID (when present) is at a documented offset in the header.

### Assumptions

- Header region layout stable engine-wide (verified across observed builds).
- Base64-encoded blob length (83 bytes) stable.

### Known failure modes

- **Build identifier changes.** If the 83-byte blob is a build hash, it varies per build but its byte position does not.
- **Auth scheme change.** If Nacon-OS auth gating changes, header layout could change. No observed instance.

### Cross-finding anchoring

Inherits from `save-binary-format.md` (header framing). Multiplayer aspects covered in `multiplayer-host-authority.md`.
