// Hourglass.js — fire the chapter hourglass's reward-item spawner on demand.
//
// Thin wrapper around the verified working primitive in spawner_probe.js
// (rw/findings/entity-spawner-mechanism.md §"Live work — 2026-05-07
// follow-up"). The hourglass's parent settings name is "NoModel+2Cpnt"
// (the engine's auto-name for "no base model + 2 attached components");
// sub-index 0 of its spawner pair drops the early-boss-reward item —
// normally only granted on boss-kill before the timer expires.
//
// Working flow:
//   loadPower("Hourglass")        // auto-loads + arms spawner_probe's ctor hook
//   <reload chapter>              // ctor hook captures every spawner ctor'd at load
//   <walk out of safe area>       // (optional) puts hourglass into active state
//   Hourglass.spawnItem()                            // fire reward once (quiet)
//   Hourglass.spawnItem({ intervalMs: 2000 })        // fire every 2s (quiet)
//   Hourglass.spawnItem({ verbose: true })           // pass underlying logs through
//   Hourglass.spawnItemStop()                        // stop the interval
//
// Default is silent — the underlying SpawnerProbe.expr_summonAtPlayer is
// chatty (multiple log lines per call) which floods the REPL on intervals.
// Pass { verbose: true } to opt in to those logs for one-shot debugging.
//
// Depends on:
//   - rw_lab.js (RW.* hub)
//   - mods/spawner_probe.js (auto-loaded)

(function () {
    var version = "0.3.0";
    if (typeof RW !== "object") {
        console.log("[Hourglass] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    if (!RW.Hourglass) RW.Hourglass = {};
    var Hourglass = RW.Hourglass;
    Hourglass._timer = Hourglass._timer || null;

    // Re-load safety: clear any prior interval before re-arming.
    if (Hourglass._timer) {
        try { clearInterval(Hourglass._timer); } catch (e) {}
        Hourglass._timer = null;
    }

    // Ensure spawner_probe is loaded and its ctor hook is armed. Does NOT
    // re-arm if the hook is already attached — that would clobber
    // SpawnerProbe._spawners and lose the user's capture set.
    function ensureSpawnerProbe() {
        if (!RW.SpawnerProbe || typeof RW.SpawnerProbe.expr_summonAtPlayer !== 'function') {
            try { RW.loadMod("spawner_probe"); }
            catch (e) {
                console.log("[Hourglass] could not load spawner_probe: " + e.message);
                return false;
            }
        }
        if (!RW.SpawnerProbe || typeof RW.SpawnerProbe.expr_summonAtPlayer !== 'function') {
            return false;
        }
        if (!RW.SpawnerProbe._ctorHook) {
            RW.SpawnerProbe.expr_armSpawnerCtor();
        }
        return true;
    }

    ensureSpawnerProbe();

    // Run fn with console.log temporarily silenced. Restored even on throw.
    function silenced(fn) {
        var orig = console.log;
        console.log = function () {};
        try { return fn(); }
        finally { console.log = orig; }
    }

    /*
     * ----------------------------------------------------------------
     * Hourglass.spawnItem(opts?: { intervalMs?: number, verbose?: boolean }): object | null
     *
     * Fire the chapter hourglass's reward-item spawner. The drop is the
     * early-boss-reward item — normally only granted upon defeating
     * the chapter boss before the hourglass timer expires.
     *
     * Without opts: fires ONCE silently and returns the spawner record
     *   from the underlying SpawnerProbe.expr_summonAtPlayer call.
     * With opts.intervalMs: fires every intervalMs ms until
     *   spawnItemStop() is called; returns null. Calling spawnItem with
     *   intervalMs again replaces the active timer.
     * With opts.verbose: lets the underlying primitive's log lines
     *   through (selected/fired/etc.). Default false to keep interval
     *   mode from flooding the REPL.
     *
     * Prerequisites:
     *   spawner_probe's ctor hook must have captured the hourglass at
     *   chapter load. loadPower("Hourglass") auto-arms the hook the
     *   first time it's loaded; subsequently you only need a chapter
     *   reload if the captured set was cleared (e.g. by a manual
     *   SpawnerProbe.expr_armSpawnerCtor() between sessions).
     *
     * Usage:
     *   loadPower("Hourglass")
     *   <reload chapter, walk out of safe area>
     *   Hourglass.spawnItem()                            // quiet one-shot
     *   Hourglass.spawnItem({ intervalMs: 2000 })        // quiet interval
     *   Hourglass.spawnItem({ verbose: true })           // see underlying logs
     *   Hourglass.spawnItemStop()                        // stop interval
     *
     * Result:
     *   Each fire produces an item drop at the hourglass's natural
     *   position. Pre-active hourglass: one fire per state transition.
     *   Active hourglass: re-fires indefinitely.
     *
     * Caveats:
     *   - If a quiet fire silently no-ops, retry with verbose:true to
     *     see why (typically: chapter-reload needed, or the hourglass
     *     wasn't in an unfired state).
     *   - Fast intervals (< 250 ms) may overrun the spawn allocator.
     *     Default ≥ 1000 ms is safe.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Delegates to RW.SpawnerProbe.expr_summonAtPlayer({
     *     nameMatch: "NoModel+2Cpnt", index: 0, noWarp: true
     *   }), which walks SpawnerProbe._spawners (populated by the
     *   spawner-ctor hook on FUN_1402d0ee0, RVA 0x2d0ee0), finds the
     *   spawner whose parent settings name is "NoModel+2Cpnt" at
     *   sub-index 0, and calls FUN_1406f62b0 (RVA 0x6f62b0) — the
     *   broadcast worker the engine itself uses internally during
     *   natural activation. noWarp:true skips the parent-warp so the
     *   spawn fires at the spawner's natural bound transform (the
     *   hourglass's location). Quiet mode wraps the call in a
     *   console.log redirect; verbose mode lets the underlying logs
     *   pass through.
     */
    Hourglass.spawnItem = function (opts) {
        var intervalMs = (opts && typeof opts.intervalMs === 'number') ? opts.intervalMs : 0;
        var verbose    = !!(opts && opts.verbose);

        if (!ensureSpawnerProbe()) {
            console.log("[Hourglass.spawnItem] spawner_probe unavailable");
            return null;
        }

        var fire = function () {
            var fireArgs = { nameMatch: "NoModel+2Cpnt", index: 0, noWarp: true };
            if (verbose) return RW.SpawnerProbe.expr_summonAtPlayer(fireArgs);
            return silenced(function () { return RW.SpawnerProbe.expr_summonAtPlayer(fireArgs); });
        };

        if (intervalMs > 0) {
            if (Hourglass._timer) {
                try { clearInterval(Hourglass._timer); } catch (e) {}
                Hourglass._timer = null;
            }
            Hourglass._timer = setInterval(function () {
                try { fire(); }
                catch (e) {
                    console.log("[Hourglass.spawnItem] tick threw: " + e.message + " — stopping");
                    try { clearInterval(Hourglass._timer); } catch (er) {}
                    Hourglass._timer = null;
                }
            }, intervalMs);
            console.log("[Hourglass.spawnItem] interval " + intervalMs +
                        "ms — call Hourglass.spawnItemStop() to stop");
            return null;
        }

        return fire();
    };

    /*
     * ----------------------------------------------------------------
     * Hourglass.spawnItemStop(): void
     *
     * Stop the interval timer started by spawnItem({ intervalMs }).
     * No-op if no timer is running.
     * ----------------------------------------------------------------
     */
    Hourglass.spawnItemStop = function () {
        if (!Hourglass._timer) {
            console.log("[Hourglass.spawnItemStop] no active timer");
            return;
        }
        try { clearInterval(Hourglass._timer); } catch (e) {}
        Hourglass._timer = null;
        console.log("[Hourglass.spawnItemStop] stopped");
    };

    RW.registerMod("power:Hourglass", version);
    console.log("[Hourglass] " + version + " loaded.");
    console.log("[Hourglass]   spawnItem()                          — fire reward once (quiet)");
    console.log("[Hourglass]   spawnItem({ intervalMs: 2000 })      — fire every 2s (quiet)");
    console.log("[Hourglass]   spawnItem({ verbose: true })         — pass underlying logs through");
    console.log("[Hourglass]   spawnItemStop()                      — stop the interval timer");
})();

// Top-level alias for REPL convenience
var Hourglass = RW.Hourglass;
