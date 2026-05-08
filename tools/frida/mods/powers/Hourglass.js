// Hourglass.js — fire the chapter hourglass's reward-item spawner on demand.
//
// Standalone power. Hooks oCEntityCpntEntitySpawner_ctor (RVA 0x2d0ee0) at
// IIFE time, captures every spawner ctor'd during chapter setup, filters to
// the one whose parent's settings name is "NoModel+2Cpnt" (sub-index 0 = the
// early-boss-reward item), and fires it via FUN_1406f62b0 (RVA 0x6f62b0).
// No spawner_probe dependency.
//
// Working flow:
//   loadPower("Hourglass")        // BEFORE chapter loads — arms ctor hook
//   <load chapter>                // hook captures every spawner ctor'd at setup
//   <walk out of safe area>       // (optional) puts hourglass into active state
//   Hourglass.spawnItem()                            // fire reward once (quiet)
//   Hourglass.spawnItem({ intervalMs: 2000 })        // fire every 2s (quiet)
//   Hourglass.spawnItem({ verbose: true })           // log selection + fire
//   Hourglass.spawnItemStop()                        // stop interval
//
// Pre-active hourglass: one fire per state transition, then silently dropped.
// Active hourglass (player has left the starting safe zone): re-fires
// indefinitely.
//
// Depends on:
//   - rw_lab.js (RW.* hub)

(function () {
    var version = "0.4.0";
    if (typeof RW !== "object") {
        console.log("[Hourglass] FATAL: RW missing — load rw_lab.js first");
        return;
    }
    var rwMod = Process.findModuleByName("Ravenswatch.exe");
    if (!rwMod) { console.log("[Hourglass] FATAL: no Ravenswatch.exe"); return; }
    var IMG = rwMod.base;

    // Domain vocabulary — every offset names a field on either an
    // oCEntityCpntEntitySpawner instance or its parent oCEntity.
    // Cross-references rw/findings/entity-spawner-mechanism.md.
    var SPAWNER_CTOR_RVA       = 0x2d0ee0;   // FUN_1402d0ee0 — oCEntityCpntEntitySpawner ctor
    var BROADCAST_FIRE_RVA     = 0x6f62b0;   // FUN_1406f62b0 — broadcast worker (the spawn primitive)
    var SPAWNER_PARENT_OFF     = 0x08;       // spawner.+0x08 = parent oCEntity*
    var SPAWNER_FLAGS_OFF      = 0x64;       // spawner.+0x64 byte; bit 3 set = consumed
    var SPAWNER_CONSUMED_BIT   = 0x08;       // bit 3 of +0x64
    var ENTITY_SETTINGS_OFF    = 0x28;       // entity.+0x28 = oCEntitySettings*
    var SETTINGS_NAME_PTR_OFF  = 0x08;       // settings.+0x08 = char* name
    var SETTINGS_NAME_LEN_OFF  = 0x10;       // settings.+0x10 = u32 length
    var HOURGLASS_PARENT_NAME  = "NoModel+2Cpnt";
    var HOURGLASS_REWARD_INDEX = 0;          // sub-index 0 of hourglass spawner pair

    if (!RW.Hourglass) RW.Hourglass = {};
    var Hourglass = RW.Hourglass;
    Hourglass._spawners = Hourglass._spawners || [];
    Hourglass._ctorHook = Hourglass._ctorHook || null;
    Hourglass._timer    = Hourglass._timer    || null;

    // Re-load safety: detach prior ctor hook + clear interval before
    // re-arming. Captures persist across re-loads so an edit-and-loadPower
    // cycle doesn't lose the working set.
    if (Hourglass._ctorHook) {
        try { Hourglass._ctorHook.detach(); } catch (e) {}
        Hourglass._ctorHook = null;
    }
    if (Hourglass._timer) {
        try { clearInterval(Hourglass._timer); } catch (e) {}
        Hourglass._timer = null;
    }
    Hourglass._ctorHook = Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
        onEnter: function (args) {
            try { Hourglass._spawners.push(ptr(args[0])); }
            catch (e) {}
        }
    });

    var fireFn = new NativeFunction(IMG.add(BROADCAST_FIRE_RVA), 'void', ['pointer']);

    function readSettingsName(settings) {
        try {
            if (!settings || settings.isNull()) return null;
            if (settings.toString() === '0xffffffffffffffff') return null;
            var p = settings.add(SETTINGS_NAME_PTR_OFF).readPointer();
            var n = settings.add(SETTINGS_NAME_LEN_OFF).readU32();
            if (n <= 0 || n > 512) return null;
            return p.readUtf8String(n);
        } catch (e) { return null; }
    }

    // Walk the captured spawner list in capture order; among the
    // unfired spawners (bit 3 of +0x64 clear), substring-match
    // "NoModel+2Cpnt" (case-insensitive) against either the spawner's
    // own settings name (+0x10) or the parent entity's settings name
    // (parent.+0x28). Return the Nth match. Mirrors spawner_probe's
    // expr_listSpawners filter exactly so we tolerate the same edge
    // cases (trailing nulls, padding, name in either field). Stale
    // captures from prior chapter loads are skipped via try/catch.
    function findHourglassSpawner() {
        var key = HOURGLASS_PARENT_NAME.toLowerCase();
        var idx = -1;
        for (var i = 0; i < Hourglass._spawners.length; i++) {
            var sp = Hourglass._spawners[i];
            try {
                var flags = sp.add(SPAWNER_FLAGS_OFF).readU8();
                if ((flags & SPAWNER_CONSUMED_BIT) !== 0) continue;

                var ownName = null;
                try {
                    var ownSettings = sp.add(0x10).readPointer();
                    if (ownSettings && !ownSettings.isNull() &&
                        ownSettings.toString() !== '0xffffffffffffffff') {
                        ownName = readSettingsName(ownSettings);
                    }
                } catch (e) {}

                var parentName = null;
                try {
                    var parent = sp.add(SPAWNER_PARENT_OFF).readPointer();
                    if (parent && !parent.isNull() &&
                        parent.toString() !== '0xffffffffffffffff') {
                        var pSettings = parent.add(ENTITY_SETTINGS_OFF).readPointer();
                        if (pSettings && !pSettings.isNull() &&
                            pSettings.toString() !== '0xffffffffffffffff') {
                            parentName = readSettingsName(pSettings);
                        }
                    }
                } catch (e) {}

                var hay = ((ownName || "") + " " + (parentName || "")).toLowerCase();
                if (hay.indexOf(key) < 0) continue;

                idx++;
                if (idx === HOURGLASS_REWARD_INDEX) return sp;
            } catch (e) {}
        }
        return null;
    }

    /*
     * ----------------------------------------------------------------
     * Hourglass.spawnItem(opts?: { intervalMs?: number, verbose?: boolean }): NativePointer | null
     *
     * Fire the chapter hourglass's reward-item spawner. The drop is the
     * early-boss-reward item — normally only granted upon defeating
     * the chapter boss before the hourglass timer expires.
     *
     * Without opts: fires ONCE silently and returns the spawner pointer.
     * With opts.intervalMs: fires every intervalMs ms until
     *   spawnItemStop() is called; returns null. Calling spawnItem
     *   with intervalMs again replaces the active timer.
     * With opts.verbose: logs the selection + fire (quiet by default
     *   to keep interval mode from flooding the REPL).
     *
     * Prerequisites:
     *   loadPower("Hourglass") MUST run before the chapter loads, so
     *   the spawner-ctor hook is already attached when chapter setup
     *   ctors the hourglass spawner. Loaded mid-chapter, the hook
     *   misses the ctor; reload the chapter once to recapture.
     *
     * Usage:
     *   loadPower("Hourglass")
     *   <load chapter, walk out of safe area>
     *   Hourglass.spawnItem()                            // quiet one-shot
     *   Hourglass.spawnItem({ intervalMs: 2000 })        // quiet interval
     *   Hourglass.spawnItem({ verbose: true })           // log fire
     *   Hourglass.spawnItemStop()                        // stop interval
     *
     * Result:
     *   Each fire produces an item drop at the hourglass's natural
     *   position. Pre-active hourglass: one fire per state transition.
     *   Active hourglass: re-fires indefinitely.
     *
     * Caveats:
     *   - If a quiet fire silently no-ops, retry with verbose:true.
     *     Typical fix: reload the chapter once with this power loaded.
     *   - Fast intervals (< 250 ms) may overrun the spawn allocator.
     *     Default ≥ 1000 ms is safe.
     *   - Heap pointers in the capture set go stale on chapter reload;
     *     the find logic skips entries whose parent dereference fails.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   File-scope Interceptor on FUN_1402d0ee0 (RVA 0x2d0ee0,
     *   oCEntityCpntEntitySpawner ctor) captures every spawner pointer
     *   ctor'd during chapter setup. spawnItem walks the capture list
     *   skipping entries with bit 3 of +0x64 set (consumed flag), reads
     *   each spawner's parent (+0x08), the parent's oCEntitySettings
     *   (+0x28), and the settings name (+0x08 char*, +0x10 u32 length).
     *   Picks the Nth unfired match for parent name "NoModel+2Cpnt"
     *   (sub-index 0 = early-boss-reward; sub-index 1 currently
     *   unmapped). Calls FUN_1406f62b0(spawner) (RVA 0x6f62b0) — the
     *   broadcast worker the engine itself uses internally during
     *   natural activation. No parent-warp: the item drops at the
     *   spawner's natural bound transform (the hourglass's location).
     *   See rw/findings/entity-spawner-mechanism.md §"Live work —
     *   2026-05-07 follow-up" for rationale and ruled-out alternatives.
     */
    Hourglass.spawnItem = function (opts) {
        var intervalMs = (opts && typeof opts.intervalMs === 'number') ? opts.intervalMs : 0;
        var verbose    = !!(opts && opts.verbose);

        var fire = function () {
            if (!Hourglass._spawners.length) {
                if (verbose) console.log("[Hourglass.spawnItem] no captures — load before chapter and reload");
                return null;
            }
            var sp = findHourglassSpawner();
            if (!sp) {
                if (verbose) console.log("[Hourglass.spawnItem] no unfired \"" +
                                         HOURGLASS_PARENT_NAME + "\" sub-index " +
                                         HOURGLASS_REWARD_INDEX + " in captures");
                return null;
            }
            try {
                fireFn(sp);
                if (verbose) console.log("[Hourglass.spawnItem] fired " + sp);
                return sp;
            } catch (e) {
                if (verbose) console.log("[Hourglass.spawnItem] fire threw: " + e.message);
                return null;
            }
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
    console.log("[Hourglass]   spawnItem({ verbose: true })         — log selection + fire");
    console.log("[Hourglass]   spawnItemStop()                      — stop the interval timer");
})();

// Top-level alias for REPL convenience
var Hourglass = RW.Hourglass;
