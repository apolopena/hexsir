# Multiplayer host-authority and replication architecture

**Status:** in-progress
**Created:** 2026-05-04

## Sources

- `Ravenswatch.exe` (Ghidra, string scan + import map — image base via Ghidra ASLR)
- `tools/frida/rw_lab.js` (`forceBossSpawn`, used in the host-side experiment below)
- `rw/findings/save-account-binding.md` (prior context: Nacon-OS gates online/MP, not local saves)
- `rw/findings/pin-identity-uncertain.md` (prior context: speculation about replication subsystems)
- `rw/findings/chapter-boss-portal-trigger.md` (the natural arrival path that `forceBossSpawn` partially bypasses)
- Live MP session, host = user, peer = remote player (run-time observation, see "Experiment: forceBossSpawn from host" below)

## Confirmed Findings

### Stack (top → bottom)

| Layer | Tech | Evidence (string / symbol) |
|---|---|---|
| Cross-platform brokerage / matchmaking / RPC / party (server-mediated) | Stormancer (Nacon middleware) | `Stormancer::GameSessions`, `Stormancer::Party`, `Stormancer::RpcService`, build path `C:\ravenswatch\ravenswatch\ThirdParty-Ext\Stormancer\…` |
| Lobby provider (Steam) | Steamworks | `SteamMatchMaking009`, `+connect_lobby`, `Steam.CreateLobby/JoinLobby/SetLobbyJoinable` |
| Lobby + NAT punch + relay (cross-platform) | Epic Online Services | `EOS_Lobby_*`, `EOS_P2P_*`, relay control `EOS_RC_AllowRelays` / `EOS_RC_ForceRelays`, NAT detection `EOS_NAT_Open/Moderate/Strict` |
| Voice chat | EOS RTCAudio | `EOS_RTCAudio_UpdateSending`, `_QueryInputDevicesInformation` |
| P2P transport (actual game traffic) | RakNet (with a SLikeNet fork layer behind a Stormancer transport abstraction) | `FullyConnectedMesh2`, `RakPeer`, `NatPunchthroughClient`, `oCSLNetReplicationManagerSceneContext`, build path `C:\Workspace\oengine2\ThirdParty-Ext\RakNet\…` |
| Entity replication | RakNet `ReplicaManager3`, wrapped by engine class `oINetworkReplicationManagerSceneContext` | `Replica3`, `ReplicaManager3`, `Connection_RM3`, `NetworkIDObject` |
| Game session root | `LobbyGs` (sibling of `oCDtRootGs` save root in the same `Gs` family) | `"LobbyGs"` string |

### Topology

Full mesh, not star — `FullyConnectedMesh2` + `ID_FULLMESH_CREATED`. Every peer connects to every other peer. "Host" is a logical role on top of the mesh, not a network hub.

### Engine identity

The game engine is `oengine2` (Passtech in-house — explains the `oC*Gs` / `oI*` naming convention used throughout save-subsystem digs). `oengine2` + Stormancer + RakNet are three distinct subsystems; keep them named correctly when annotating.

### Three replication modes (verbatim from binary strings)

- "Host spawns the entity and replicates it to every other peer." (host-authoritative replicated)
- "Host spawns the entity and does not replicate it." (host-local — e.g. AI bookkeeping)
- "Each peer spawns his version of the entity and replicate it to every other peer." (peer-owned, distributed)

### Host election

`Stormancer::GameSessions::HostInfosMessage` is an RPC carried at session init, dispatched from `GameSessionService::initializeP2P`. Tells each peer which scene-peer is host. No host-migration path was found in strings; `Session_Disconnected_From_Host_Go_To_Lobby` indicates host-leaves = run-ends-back-to-lobby.

### Multiplayer does not write game saves

Stated by user, no on-disk save events fire during MP runs (host or peer). `Profile_1.ob` is solo-only territory. Consequence: MP runs are a **near-free iteration platform** for host-authoritative experiments — the chapter-boss-kill save scarcity rule (CLAUDE.md, ~20 min/save) does not apply in MP.

### Host-authoritative subsystems (from experiment + observation)

| Subsystem | Authority | Replication mode | Source |
|---|---|---|---|
| Chapter timer / time advancement | Host-only | Implicit (peers observe) | Experiment below — peer-side `forceBossSpawn` did nothing because peer can't advance time |
| Boss entity (HP, hitboxes, attacks, damage taken) | Host | Full replication (mode 1) | Experiment — both peers fought the real boss |
| Pre-boss arrival cinematic / "boss arriving" announcement | Per-peer, local presentation | Triggered by an upstream event the spawn function does not fire | Experiment — host got the cinematic, peer did not |
| Shard wallet (run currency) | Shared pool, host-owned | Replicated to all peers | User: "any player that gets shards, all players get those shards" |
| Pickup-time shard modifiers (e.g. Hope Diamond) | Per-peer local | Applied at pickup before crediting shared pool | User-reported pattern |

### Host-authority enforcement is at the spawn function, not just by social contract

Peer-initiated `forceBossSpawn` produced only local UI flicker — no replicated state mutation. Indicates the spawn function checks authority (or simply isn't reachable from a non-host scene-peer's replication graph). Peers cannot mutate host-authoritative state by calling host-side functions locally.

### Frida-driven host-side mutations replicate through the normal path

`forceBossSpawn` invoked on the host caused the boss entity to appear and become combat-active for the peer too — the engine doesn't distinguish gameplay-code calls from foreign-hook calls when the calling machine is the authority. Implication: any host-authoritative subsystem can be experimentally mutated via host-side Frida and the replication system propagates state to peers automatically.

## Experiment: forceBossSpawn from host

**Setup:** fresh-game-state MP run, chapter 1, user as host with `tools/frida/rw_lab.js` loaded, one remote peer, neither peer strong enough to actually kill the boss.

**Action:** host called `forceBossSpawn` (introduced in commit `0646437` — "BREAKTHROUGH-4: chapter-boss arrival on demand").

**Observed:**

- **Host:** clean natural arrival — pre-boss animation played, boss appeared, combat began.
- **Peer:** got teleported / "pulled in" to the boss arena with no warning — no pre-boss animation. Ended up at the boss with no narrative cue.
- **Both:** fought the real boss — correct HP, real hitboxes, damage applied normally on both sides.
- **Run did not save** (consistent with "MP doesn't write saves") and no boss kill (intentional — that's a separate test).

**Diagnostic interpretation:** the natural chapter-boss arrival path is multi-step:

1. Host's chapter-timer expiry handler fires (timer reaches end-of-chapter).
2. Handler broadcasts a "boss arriving" RPC / replicated-flag to all peers.
3. Each peer (host included) runs their **local** pre-boss cinematic in response to step 2.
4. Host calls the boss-spawn function.
5. Peers get pulled to the arena via replicated position/scene-state.

`forceBossSpawn` enters at step 4. The host's local cinematic still runs because step 4 calls it as a side effect on the local machine, but the step-2 broadcast never fires, so peers never get the cinematic-trigger event. They only experience step 5 (teleport).

**Inverse experiment (peer side):** peer-side `forceBossSpawn` showed UI indicators ("boss spawned") but no real game-state change — confirms the spawn function only takes effect when invoked by the authoritative host, and that local UI hooks fire regardless of authority outcome.

## Shard-gain plumbing (Ghidra dig 2026-05-04)

Architecture for the shared-pool shard sync, so we can drive it from the host via Frida and observe peer replication.

- **Runtime IDs registered at `image+0x1d1ff5`:**
  - `0x12e831f3` = "Gain dream shards"
  - `0x12e831f4` = "Lose dream shards"
- **Delta dispatcher: `FUN_14038c2b0` (RVA `0x38c2b0`)** — receives new vs. old shard floats (XMM7 / XMM8), routes to gain or loss event with the magnitude. Called from 8 sites that look like various gain/loss source paths (boss kill, pickup, sell, store, etc.).
- **Named-event fire helper: `image+0x67dea0`** — signature `fire(eventBus, hash, *amount_float)`. Subscribers receive the gain/loss event, including:
  - HUD pop animation
  - Per-player modifiers (Hope Diamond, Heal-on-gain, Sandman-price modifiers, etc.)
  - `ReplicaManager3` replication path that syncs the change to peers in MP
- **Held shards field:** `oCDtEntityCpntHeroControllerPersistentData` body `+0x1D` (float32 LE) — confirmed by `held-dream-shards.md`.
**Breakthrough 2026-05-04 — full decompile of `image+0x38c2b0` resolves the architecture.**

What I previously called "the dispatcher" is actually the **canonical gain function itself**, now renamed in Ghidra to `HC_change_dream_shards`. All 8 "callers" I'd been hooking are the 8 different shard-source code paths (pickup, store, sandman, boss reward, sell, damage-loss, etc.) calling this single function. The function's signature is:

```c
HC_change_dream_shards(longlong HC, float delta, oCCustomFlagList *src)
```

Behavior (verified by decompile):
- `if delta > 0`: increments cumulative-earned mirrors at `HC+0x1d48[+0x10]` and `HC+0x1d78[+0xf4]`.
- `if delta < 0` AND `src` has "Purchase" tag: increments cumulative-spent-on-purchases mirrors at `HC+0x1d48[+0x4]` and `HC+0x1d78[+0xf8]`.
- always: writes `HC+0x1590 = max(0, current + delta)` — **THE held_shards runtime field** — and mirrors the new value to `*(HC+0x1d48)`.
- fires named event `0x12e831f3` (gain) or `0x12e831f4` (loss) with magnitude as float arg.
- fires global-value event `0x171c27b5` with the new int value.
- runs subscriber loop via `dispatch_event_with_swap_remove(HC+0x15d8, ...)`.

**HC body runtime offsets (all 4-aligned, NOT the byte-packed save-file offsets):**

| Offset | Field |
|---|---|
| `+0x1590` | held_dream_shards (float32) ★ |
| `+0x1598` | derived ratio (set on every change) |
| `+0x15d8` | subscriber list head |
| `+0x1d48` | stat tracker A* |
| `+0x1d78` | stat tracker B* (may be NULL) |

**Where my earlier probes went wrong.** I labelled the function a "dispatcher" because the disassembly showed it firing the gain/loss event hash. The function's `param_1` IS HC. In the caller[7] probe output, `rcx = 0x22edd517018` (constant across all fires) was HC the whole time — but the per-pointer scan only went to `+0x80`, so it missed `+0x1590` entirely. The decompile, instead of more register-state probing, would have shown this in one query. Annotated in Ghidra now (plate comment with full field map) so the next session lands in named territory.

**Implementation status (`tools/frida/rw_lab.js`).** Hook on `HC_change_dream_shards` entry captures `args[0]` as `capturedHC` (refreshed every shard event). Two paths:

- **`gainShards(n)` (path A) — CONFIRMED WORKING 2026-05-04 in solo. MP replication PREDICTED to work via per-frame watcher pattern.** Direct `HC+0x1590 += n` write. HUD updates in real time. The mechanism for HUD update is `HC_per_frame_update` (image+0x38e260, decompiled 2026-05-04): it watches `+0x1594` (cached/animated) vs `+0x1590` (current) every frame, lerps the cached value toward the current, and dispatches on `HC+0x15b8`. This is the BossTimer-equivalent pattern (`forceBossSpawn` works the same way: write `BossTimer.elapsed`, next frame's `BossTimer_update` detects the change and fires the event). `ReplicaManager3` likely subscribes per-field — meaning a host's raw `+0x1590` write should propagate to peers identically to how `forceBossSpawn` propagates to peers. Captured-HC log line:
  > `[SHARDS] HC=0x11d61d4b1f8  held(+0x1590)=132.00  ratio(+0x1598)=42.4497  trkA=0x11d42f5e8f0 (*=132.00)  trkB=0x11cf0aca430`
  Verifies (a) the runtime offset `+0x1590` is correct, (b) the engine's HUD is field-driven not event-driven for this value, and (c) `*(HC+0x1d48) = held` is the engine's own self-mirror that re-syncs on the next natural shard event regardless of our writes.
- `gainShardsCall(n)` (path B, parked) — call the canonical function via `NativeFunction(HC, delta, src_flags)`. Would also fire HUD pop animation, run modifier subscriber loops (Hope Diamond, Heal-on-gain), and replicate via `ReplicaManager3` to peers in MP. Parked because `src_flags` is an `oCCustomFlagList*`; passing NULL crashes on the unconditional `FUN_140651ec0(&local_160, src)`. To wire: cache `args[2]` from the entry hook on a real shard event and reuse the captured pointer. Only needed if path A turns out to miss something we care about (modifier ticks, MP replication).

Companion helpers: `shardsHc()`, `shardsStatus()` (dumps held + ratio + stat trackers).

**Workflow (verified by user, 2026-05-04):**

1. Kill `Ravenswatch.exe` (Frida holds the process; clean detach requires shutdown). MP doesn't write saves and solo only saves on chapter-boss kill — both forms of mid-chapter kill lose zero on-disk state.
2. Swap to the desired proof (`rerw swap savefile --source <proof>`).
3. Relaunch the game and load.
4. Play briefly so a natural shard event fires (any enemy kill that drops shards, crystal break, hit-with-shards-loss). This is what populates `capturedHC` on the Frida side via the entry hook.
5. `shardsStatus()` to confirm capture (HC printed, held value matches HUD).
6. `gainShards(N)` — HUD jumps in real time.

The "play briefly" step exists because HC capture is reactive (entry hook on `HC_change_dream_shards`). A startup-time heap scan would let users skip step 4, at the cost of finding HC's typedesc/vtable[0] via a separate Ghidra dig. Not yet pursued.

## Unresolved

- **Path A test (in solo first):** call `gainShards(100)` after the entry hook has captured HC (any natural shard event), watch the HUD. If it updates → solo gold-farming is solved with a single 4-byte write. If not → HUD is event-driven, escalate to path B.
- **Path B implementation if needed:** wire `gainShardsCall(n)` to call `HC_change_dream_shards(HC, n, src_flags)` via `NativeFunction`. Two sub-options for `src_flags`:
  - **Cache a live `oCCustomFlagList*`** from `args[2]` of a natural shard event in the entry hook. Reuse it for synthetic gains. Cleanest if the engine doesn't mutate the cached object.
  - **Construct an empty `oCCustomFlagList`** in JS with `Memory.alloc` + vtable pointer to `oCCustomFlagList::vftable`. Riskier — engine might reject or crash on missing fields.
- **MP replication verification** — once path A or B works in solo, verify in MP: host calls it, peer's HUD should update if the gain reaches `ReplicaManager3`. Path A may not replicate (no event fired); path B should replicate (full natural pipeline).
- **Other field discoveries from the decompile** (worth their own investigation):
  - `HC+0x1d48` and `HC+0x1d78` are runtime stat-tracker pointers — the cumulative-earned and cumulative-spent values mirror through them. Useful if we want to forge total-earned for store-priced unlocks or "Total Dream shards purchase" stat-tracked rewards.
  - `HC+0x15d8` is the subscriber list head. Watching it grow during chapter init would reveal which game systems subscribe to shard changes (Hope Diamond, Heal-on-gain, achievement counters, etc.).
- **Can host affect peer local game state via Star of Fate?** Specifically, can host-side action mutate a peer's Star of Fate state? The shard wallet shows a shared-pool replication pattern; SoF is conventionally per-peer-persistent, but the path is not searched. Internal class name not yet pinned (`StarOfFate` / `Fate` / `PermanentTalent` / `SkillTree` all returned zero strings). Active follow-up.
- **Step-2 broadcast identity.** Where is the "boss arriving" RPC / replicated-flag broadcast in the chapter-timer-expiry handler? Discoverable via Ghidra: xref the function `forceBossSpawn` calls, walk one frame up to the natural caller, locate the broadcast. Goal: a `broadcastBossArriving()` Frida helper so MP boss arrival is fully natural for peers in future experiments.
- **Peer-side authority audit.** What can a peer mutate that replicates back to host / other peers? Talent picks, item pickups, character position. Tells us whether peer packets carry implicit trust or are validated server-side. Untested.
- **Boss-kill in MP.** Does any file get written when the host kills a boss in MP (not just `Profile_1.ob` — any file)? Does the chapter-end "next chapter" sequence fire for both peers? Flagged for a future test.
- **partyDataToken** — server-issued token tying Steam lobbies to Stormancer parties. Relevant if we ever want to drive MP from outside the UI. Not yet investigated.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template. Tight section since this finding is in-progress and architecture-focused; expand when `HC_change_dream_shards` and friends get full annotation.

| Symbol | Anchor |
|---|---|
| `HC_change_dream_shards` | Distinctive 3-arg signature `(HC*, int, oCCustomFlagList*)`; calls into the shard-replication path. xrefs from any natural shard-gain UI event (e.g. picking up a shard pickup). |
| `HC+0x1590` (raw shard wallet) | Re-derive: find the function that subscribes to `BOSS_DEFEATED` or shard-gain events, look at which `HC+0x...` it writes. |
| `HC+0x1d48`, `HC+0x1d78` (stat-tracker ptrs) | Stat-tracker classes have RTTI; xrefs from those vtables to the HC instance. |
| `HC+0x15d8` (subscriber list head) | Distinctive linked-list-head pattern; walk subscribers during chapter init. |
| `LobbyGs` | RTTI: `.?AVLobbyGs@@`. The lobby Game-State class. |
| `oCSLNetReplicationManagerSceneContext` | RTTI string; primary replication entry point. Vtable holds the three-mode enum. |
| `HostInfosMessage` RPC handler | Anchor via Stormancer / RakNet build-path strings (`C:\Workspace\oengine2\ThirdParty-Ext\RakNet`, `C:\ravenswatch\ravenswatch\ThirdParty-Ext\Stormancer`). |
| `oCCustomFlagList::vftable` | RTTI: `.?AVoCCustomFlagList@@`. Used as payload for named events. |

### Cross-finding anchoring

- `chapter-boss-portal-trigger.md` — `forceBossSpawn` is exercised in this finding's experiment; same anchors apply.
- `save-subsystem.md` — for any save-side cross-checks.

## Notes

- **Not yet annotated in Ghidra.** The architecture symbols (`LobbyGs`, `HostInfosMessage` RPC handler, `oCSLNetReplicationManagerSceneContext` vtable, the three-mode replication enum) are still at default names. Per CLAUDE.md "annotate findings on the spot," follow up by renaming these in Ghidra so future digs land in named territory.
- **Build paths leaked:** `C:\Workspace\oengine2\ThirdParty-Ext\RakNet\` and `C:\ravenswatch\ravenswatch\ThirdParty-Ext\Stormancer\stormancer\`. Useful for distinguishing engine-vendored third-party code from game-side glue.
- **Scope clarification:** this finding is about the *runtime* multiplayer architecture. Anything related to MP saving / persistence boundary (does anything cross MP → disk?) is explicitly out of scope here — open the question if and when the boss-kill MP test produces evidence.
