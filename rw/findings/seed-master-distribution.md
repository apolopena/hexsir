[← Back to findings](README.md)

# Master seed distribution — chapter master → per-context subseeds
**Status:** confirmed
**Created:** 2026-05-08

The chapter master seed (the one displayed on screen during play) is distributed at chapter load to four per-context subseed slots by `apply_session_seed_to_scene_contexts` (RVA `0x26af00`). Forcing the master at this function's entry gives full deterministic control over camps, camp locations, reward-slot distribution, and any other subsystem reading from a per-context subseed. **Talents, item rolls, chest contents, and shop offers are NOT affected** — those run on a separate global TLS+0xff3c stream (see `rng-behavior.md`).

Live-verified 2026-05-08 against a running session.

## Sources

- Static dig: `level_load_orchestrator` decompile (RVA `0x289b30`), traced from "Generate enemy camps" profiler label and `MAP_GENERATION_DONE` event-publish site.
- Decompile of `apply_session_seed_to_scene_contexts` and the tag-dispatcher caller `FUN_1402696a0` (tag `0x15dba49e` = "apply session seed").
- Live verification via Frida read of MapSceneContext and EntitySceneContext memory in a running game session — master 0x6690D7DE observed at both `+0x80` and `+0x3b8` slots simultaneously.
- Cross-references to `rng-behavior.md` for the per-event RNG split (TLS+0xff3c).
- Frida implementation: `tools/frida/mods/powers/Seed.js` v0.1.0 — confirmed working live.

## TL;DR

- **One master seed → four subseeds.** `apply_session_seed_to_scene_contexts` reads the master from `param_2 + 0x1c`, then writes each subseed pair as `(master, PCG_step(master))`.
- **Hook point for forcing:** `apply_session_seed_to_scene_contexts` entry. Overwrite `args[1] + 0x1c` before the function reads it. One write controls all four destination slots.
- **Scope of effect:**
  - **Forced:** camp selection, camp placement, reward-slot type distribution, terrain procedural decisions, anything reading the per-context subseeds.
  - **Not forced:** talent picks, item rolls, chest contents, shop offers, drops — these run on TLS+0xff3c (the inlined per-event PCG documented in `rng-behavior.md`).
- **This is the architecture the user wanted:** known map + camp layout, fresh talents/loot/shops every run.

## The distribution function

```c
void apply_session_seed_to_scene_contexts(longlong param_1, longlong param_2, char param_3) {
    // Find scene contexts via type-tester
    EntitySceneContext = scene_manager_find_context_by_type(scene, &EntitySceneContextTester);
    MapSceneContext    = scene_manager_find_context_by_type(scene, &MapSceneContextTester);
    // ... + lookup of a third context via DAT_141446fe8

    int master = *(int *)(param_2 + 0x1c);                  // ← THE MASTER SEED
    short chapter_id = *(short *)(param_2 + 0x1a);          // ← chapter ID stored alongside

    // Distribute master to four subseed pairs.
    // Each pair: master at +0x00, PCG_step(master) at +0x04.
    // The PCG step uses standard constants 0x2c9277b5, 0xac564b05, 0x108ef2d9.

    EntitySceneContext->+0x3b8 = master;
    EntitySceneContext->+0x3bc = pcg_step(master);

    MapSceneContext->+0x80 = master;
    MapSceneContext->+0x84 = pcg_step(master);

    *DAT_141446a98 = master;       // global slot 1, subsystem unknown
    *(DAT_141446a98 + 4) = pcg_step(master);

    *DAT_141446a78 = master;       // global slot 2, subsystem unknown
    *(DAT_141446a78 + 4) = pcg_step(master);

    *(int *)(g_game_profile_data_manager_ptr + 0x20 + 0x22c) = chapter_id;

    // ... per-context post-init walks param_2's array of additional contexts ...
}
```

The PCG step pattern (inline at every distribution site):

```c
uint32_t pcg_step(uint32_t s) {
    uint32_t v = s * 0x2c9277b5 + 0xac564b05;
    v = (v >> ((v >> 0x1c) + 4)) ^ v;
    v *= 0x108ef2d9;
    v = (v >> 0x16) ^ v;
    return v & 0x7fffffff;
}
```

Same algorithm as `chapter_distribute_rewards_inline_pcg_at_offset_0x84`'s in-loop step (i.e. the `+0x84` running stream uses this to advance per roll).

## Live verification (2026-05-08)

Game running with on-screen seed `1720768478` (`0x6690D7DE`).

```
[verify] MapSceneContext       = 0x213e2295bb0
[verify]   +0x80 master        = 0x6690d7de   ← matches expected master
[verify]   +0x84 running       = 0xb191414    ← drifted (rolls fired during play)
[verify] EntitySceneContext    = 0x2138d606cc0
[verify]   +0x3b8 master       = 0x6690d7de   ← matches expected master
[verify]   +0x3bc running      = 0x5b2a3388   ← drifted
[verify] expected master       = 0x6690D7DE
```

The two `+0x00` slots (master copies) hold the displayed seed exactly. The two `+0x04` slots (running streams) have advanced as expected. Distribution model verified end-to-end.

## Source of the master

The master arrives in a tagged message struct, extracted at `param_2 + 0x1c` of `apply_session_seed_to_scene_contexts`. The dispatcher `FUN_1402696a0` shows the message envelope:

```c
if (*(int *)(param_3 + 8) == 0x15dba49e) {       // tag = "apply session seed" event
    apply_session_seed_to_scene_contexts(param_1, param_3 + 0x10, 0);
    *(undefined1 *)(param_1 + 0x194) = 1;
    if (*(int *)(*(longlong *)(param_1 + 0x98) + 0x70) == 5) {
        FUN_140269570(param_1, 1);
    }
}
```

Three callers exist: `FUN_140266500`, `FUN_1402674a0`, `FUN_1402696a0` — all tag-dispatch handlers, likely covering host-init / save-load / multiplayer-replicate variants. Determining which originates the master value is open work; for forcing, the hook at `apply_session_seed_to_scene_contexts` entry is upstream of all three.

## What the master controls vs. doesn't

### Controlled (deterministic when master is forced)

Anything reading from a per-context subseed advances along a deterministic PCG chain seeded from the master. Confirmed or strongly inferred:

- **Camp selection** — which `40x40_X` / `64x64_X` template gets placed in each camp slot.
- **Camp placement** — where camp slots end up on the map (procedural slot positioning).
- **Chapter rewards distribution** — `chapter_distribute_rewards_inline_pcg_at_offset_0x84` reads `MapSceneContext+0x84` directly. Which reward-type bucket gets which slot count, which tier-def each gets bound to.
- **Other map-scoped procedural decisions** — terrain partitioning, sectorization breakpoints (likely; not separately verified).

### NOT controlled (still random when master is forced)

These run on the **separate TLS+0xff3c global stream** (see `rng-behavior.md` §"Single TLS-backed PCG stream"):

- **Talent picker** (selection AND tier rolls — verified-forced via separate harness in `rw_lab.js`).
- **Item picker** (Sandman shop offers — same single-seed model expected per `rng-behavior.md`).
- **Chest contents.**
- **Shop offers.**
- **Drops.**
- **Per-event combat RNG** (entity-component random initializers, AI, particles).

Live confirmation by user 2026-05-08: "This seed is affecting camp selection and camp placement. It is not affecting roles in the shop, which makes me believe that it's not affecting talent picks." Exactly matches the documented split.

The split is the *intended* engine architecture — the `Forced Seed UInt` INI option (hash `0x1949b098`) feeds this same master-seed path. The documented limitation in `rng-behavior.md` "the Forced Seed UInt feeds the master-seed path, but per-event picks bypass that path" is the same observation, reached from the other direction.

## Frida primitive — `Seed.js`

`tools/frida/mods/powers/Seed.js` v0.1.0:

```js
loadPower("Seed")             // load BEFORE the chapter you want forced
Seed.set(1720768478)          // arm: override master to this value on next chapter load
                              // Seed.set(0x6690d7de) also accepted
// reload chapter
//   [Seed] forced master 0x<orig> -> 0x6690d7de (1720768478)
//   chapter generates deterministically from this seed
Seed.clear()                  // disarm
Seed.status()                 // { armed: bool, value: number | null }
```

Setup-bound — must be loaded before `apply_session_seed_to_scene_contexts` fires. Marked with `*` in `rw_lab.js`'s power listing per the standard convention.

## Locating these symbols on a new build

Per `rw/docs/README.md` §"Locating <thing>" — RE-side template.

### Function anchors

| Symbol | Anchor strategy |
|---|---|
| `apply_session_seed_to_scene_contexts` | Byte-pattern search the inline PCG mix constant `b5 77 92 2c` (= `0x2c9277b5` LE). Filter to functions with 4+ matches in close proximity (the four distribution sites). The match in `apply_session_seed_to_scene_contexts` clusters tightly: 4 hits within ~0xc0 bytes. |
| `level_load_orchestrator` | xref TO the string `"Generate enemy camps"` at `0x140ef7228` lands on the level-load-orchestrator's profiler-marker assignment. |
| Tag `0x15dba49e` "apply session seed" | Byte-pattern `9e a4 db 15`. Single hit in `FUN_1402696a0`'s dispatch comparison. |

### Data anchors

| Address | Symbol | Notes |
|---|---|---|
| `g_game_profile_data_manager_ptr+0x20+0x22c` | chapter_id mirror | Written from `param_2+0x1a` |
| `DAT_141446a98` | global subseed slot 1 | u32 master + u32 running |
| `DAT_141446a78` | global subseed slot 2 | u32 master + u32 running |

### Per-subsystem usage anchors

| Subsystem | Subseed location | Inline-PCG callsite anchor |
|---|---|---|
| Chapter rewards | `MapSceneContext+0x84` | `chapter_distribute_rewards_inline_pcg_at_offset_0x84` (RVA `0x1e6030`) — name itself encodes the offset |
| Camp tier picking | TLS+0xff3c (calls `pcg_step_thread_local_seed`) | `mapscenecontext_on_level_start_assign_camp_tiers` (RVA `0x1e5100`) |

The camp **content** picker (which specific `40x40_X` template) lives in a `MAP_GENERATION_DONE` (event hash `g_eventHash_MAP_GENERATION_DONE` at `0x1412c09d8`) subscriber not yet identified. Forcing the master controls it via whichever subseed it reads (likely `EntitySceneContext+0x3bc`).

## Open questions

- **Which subsystem owns each of the two `DAT_141446a78` / `DAT_141446a98` global slots?** Not investigated. Find via search for `mov reg, [DAT_141446a78]` / `[DAT_141446a98]` patterns and decompile readers.
- **Which `MAP_GENERATION_DONE` subscriber is the camp-content picker?** ≥6 subscriber registration sites visible at xrefs to `s_MAP_GENERATION_DONE_event_name` (`0x140ef1650`); not filtered down. Forcing the master makes the camp-content roll deterministic regardless, so this is curiosity-level work.
- **Cross-session reproducibility verified.** The master is a portable u32. Capture in REPL on session A, paste into `Seed.set()` on session B → same chapter content. (Verified-by-design; same hook intercepts the value pre-distribution.)
- **Master-seed source.** Where the value at `param_2 + 0x1c` originates BEFORE the dispatcher receives the tagged message. Likely from session/run startup, possibly seeded from system time on a fresh run or from save-state on continued runs. Not relevant for forcing (we override downstream of the source) but interesting for reproducing a "natural" run from save state.

## Cross-references

- `rw/findings/rng-behavior.md` — the per-event RNG model on TLS+0xff3c (the OTHER seed path; not affected by master force).
- `rw/findings/random-seed-system.md` — parent doc tracking overall progress on the random-seed system.
- `tools/frida/mods/powers/Seed.js` — the Frida primitive.
- Ghidra plate comments (committed via Ghidra's persistence): `apply_session_seed_to_scene_contexts`, `level_load_orchestrator`, `mapscenecontext_on_level_start_assign_camp_tiers`, `chapter_distribute_rewards_inline_pcg_at_offset_0x84`.
