# Frida script code standards

Opinionated rules for Frida scripts in this directory. Following them keeps
files small, the REPL discoverable, and reloads non-destructive. **Read this
before adding a new power, mod, or helper to `rw_lab.js`.**

## Project layout

```
tools/frida/
├── rw_lab.js                  # central hub: globals, mod/power loader,
│                              # shared utilities (RW.after, RW.help, ...),
│                              # legacy harnesses still in flight
├── mods/
│   ├── <name>.js              # regular mods (e.g. boss_rush, hello)
│   └── powers/
│       └── <Name>.js          # individual gameplay-affecting capabilities
└── CODE_STANDARDS.md          # this file
```

`rw_lab.js` is the only script you launch directly. Everything else is loaded
on demand from inside the REPL via `loadMod("name")` or `loadPower("Name")`.

## Powers vs mods

A **power** is a single self-contained gameplay capability with a focused
public API: e.g. `Teleport`, `ChapterBoss`. They live under `mods/powers/`,
filenames are PascalCase, the file's top-level namespace matches the
filename. Loaded via `loadPower("Name")`. Each power gets registered as
`power:Name` in `RW.mods` so `status()` can distinguish them.

A **mod** is anything else — research scaffolding, a one-off probe, a hub
of related read-only helpers (e.g. `boss_rush` with its encyclopedia walker
and resolver capture). Filenames are lowercase / snake_case. Loaded via
`loadMod("name")`.

When in doubt: if it has a clean callable surface a non-RE user would
invoke, it's probably a power. If it's research goo, it's a mod.

## Naming

| Thing | Convention | Example |
|---|---|---|
| Power file | `PascalCase` noun | `Teleport.js`, `ChapterBoss.js` |
| Power namespace | matches filename exactly | `RW.Teleport`, `RW.ChapterBoss` |
| Method | `camelCase`, preposition or verb | `Teleport.to`, `Teleport.refresh` |
| Read-only getter | `camelCase` noun, no `get` prefix | `Teleport.position()` |
| Delay variant | `delay<Verb>(seconds, ...sameArgs)` | `Teleport.delayBy(2, 5, 0, 0)` |
| Mod file | `lowercase` or `snake_case` | `boss_rush.js`, `hello.js` |
| Module-private state | `_underscorePrefix` on `RW` | `RW._chapterBossState` |
| Offset / RVA / fixed tuning | `SCREAMING_SNAKE_CASE` | `BT_ELAPSED_OFF`, `TARGET_RVA`, `HEAP_SCAN_CHUNK` |
| Log prefix | `[<Name>]` or `[<Name>.method]` | `[Teleport] to (5,0,0)` |

The method should read naturally in English after the namespace:
"Teleport **to** coords", "Teleport **by** delta", "ChapterBoss, **spawn**".

**Noun vs verb is the implicit getter/setter convention:**

- Bare-noun method = pure read returning data (`Teleport.position()`).
  No `get` prefix — that's Java-bean-style and considered clunky in
  modern JS.
- Verb / preposition method = action with side effects
  (`Teleport.to(x,y,z)`, `Teleport.refresh()`).

If a getter feels ambiguous, rename it to a different noun
(`coords()`, `where()`) before adding a `get` prefix.

## The docstring contract

Every public method gets a docstring immediately above its definition.
A docstring is **one block comment** with **two fence lines** inside it.
Fence #1 opens the user-facing help section; fence #2 closes it.
Anything below fence #2 (still inside the same block) is **MECHANISM** —
developer notes, RVAs, decompile reasoning — visible in the source but
NOT parsed into `help()`.

A fence is a line that, after stripping the leading ` * ` block-comment
prefix, is three or more `-` characters and nothing else.

```js
    /*
     * ----------------------------------------------------------------
     * Teleport.to(x: number, y: number, z: number): void
     *
     * Absolute teleport. Visible character snaps on the next frame.
     *
     * Result: logs "[Teleport] to (x,y,z)"; returns void.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Calls oCEntity::setPosition at vtable[+0x50] (RVA 0x6ca7f0).
     *   Engine writes +0x324 and broadcasts to subscribers at +0x3a8.
     */
    Teleport.to = function (x, y, z) { ... };
```

`rw_lab.js` parses this at `loadPower` time. The lookup key is the text
before the `(` of the signature line — `Teleport.to` here — so
`help("Teleport.to")` prints the section between the two fences.

**Required prose fields between the fences**, in this order:

1. **TS-style signature** as the first non-blank line.
2. **One-line summary** of what the function does.
3. **Usage** examples for non-trivial signatures.
4. **Result** — what visibly changes, what the function returns, side
   effects, log lines emitted.
5. **Caveats** for edge cases (no-op conditions, capture-required state,
   pointer staleness across chapter reloads, etc.).

**MECHANISM section below fence #2** is optional but encouraged for any
non-trivial implementation. It's where to put: which RVAs / vtable
slots are touched, which decompile findings inform the impl, which
engine event chain we're triggering. The user reading `help()` doesn't
need this; the next maintainer modifying the function does.

**Block comments without two fence lines are ignored by the parser** —
that's how regular block comments and commented-out code stay invisible
to `help()`.

## Where named values live

Don't sprinkle magic literals through code; every byte offset, RVA,
threshold, or tuning constant gets a name. Placement rule, in order of
preference:

- **Used across multiple files** → hang it on `RW.*` or expose it from
  `rw_lab.js`.
- **Part of the file's domain vocabulary** → file scope (just inside
  the IIFE), even if only one function references it today. A
  domain-focused file (e.g. `ChapterBoss.js` is "all about the
  BossTimer field block") will likely grow more functions that touch
  the same fields; declaring them once up front documents the
  vocabulary and keeps additions cheap.
- **Tied to one method's specific concern** → declare at the top of
  that method as a local `var`. This is the right call when each
  method touches a *different* entity (e.g. `Currency.addShards` reads
  HC+0x1590, `Currency.addStars` reads a different field — the offsets
  are method-local because they don't share a domain).

```js
// good — domain vocabulary at file scope (every fn here touches the
// BossTimer field block; future fns likely will too):
var BT_ELAPSED_OFF   = 0x12c;
var BT_BOSS_TIME_OFF = 0x144;
ChapterBoss.spawn  = function () { ... BT_ELAPSED_OFF ... };
ChapterBoss.status = function () { ... BT_BOSS_TIME_OFF ... };

// good — method-local because Currency bundles unrelated entities and
// each method reads a *different* field:
Currency.addShards = function (n) {
    var HC_HELD_SHARDS_OFF = 0x1590;
    ...
};
Currency.addStars = function (n) {
    var HC_HELD_STARS_OFF = 0x????;   // different field, scoped here
    ...
};
```

Heuristic: if extracting the constant to file scope would feel like
bringing in vocabulary that doesn't belong in the file's domain, it
stays method-local. If it's "the file's domain again," it goes up.

A constant you only reference inside a docstring (e.g. for context in
MECHANISM) does NOT need a declaration — write the literal in the
prose. Declarations are for code that uses them.

## State & re-load safety

`loadPower("X")` and `loadMod("y")` re-evaluate the file on every call.
Files must therefore be idempotent under re-eval. Concretely:

**Don't use top-level `const` / `let`** in a mod or power file. They will
throw on the second eval ("identifier already declared"). Use `var`, or
attach to `RW`. The IIFE pattern at the top of every file gives you a
private scope without leaking, but anything you want to survive across
re-loads must hang off `RW`.

**Guard initial state.** Do this:

```js
if (!RW.Teleport) RW.Teleport = {};
var Teleport = RW.Teleport;
```

That preserves user-set fields across reloads. Don't blindly overwrite
`RW.Teleport = {}` at the top — you'll wipe captured pointers.

**Detach hooks before re-arming.** The Interceptor attach in `Teleport`'s
refresh path explicitly detaches a prior hook before installing a new
one. If you don't, every reload stacks another Interceptor on the same
RVA — they won't conflict but they'll all fire on every call, and you
can't easily clean them up.

```js
if (Teleport._captureHook) {
    try { Teleport._captureHook.detach(); } catch (e) {}
    Teleport._captureHook = null;
}
Teleport._captureHook = Interceptor.attach(...);
```

**Cross-power state sharing.** Sometimes two powers need the same
runtime pointer that's most cheaply captured by one of them. Example:
`Currency` writes through the HC pointer; `Teleport`'s frame-tick hook
captures HC every frame anyway. Rather than installing a second hook
on the same RVA, `Teleport` exposes `Teleport.hc` as a public
read-only field, and `Currency.addShards` reads it as a fallback when
its own (rare-event) capture hasn't fired yet. Rules for this:

- The producer power exposes a documented read-only field on its
  namespace (`Teleport.hc`, not `Teleport._hc`).
- The producer's REPL-surface header lists the field with a one-line
  note that it's exposed for cross-power sharing.
- The consumer power treats it as a *fallback* — its primary capture
  path stays in place; the borrow is opportunistic.
- The consumer's MECHANISM section names the producer explicitly so
  the dependency is visible to anyone reading the source.
- Consumers MUST NOT write to the producer's field. One writer.
- If a third power would also benefit, promote the field to a shared
  utility (`RW.hc`) before the coupling sprawls.

**Hook ownership: powers own their hooks; mods compose by loading
powers, not by re-hooking.** If a power exposes capability X via a hook
on RVA `0xfoo`, a mod that needs X should call `loadPower("X")` and
use the power's API rather than installing its own Interceptor on
`0xfoo`. Stacking independent hooks on the same RVA fires both on
every call (no collision but doubled cost + log noise) and tightly
couples the mod to internals it didn't audit. This is the only real
multi-load risk; idempotent loads are the design's normal case.

## Resolving DLL exports

Use `Process.findModuleByName("dll").findExportByName("Func")` — the instance
form. The static `Module.findExportByName(...)` was removed in newer Frida and
throws `TypeError: not a function` on load. Null-check the module: DLLs like
`winhttp.dll` may not be loaded yet when a power evaluates.

## Logging

Every log line starts with `[<Name>]` or `[<Name>.method]` so output is
greppable. Don't use bare `console.log("hello")` — it pollutes the REPL
and is unfindable in the diag log.

Hot-path hooks (called every frame) should do as little work as possible.
A frame-tick `onEnter` that captures one pointer is fine; one that
parses strings or formats output is not. Push that work to the on-demand
methods (`status()`, etc.) where the user pays the cost only on call.

## Shared utilities

`rw_lab.js` exposes utilities that powers and mods should reuse rather
than reimplement:

| Utility | Purpose |
|---|---|
| `RW.after(seconds, fn)` | Wall-clock delay (validated `setTimeout`). Use in `delay<Verb>` helpers; not pause-aware. |
| `RW.docs[key]` | Auto-populated by `loadPower`. Read-only from power code. |
| `RW.help(target?)` | Lists or shows docstrings. Not for power code; user-facing. |
| `RW.registerMod(name, version)` | Call once per power/mod with version string. |

Powers should NOT define their own `setTimeout` wrappers, their own log
prefix conventions, or their own re-load guards. If you need new shared
behavior, add it to `rw_lab.js` first and reference it.

## Delays

Default `delay<Verb>(seconds, ...sameArgs)` helpers wrap `RW.after` —
fires N seconds from now and runs the immediate primitive. Implementation
is a one-liner per power:

```js
Teleport.delayBy = function (seconds, dx, dy, dz) {
    RW.after(seconds, function () { Teleport.by(dx, dy, dz); });
};
```

**Caveats common to all `delay<Verb>` helpers:**

- Fires on the host clock regardless of game state. The deferred
  primitive will still run if you pause the game, but whether its
  effect is visible depends on the primitive.
- Captured pointers must remain valid for the delay window. A chapter
  reload between scheduling and firing usually invalidates them; the
  deferred call will log "no player" or similar and silently no-op.
- For relative ops (`delayBy`), the delta is applied to the position at
  *firing time*, not at *call time*. If the player walks during the
  delay, the shift starts from wherever they end up.

**Engine-tick delay (different mechanism, call out explicitly):** some
powers schedule via in-game timer fields rather than via `RW.after`,
so the engine's own update loop fires the action. Example:
`ChapterBoss.delaySpawn` writes `elapsed = boss_time - seconds` so the
natural `BossTimer` comparison fires after `seconds` of *game time*
(scaled by speedMult, paused when the game pauses). Such variants must
say "engine-tick delay" in their docstring so readers know they
behave differently from the default.

**Docstring convention for delay variants:** point to this section
instead of repeating the caveats. One-liner like:

```
// Teleport.delayBy(seconds: number, dx: number, dy: number, dz: number): void
//
// Delayed Teleport.by. See CODE_STANDARDS.md §Delays.
```

The reader follows the link; the source of truth lives in one place.

## Top-level REPL aliases

The last line of every power file is the REPL convenience alias:

```js
var Teleport = RW.Teleport;
```

This binds the namespace to a global `var` so REPL users can type
`Teleport.to(...)` instead of `RW.Teleport.to(...)`. Power code itself
should always reference through `RW.<Name>` internally — the top-level
alias is purely for ergonomics.

## Discovery marker for setup-bound powers

Most powers' hooks fire continuously and can be loaded any time
(`ChapterBoss`'s frame-tick capture, `Teleport`'s player frame-tick).
A few must be loaded before a one-shot setup window — typically a
chapter or a game launch — because their hook captures events that
only fire during that window. Mark these in `rw_lab.js`'s power
listing with a trailing `*` plus the shared footnote: `* = load before
chapter (or game) start — the power's hook arms during setup`.
`Hourglass` is the current example: chapter setup ctors the hourglass
spawner; the ctor hook must already be attached.

Quiet by default for periodic powers. If a power has an interval
mode (e.g. `spawnItem({ intervalMs })`), don't log per-tick — that
floods the REPL. Expose a `verbose: true` opt for debugging.

## Validation checklist for a new power

Before considering a new power "done":

- [ ] File path: `mods/powers/<PascalCaseNoun>.js`
- [ ] Namespace: `RW.<SameAsFilename>` and top-level `var <name> = RW.<name>`
- [ ] Methods are camelCase and read naturally after the namespace
- [ ] Delay variants follow `delay<Verb>(seconds, ...sameArgs)` and use `RW.after`
- [ ] Every public method has a fenced docstring with TS-style signature
- [ ] State is on `RW`, guarded with `if (!RW._x) RW._x = {}`
- [ ] Hooks are tracked + re-detached on re-load
- [ ] DLL exports resolved via `Process.findModuleByName(...).findExportByName(...)`, not the removed static `Module.findExportByName`
- [ ] `RW.registerMod("power:<Name>", version)` is called
- [ ] Log lines all use `[<Name>]` prefix
- [ ] If the hook arms during chapter/game setup, marked with `*` in `rw_lab.js`'s power listing
- [ ] Periodic methods are quiet by default; debug logs gated behind `verbose: true`
- [ ] `loadPower("<Name>")` followed by `help("<Name>")` shows every method
- [ ] No top-level `const` / `let` (only `var` / IIFE / `RW.*` assignments)
