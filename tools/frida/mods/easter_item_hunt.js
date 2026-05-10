// easter_item_hunt.js — interval-fire the chapter hourglass's reward
// spawner. Stops automatically after N items have been placed.
//
// Composes:
//   - RW.Hourglass     — fires the hourglass reward (auto-loaded on start)
//
// API:
//   loadMod("easter_item_hunt")
//   EasterItemHunt.start(100)                          // 100 items, default interval
//   EasterItemHunt.start(100, { intervalMs: 1500 })
//   EasterItemHunt.pause() / EasterItemHunt.resume()
//   EasterItemHunt.log(false)                          // silence per-item log
//   EasterItemHunt.log(true)                           // re-enable (default ON)
//
// Note: items land wherever the hourglass spawns them. Earlier versions
// of this mod scattered each item to a random point near the player via
// setPosition + a 100ms maintain-tick, but the engine's per-frame
// transform reset on item entities made the scatter glitchy and the
// items snapped back together anyway. The relocation was removed in
// v0.9.0; if you want it back, see the v0.8.0 implementation in git.

(function () {
    var version = "0.10.0";
    if (typeof RW !== "object") {
        console.log("[EasterItemHunt] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    if (!RW.EasterItemHunt) RW.EasterItemHunt = {};
    var EasterItemHunt = RW.EasterItemHunt;

    EasterItemHunt._timer     = EasterItemHunt._timer || null;
    EasterItemHunt._remaining = (typeof EasterItemHunt._remaining === 'number') ? EasterItemHunt._remaining : 0;
    EasterItemHunt._paused    = (typeof EasterItemHunt._paused === 'boolean')   ? EasterItemHunt._paused    : false;
    EasterItemHunt._logging   = (typeof EasterItemHunt._logging === 'boolean')  ? EasterItemHunt._logging   : true;

    // Re-load safety: clear any prior interval before re-arming so an
    // edit-and-loadMod cycle doesn't leave an orphaned tick running.
    if (EasterItemHunt._timer) {
        try { clearInterval(EasterItemHunt._timer); } catch (e) {}
        EasterItemHunt._timer = null;
    }

    // IIFE-time dep load. Hourglass has a chapter-timing constraint
    // (its ctor hook must arm before chapter setup), so loading it here
    // on `loadMod("easter_item_hunt")` means the user only has to load
    // THIS file before the chapter — not Hourglass separately.
    try {
        if (!RW.Hourglass) RW.loadPower("Hourglass");
    } catch (e) {
        console.log("[EasterItemHunt] dep load at IIFE time failed: " + e.message);
    }

    function preflight() {
        if (!RW.Hourglass || typeof RW.Hourglass.spawnItem !== 'function') {
            console.log("[EasterItemHunt] FATAL: Hourglass not loaded — IIFE-time auto-load failed");
            return false;
        }
        // Guarded refresh: only arm the player-capture hook if we don't already
        // have an entity ptr. Blind refresh clears RW.Player.entity to null.
        // We don't actively use player loc anymore, but past sessions had this
        // call in the preflight; restoring as a safety net.
        if (RW.Player && typeof RW.Player.refresh === 'function' && !RW.Player.entity) {
            try { RW.Player.refresh(); } catch (e) {}
        }
        return true;
    }

    function spawnOne() {
        // Propagate logging as verbose so Hourglass surfaces *why* a fire
        // failed (no captures vs. all consumed) instead of us just seeing null.
        var sp = RW.Hourglass.spawnItem({ verbose: EasterItemHunt._logging });
        if (!sp) return false;
        return true;
    }

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.start(count: number, opts?: { intervalMs?: number }): void
     *
     * Begin an item hunt: every intervalMs ms, fire the chapter
     * hourglass's reward spawner. Items land at the hourglass's natural
     * drop position. Stops automatically after `count` items have been
     * spawned.
     *
     * Auto-loads Hourglass on first call (idempotent).
     *
     * opts.intervalMs: ms between spawns (default 1500).
     *
     * Result: starts an interval timer; logs progress per item if
     *   logging is on; stops automatically once `count` is reached.
     *   Calling start() again resets any in-progress hunt.
     *
     * Caveats:
     *   - Requires Hourglass prerequisites: power loaded before chapter,
     *     chapter loaded so the ctor hook captured the hourglass.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.start = function (count, opts) {
        if (typeof count !== 'number' || count <= 0) {
            console.log("[EasterItemHunt.start] usage: start(count, { intervalMs? })");
            return;
        }
        if (!preflight()) return;

        var intervalMs = (opts && typeof opts.intervalMs === 'number') ? opts.intervalMs : 1500;

        if (EasterItemHunt._timer) {
            try { clearInterval(EasterItemHunt._timer); } catch (e) {}
            EasterItemHunt._timer = null;
        }
        EasterItemHunt._remaining = count;
        EasterItemHunt._paused    = false;

        console.log("[EasterItemHunt.start] " + count + " items, intervalMs=" + intervalMs);

        EasterItemHunt._timer = setInterval(function () {
            if (EasterItemHunt._paused) return;
            if (EasterItemHunt._remaining <= 0) {
                try { clearInterval(EasterItemHunt._timer); } catch (e) {}
                EasterItemHunt._timer = null;
                console.log("[EasterItemHunt] hunt complete");
                return;
            }
            try {
                if (spawnOne()) {
                    EasterItemHunt._remaining--;
                }
            } catch (e) {
                console.log("[EasterItemHunt] tick threw: " + e.message + " — stopping");
                try { clearInterval(EasterItemHunt._timer); } catch (er) {}
                EasterItemHunt._timer = null;
            }
        }, intervalMs);
    };

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.stop(): void
     *
     * Cancel an in-progress hunt. Clears the interval timer and
     * resets remaining count to 0. No-op if no hunt is active.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.stop = function () {
        if (!EasterItemHunt._timer) {
            console.log("[EasterItemHunt.stop] no active hunt");
            return;
        }
        try { clearInterval(EasterItemHunt._timer); } catch (e) {}
        EasterItemHunt._timer = null;
        var left = EasterItemHunt._remaining;
        EasterItemHunt._remaining = 0;
        EasterItemHunt._paused = false;
        console.log("[EasterItemHunt.stop] stopped (" + left + " items unfired)");
    };

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.pause(): void
     *
     * Pause an in-progress hunt. The interval timer keeps running but
     * each tick is a no-op until resume() is called. Remaining count
     * is preserved.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.pause = function () {
        if (!EasterItemHunt._timer) {
            console.log("[EasterItemHunt.pause] no active hunt");
            return;
        }
        EasterItemHunt._paused = true;
        console.log("[EasterItemHunt.pause] paused (" + EasterItemHunt._remaining + " items remaining)");
    };

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.resume(): void
     *
     * Resume a paused hunt.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.resume = function () {
        if (!EasterItemHunt._timer) {
            console.log("[EasterItemHunt.resume] no active hunt — call start(count) first");
            return;
        }
        if (!EasterItemHunt._paused) {
            console.log("[EasterItemHunt.resume] not paused");
            return;
        }
        EasterItemHunt._paused = false;
        console.log("[EasterItemHunt.resume] resumed (" + EasterItemHunt._remaining + " items remaining)");
    };

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.log(on: boolean): void
     *
     * Toggle per-item placement logging. ON by default — pass false to
     * silence the per-spawn log lines.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.log = function (on) {
        EasterItemHunt._logging = !!on;
        console.log("[EasterItemHunt.log] per-item logging " + (EasterItemHunt._logging ? "ON" : "OFF"));
    };

    RW.registerMod("easter_item_hunt", version);
    console.log("[EasterItemHunt] " + version + " loaded.");
    console.log("[EasterItemHunt]   ⚠  LOAD THIS MOD BEFORE THE CHAPTER LOADS.");
    console.log("[EasterItemHunt]      Hourglass arms a spawner-ctor hook at IIFE time;");
    console.log("[EasterItemHunt]      mid-chapter loads miss the ctor → spawnItem returns null.");
    console.log("[EasterItemHunt]   ⚠  WALK OUT OF THE STARTING SAFE AREA before start().");
    console.log("[EasterItemHunt]      Pre-active hourglass = one fire then consumed bit blocks re-fires.");
    console.log("[EasterItemHunt]      Active hourglass (player out of safe zone) re-fires indefinitely.");
    console.log("[EasterItemHunt]   start(count, opts?)  — opts: intervalMs (1500)");
    console.log("[EasterItemHunt]   stop()               — cancel in-progress hunt");
    console.log("[EasterItemHunt]   pause() / resume()");
    console.log("[EasterItemHunt]   log(on: bool)        — toggle per-item placement log (default ON)");
    console.log("[EasterItemHunt]   auto-loads Hourglass on start()");
})();

// Top-level alias for REPL convenience
var EasterItemHunt = RW.EasterItemHunt;
