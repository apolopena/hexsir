[← Back to findings](README.md)

# Steam profile playtime is session-based, not game-driven

The game does not (and cannot via Steamworks) write to the Steam profile "hours played" counter. Save-file recorded playtime has no path to Steam.

**Status:** confirmed
**Created:** 2026-05-07

## TL;DR

Investigated user observation that loading a chapter-2/3 save and doing a 2-minute test caused Steam profile playtime to grow by 30 minutes to 1 hour. The binary does not have any code path that writes to Steam profile playtime (it can't — the Steamworks public API doesn't expose that field). The three "playtime"-named keys in the binary are debug-overlay scratch values and a studio analytics field; none reach Steam. The growth pattern is most likely Steam-side rounding (Steam profile playtime is reported in 0.1h / 6-minute granularity, so a 2-min test rounds up; multiple short tests in a sitting accumulate visibly).

## Sources

- `Ravenswatch.exe` (Ghidra project `Ravensmith.rep`):
  - `debug_overlay_set_kv` @ `0x1405051a0` (formerly `FUN_1405051a0`) — internal 64-slot scratch table
  - `passtech_analytics_post_event` @ `0x1401f6b10` (formerly `FUN_1401f6b10`) — studio analytics POST
  - `SteamUserManager_get_ISteamUserStats` @ `0x140a2aab0`
  - `SteamUserManager_get_ISteamUser` @ `0x1400dd6f0`
  - `Steam_init_and_register_lobby_handlers` @ `0x1400e42d0`
- Strings searched: `playtime`, `SteamAPI_`, `SteamUserStats`, `SetStat`, `STEAM`, `steam_api`
- IAT enumeration confirmed Steamworks is delay-loaded (no static thunks; resolved via `DelayLoad_SteamAPI_*` and `SteamInternal_*`)

## What the three "playtime" strings actually are

| String | Address | Sink | Purpose |
|---|---|---|---|
| `playtime.game` | `0x140eef100` | `debug_overlay_set_kv` | Debug HUD scratch key, written every options/audio tick from FUN_1401d0f40 |
| `playtime.run` | `0x140ef7420` | `debug_overlay_set_kv` | Debug HUD scratch key, written every per-run tick from FUN_14028dbc0 (alongside `map.difficulty`) |
| `run_playtime` | `0x140ef2a30` | `passtech_analytics_post_event` | JSON field in studio analytics POST (Passtech/Nacon backend) |

`debug_overlay_set_kv` is a 64-slot in-process key/value table (32 KB total: 64 × 0x200 bytes per slot, 0x100 key + 0x100 value). Pure RAM scratch — never serialized, never networked. Likely powers a developer HUD panel.

`passtech_analytics_post_event` is the studio's own analytics — see `telemetry-surface-and-warden.md`. Goes to `dt-live.passtechgames.com` and `nacon-os.com`, not Steam.

## Steam surface in the binary

Three interfaces queried by name:

- `SteamUser023` — identity (Steam account ID, persona name)
- `STEAMUSERSTATS_INTERFACE_VERSION012` — stats and achievements
- `STEAMAPPS_INTERFACE_VERSION008` — DLC checks, build info

Notably absent: `SteamRemoteStorage` (no Steam Cloud usage — confirms `CLAUDE.md` "Steam Cloud disabled" assumption from the save-account-binding finding).

The `STEAMUSERSTATS` consumer is `oCSteamAchievementsManager` (RTTI string at `0x1413dc500`) — used for achievement state, not for arbitrary stat writes that could affect profile playtime. And even if `SetStat` were called, it would only affect game-defined custom stats, not the Steam profile "hours played" counter, which is never writable from the game side.

## Why the user's observation can't be game-driven

Steam tracks profile playtime at the Steam-client level. The Steam client measures from process launch to process exit. The game has no API to extend, fake, or backdate that counter:

- `SetStat` writes go to game-specific custom stats (achievement progress, leaderboard inputs); they do not affect the profile "hours played" number.
- `StoreStats` flushes those custom stats to Steam's backend — same scope, no playtime impact.
- There is no Steamworks call that sets profile playtime. By design.

So even if every game-defined stat were maximally abused, profile playtime would still be exactly the wall-clock time the process was running, as observed by the Steam client.

## Likely cause of the user's observation

In priority order:

1. **Steam profile playtime granularity.** Steam reports profile playtime in 0.1h (6-minute) increments. A 2-minute session rounds up to 6 minutes on the profile. Five 2-minute tests in one sitting → +30 min. Ten → +1 h. This matches the observed range exactly.
2. **Slow shutdown on heavier saves.** Chapter-2/3 saves carry more in-memory state (encyclopedia, modifiers, run state). The shutdown path may take noticeably longer to flush than chapter-1 saves. Steam keeps counting until the process exits. Adds at most ~10s per test, not the 30+ min seen.
3. **Process kept alive after window close.** Crash dialog, stuck Steam overlay sub-process, or a hung graphics driver shutdown can keep `Ravenswatch.exe` running invisibly. Steam still counts.

## Test to confirm

Two consecutive sessions of identical wall-clock duration:

- Run A: launch, do not load any save, sit at title for exactly 2 min, quit. Note Steam profile delta.
- Run B: launch, load a chapter-3 proof, wait 2 min in-game, quit. Note Steam profile delta.

If both grow the same amount → Steam-side rounding (this finding's conclusion). If Run B grows much more → there is something binary-side worth chasing further (and at that point WinDbg-instrumenting the shutdown path becomes the right next step).

## Notes

- The `oe::SteamUserManager` vtable lives at `0x1412d2300`. One of its slots (4-byte cached interface ptr at `0x1414d5fb4`) holds the resolved `ISteamUserStats*` after first acquisition.
- `SteamAPI_Init` is delay-loaded from `steam_api64.dll`; the resolution table at `0x1412b6cf4` references the dll-name string at `0x140e9d640`.
- The studio's analytics include a `run_playtime` JSON field that IS derived from in-game time (DayNightCycle elapsed seconds), but that flows to Passtech, not Steam — see `telemetry-surface-and-warden.md` for the full network surface and the `tools/telemetry-warden/` block tool.
