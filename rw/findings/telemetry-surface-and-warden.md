[← Back to findings](README.md)

# Telemetry surface + telemetry-warden block tool

Full map of every outbound telemetry endpoint baked into `Ravenswatch.exe` (Passtech, Nacon, Backtrace) and a standalone tool (`tools/telemetry-warden/`) that intercepts and logs the calls without letting any bytes leave the machine.

**Status:** confirmed
**Created:** 2026-05-07
**Updated:** 2026-05-08 — Telemetry power v0.6.0 (streaming-body capture + log(N) budget mode); in-vivo confirmation that dt-live ticks are empty-body and that the heartbeat is required only to *establish* multiplayer, not maintain it.

## TL;DR

The game phones home aggressively. Every game-state event (chapter end, run start, hero pick, difficulty pick, etc.) builds a JSON payload and POSTs it via WinHTTP to studio backends — Passtech (Pub/Sub) and Nacon (Cloud Run). Crash minidumps go to Backtrace. There is one master POST function with 33 callers and 37 callsites, plus a separate batched-send scene context. No opt-out is offered in-game.

`tools/telemetry-warden/` is a standalone, stdlib-only Python listener (~130 lines) that binds `127.0.0.1:80/443/8888`, peeks the TLS SNI or HTTP Host header from each incoming connection, logs `BLOCKED <host>:<port>` to a file, and drops the connection. Combined with eight hosts-file entries, every telemetry call is intercepted at localhost — zero bytes ever leave the machine. The tool produces a per-session log and end-of-session summary.

## Sources

- `Ravenswatch.exe` (Ghidra project `Ravensmith.rep`):
  - `passtech_analytics_post_event` @ `0x1401f6b10` (formerly `FUN_1401f6b10`) — main JSON POST builder
  - `chapter_end_analytics_emit` @ `0x1401f1cf0` — one of 33 callers
  - URL strings at `0x140eed7b0..0x140f81c8` and `0x140ef2150..0x140ef3a30`
  - Imports table: WinHTTP (`WinHttpOpen`, `WinHttpConnect`, `WinHttpSendRequest`, etc.)
- `tools/telemetry-warden/{warden.py,README.md}` — block tool

## Endpoints

### Studio analytics (the firehose)

| Host | Purpose | Path |
|---|---|---|
| `dt-live.passtechgames.com` | Passtech analytics, primary | Pub/Sub topic `projects/passtech-ravenswatch/topics/ravenswatch` |
| `dt-live-2.passtechgames.com` | Passtech analytics, mirror | same topic |
| `dt-live-3.passtechgames.com` | Passtech analytics, mirror | same topic |
| `dt-dev.passtechgames.com:8888` | Passtech dev (test builds only — `*(arg1+0xd4)` flag gates) | dev path |
| `nacon-os-rec-54f75zaw5q-ew.a.run.app` | Nacon analytics v1 (Google Cloud Run, EU-West) | `/v1/analytics` |
| `nacon-os-rec-v2-54f75zaw5q-ew.a.run.app` | Nacon analytics v2 (Cloud Run) | `/v2` |
| `nacon-os.com` | Nacon analytics fallback / MyNacon account | `/v2/analytics`, `/v2` |

### Crash reporting

| Host | Purpose |
|---|---|
| `submit.backtrace.io` | Backtrace minidump upload (`/passtech/<hex-token>`) |

### Not blocked (informational, no POST from binary)

- `my.nacongaming.com` — opens privacy policy / terms of use in browser. No outbound HTTP from the binary itself.

### Out of scope for solo play

- `oCStormancerSceneContext::StartGetAnalytics` — Stormancer multiplayer matchmaking SDK has its own analytics. Only fires in matchmaking flows; solo runs shouldn't hit it.

## JSON payload shape

`passtech_analytics_post_event` builds an event with this top-level structure (assembled in a `data` array of `(key, value)` pairs):

```json
{
  "topic": "ravenswatch",
  "projectId": "passtech-ravenswatch",
  "event_type": "<caller-provided string>",
  "event_datetime": "<ISO8601>",
  "user_id": "<Steam account ID or equivalent>",
  "new_user_id": "<opaque>",
  "session_id": <u64>,
  "platform": "steam",
  "build": "<version>",
  "nacon_user_id": "<MyNacon login>",
  // The following only present when param_4 != 0 (run-context-bearing events):
  "run_id": "<run guid>",
  "hero_name": "<hero key>",
  "hero_skin": "<skin key>",
  "difficulty": "<enum>",
  "run_playtime": <seconds>
}
```

Auth header: `os-access-token: 8j3h790nHnoABIDLSKO1fhXHRvE7WuXD` (production; `ENV-TOKEN-REC` in dev/test builds when `*(arg1+0xd4)` is set).

Content-Type: `application/json`. Transport: WinHTTP.

## Code surface

- **`passtech_analytics_post_event`** is the single funnel. 33 distinct callers, 37 unconditional-call instructions. Every event the game wants to record passes through here. Hooking this one function silences ~all event traffic.
- **`oCDtAnalyticsSceneContext::_SendData`** is a separate batched-send path — caches events and dispatches them on a timer. Likely also routes through `passtech_analytics_post_event` for the actual transport, but unverified. String `"(%s) Analytics batched data send"` at `0x140ef21d0` confirms the batching.
- **`MyNacon::_CallMyNaconApi`** lambda (RTTI at `0x1413066f0`) — Nacon account API (login, content fetch). Only fires if you interact with the in-game MyNacon UI.
- **Backtrace** uploads via WinHTTP on crash. Separate code path, separate decision to block.

## tools/telemetry-warden/ — block strategy

The warden takes the network-layer block + log approach. Architecture:

1. **Hosts file edit** (one-time, manual): each telemetry hostname pinned to `127.0.0.1`. Uses Windows's standard hosts file at `C:\Windows\System32\drivers\etc\hosts`. Marker comments `# === BEGIN/END ravensmith telemetry-warden ===` make the entries trivially reversible.
2. **Local listener**: `warden.py` binds `127.0.0.1` ports `80`, `443`, and `8888`. On each incoming connection, peeks the first ~2 KB, parses the SNI extension from the TLS ClientHello (or `Host:` header for plain HTTP), prints one line to stdout, and closes the socket without responding. Game's WinHTTP request fails as a connection-reset; the game treats it as a flaky network error and either drops the event or queues for retry — every retry hits the same wall.
3. **Output**: one line per blocked attempt to stdout: `2026-05-07 14:32:01  BLOCKED  dt-live.passtechgames.com:443  (TLS)`. End-of-session summary prints a per-host count. Warden never writes to disk (per MAINT-43); redirect stdout if persistence is wanted.

### Design choices and rejected alternatives

- **Why localhost listener, not just blackhole?** A bare hosts-file blackhole works (TCP connect to `127.0.0.1` with nothing listening fails immediately) but produces no log. The listener exists only to log what was attempted — proof that blocking is effective, plus visibility into what the game tried to send.
- **Why no TLS termination / payload visibility?** Originally proposed, then dropped per "do one thing" feedback. Terminating TLS would require generating a CA, installing it in the Windows trust store, and per-host cert minting on the fly — too invasive for the goal of "block and report." We see hostname and port; we don't see encrypted body content. That's enough to confirm the block.
- **Why not Frida hook on `passtech_analytics_post_event`?** Considered as a supplement (logs from inside the game what it would have sent, no certs needed, more granular). **Built later as `tools/frida/mods/powers/Telemetry.js`** — but pivoted to hooking `winhttp!WinHttpSendRequest` instead of `passtech_analytics_post_event`. The Stormancer login function (`UsersApi::loginImpl`) was buried in C++ async-task lambda machinery (no direct Ghidra xref), and going through WinHTTP catches all telemetry layers — login, analytics, Backtrace — in one hook. See "Telemetry power" section below.
- **Why not Windows Firewall outbound rule?** Firewall rules match by IP, not hostname. Cloud Run IPs rotate. And the firewall log doesn't include host info — you'd see "blocked outbound to 35.x.y.z" without knowing which telemetry endpoint that was.

### Operational notes

- Requires Windows admin to bind privileged ports (`80`, `443`).
- Runs on Windows-side, not WSL — Windows hosts file resolves against the Windows network stack, and only a Windows-bound listener receives the game's traffic. Invoke via `python.exe \\wsl.localhost\Void\home\<user>\repos\work\ravensmith\tools\telemetry-warden\warden.py` from elevated PowerShell. The warden's log writes back to the WSL filesystem over the UNC path.
- If port `:80` is owned by something else (rare; usually IIS), :443 and :8888 binds still succeed and catch the bulk of traffic.
- Stop with Ctrl+C. Hosts entries persist across sessions; the listener is the only thing you toggle.

## tools/frida/mods/powers/Telemetry.js — in-process companion

Frida-side complement to the warden, built MAINT-45/47, extended through v0.6.0 (2026-05-08). Loaded via `loadPower("Telemetry")`. Hooks `winhttp!WinHttpSendRequest` once at load with a host-suffix filter (`passtechgames.com`, `nacon-os.com`, `nacon-os-rec`, `submit.backtrace.io`, `.a.run.app`). v0.4.0+ also attaches to `WinHttpWriteData` (streaming-body capture) and `WinHttpCloseHandle` (eviction of aborted streaming entries). API:

- `Telemetry.disable()` — matched calls return `BOOL FALSE` without doing any I/O. No socket, no DNS, no TLS handshake. The warden goes silent for those hosts because nothing reaches the network layer.
- `Telemetry.enable()` — restore default; matched calls pass through to WinHTTP normally.
- `Telemetry.log(on?: boolean | number)` — controls stdout printing of cleartext request bodies. Modes:
  - `log()` toggles on/off; `log(true)` / `log(false)` force.
  - `log(N)` (positive integer) — print the next N complete *non-empty* bodies, then auto-disable. Empty-body matches (e.g. dt-live heartbeat pings, GET handshakes) don't consume the budget; only bodies with actual bytes count toward N. Calling `log(N)` again while in budget mode adds to the remaining count.
  - Streaming POSTs (`lpOptional=NULL`, body delivered via `WinHttpWriteData` after `SendRequest` returns) are accumulated chunk-by-chunk in memory and printed as one line on completion: `[Telemetry.log] <url> body(N): <bytes>`. Aborted/closed sends evict silently. WinHTTP's `lpOptional` (or the streamed bytes) are read pre-encryption — TLS happens *inside* WinHTTP after `SendRequest` returns. Stdout only; never writes to disk.
- `Telemetry.stats()` — `{matched, blocked, logged}` counters since load. `logged` counts at print time, so it reflects bodies the user actually saw — empty-body matches under budget mode increment `matched` but not `logged`.

**Per-call block visibility.** `disable()` by itself is silent — only the `blocked` counter increments. For one line per blocked call, combine `Telemetry.disable()` with `Telemetry.log(true)`. The hook processes logging *before* the disable check returns FALSE, so you get the body / `(no body)` line for each matched call as it's intercepted. Caveat: this combination prints inline-body and empty-body matches but NOT streaming-body matches — streaming registration is gated on `!_disabled` (because the failed SendRequest never produces follow-up `WinHttpWriteData` calls). For the dt-live heartbeat (empty body) and Nacon handshakes this is fine; for `passtech_analytics_post_event` POSTs (which stream their JSON body) you'd need to enable, capture via `log(N)`, then disable — two-step.

**Why both warden and power.** The warden is the always-on broad net (catches anything hitting blocked hostnames at the network layer, including paths we haven't reverse-engineered). The Telemetry power is surgical — kills the calls inside the process, stops the retry storm at its source, and gives cleartext-body visibility. Two layers, different scopes:

| Path | Warden catches? | Telemetry power catches? |
|---|---|---|
| `passtech_analytics_post_event` JSON POSTs | yes (network drop) | yes (function-call block + body read) |
| Stormancer `UsersApi::loginImpl` retries to `dt-live*` | yes | yes |
| Backtrace crash upload | yes | yes |
| Endpoint hitting a *new* host warden's hosts file doesn't include | no | yes (if URL hostname matches power's filter pattern) |
| Endpoint hitting a host *neither* knows about | no | no — surfaces in the next URL-string scan |

## Stormancer-login retry storm — what dt-live spam actually is

When the warden first went up, only `nacon-os.com` calls were observed (~2 over 2 minutes). After Frida-driven gameplay tampering and several crashes, `dt-live.passtechgames.com` started spamming roughly once per second. Initial investigation suggested it might be persisted analytics queue from prior sessions; the actual cause was found in `_Logs/logs_*.txt`:

```
| Stormancer | ApiClient.getFederation | Can't reach the server endpoint. https://dt-live.passtechgames.com
| Stormancer | UsersApi::loginImpl | Login failed with recoverable error, doing another attempt.
```

So `dt-live*.passtechgames.com` isn't (only) an analytics host — it's also the **Stormancer multiplayer federation server**. Stormancer's `UsersApi::loginImpl` auto-fires on game launch (or first time the user navigates to a multiplayer-aware UI), the warden blocks the connection, Stormancer marks it as a "recoverable error," and re-tries roughly every second hitting both mirrors (`dt-live` then `dt-live-2`). This is *Stormancer's design* — the retry never gives up. Implications:

- The dt-live spam is **login retries**, not gameplay analytics. The Telemetry power's `disable()` is the cleanest way to silence it (kills the WinHttpSendRequest call before it reaches the network layer).
- The retry storm is fully session-recreated, not disk-persisted. No state file feeds it; quitting the game empties the queue, relaunching reproduces the same behavior because Stormancer always tries to login.
- "Solo play needs no multiplayer login" — `Telemetry.disable()` is safe for solo runs. Multiplayer matchmaking won't work while disabled.

### In-vivo behavior (2026-05-08, Frida session)

Two observations confirmed by directly hooking and toggling at runtime, beyond what the static reverse-engineering revealed:

**1. dt-live heartbeat ticks are empty-body URL pings.** With `Telemetry.log(true)` for ~5 seconds while dt-live was allowed and the game was in/near the multiplayer lobby, the hook printed a flood of `[Telemetry.log] <url> (no body)` lines — one per second, matching the Stormancer-retry cadence. Out of 106 matched ticks observed in budget mode (`log(5)`), zero printed because every one was empty (`bodyLen=0`, `dwTotalLength=0`). The URL itself is the entire heartbeat signal; there is no JSON payload accompanying the per-second tick. The previous expectation that "dt-live carries telemetry payloads" was wrong for the heartbeat path — *event*-driven analytics POSTs (chapter end, run start, etc., still sent through `passtech_analytics_post_event`) do carry bodies, but the 1-Hz Stormancer login retry does not.

**2. dt-live heartbeat is required to *establish* the multiplayer connection but NOT to *maintain* it.** Workflow:
   - hosts file allows dt-live → game launches, Stormancer succeeds, lobby connects (multiplayer functional).
   - In Frida REPL: `Telemetry.disable()` — process-side block kicks in, heartbeat stops firing the network call.
   - **Lobby connection survives.** Multiplayer remains functional with the heartbeat cut.

   Implication: the surveillance/connectivity window is post-handshake-only. Once authenticated and joined, the per-second tick can be silenced. Open follow-ups (untested as of 2026-05-08):
   - Does the connection survive *indefinitely* with `disable()` active, or does Stormancer eventually time the session out from the server side?
   - Does the connection survive lobby → in-run → back-to-lobby transitions? (Game may re-handshake at scene boundaries.)
   - If the connection drops while disabled, does `enable()` recover it on the fly, or is full re-establishment from scratch required?

   Cleanest test workflow for these follow-ups: get into lobby, `Telemetry.disable()`, then leave it sitting / play through transitions / wait for idle timeout, observing whether the lobby UI reports a disconnect.

## Known limitations

- **Cert pinning** would silently break warden visibility (TLS handshake fails before our peek can read SNI). The traffic still gets blocked because `127.0.0.1` is the only resolution. Detection: if BLOCKED stdout lines stop appearing while the game is actively running with internet access, pinning is suspected. Fallback: use the Telemetry power's `log()` mode for body visibility — the WinHTTP-layer hook is unaffected by cert pinning since it reads cleartext before WinHTTP touches TLS.
- **Stormancer matchmaking analytics** is a separate code path tied to multiplayer queueing. Solo play shouldn't reach it; not currently in the block list. Add `submit.backtrace.io`-style entry if it surfaces in future logs.
- **Studio could change the host list in a patch.** Re-run the URL-string search after every game update; new hosts (`https://...passtechgames.com` / `nacon-os` / new Cloud Run subdomains) get appended to the hosts file.

## Notes

- The game's analytics is opt-out — there is no in-game toggle to disable it. Annotated extensively in Ghidra to discourage future versions of self from re-investigating.
- Ghidra annotations applied this session: `passtech_analytics_post_event` rename + plate comment with full JSON shape, endpoint list, and auth header. Also `debug_overlay_set_kv`, `SteamUserManager_get_ISteamUserStats`, `SteamUserManager_get_ISteamUser`, `Steam_init_and_register_lobby_handlers` for adjacent context.
- See `steam-playtime-not-game-driven.md` for the parallel Steam-vs-analytics finding (the user's original question that started this dig).
