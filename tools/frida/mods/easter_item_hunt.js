// easter_item_hunt.js — interval-fire the chapter hourglass's reward and
// scatter each spawned item to a random point near the player. Stops
// automatically after N items have been placed.
//
// Composes:
//   - RW.Hourglass     — fires the hourglass reward (auto-loaded on start)
//   - RW.Transporter   — relocation primitive shared with this mod
//
// API:
//   loadMod("easter_item_hunt")
//   EasterItemHunt.start(100)                                  // 100 items, defaults
//   EasterItemHunt.start(100, { intervalMs: 1500, radius: 120 })
//   EasterItemHunt.pause() / EasterItemHunt.resume()
//   EasterItemHunt.log(false)                                  // silence per-item log
//   EasterItemHunt.log(true)                                   // re-enable (default ON)
//
// Locating the dropped item:
// Each Hourglass.spawnItem call goes through the broadcast-worker
// spawn dispatcher (FUN_1406f62b0 → vtable[28] FUN_140713520 →
// FUN_140714350). That path appends the freshly-constructed child
// entity ptr to a vector at spawner.+0x210 (count u32 at +0x218).
// After spawnItem returns we read the back of that array and treat
// it as the most-recent spawn. The +0x160 cached-output field
// documented in rw/findings/entity-spawner-mechanism.md is only
// populated by the spawnIfNotCached path, not the broadcast worker.
// PENDING LIVE VERIFICATION 2026-05-07: identified via Ghidra static
// dig (FUN_140714350 plate comment); not yet live-tested.
//
// Depends on:
//   - rw_lab.js (RW.* hub; RW.Player.loc for scatter origin)
//   - mods/powers/Hourglass.js (auto-loaded)
//   - mods/powers/Transporter.js (auto-loaded — its public API is
//     name-based, but RW.Entity.find can't resolve a fresh spawn
//     before it streams; we call the same vtable[10] setPosition
//     primitive Transporter uses internally, on the captured ptr)

(function () {
    var version = "0.8.0";
    if (typeof RW !== "object") {
        console.log("[EasterItemHunt] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    var SPAWNER_SPAWNED_ARR_OFF   = 0x210;   // spawner.+0x210 = qword* — array of spawned-child entity ptrs (broadcast-worker path)
    var SPAWNER_SPAWNED_COUNT_OFF = 0x218;   // spawner.+0x218 = u32  — count of entries in the +0x210 array
    var ENTITY_SETPOS_VT_OFF      = 0x50;    // oCEntity vtable slot 10 = setPosition (RVA 0x6ca7f0)
    var MOVE_DELAY_DEFAULT_MS     = 200;     // delay between spawn fire and first setPosition; short so we move while the engine is still in transform-driving mode (per the cauldron pattern)
    var MAINTAIN_TICK_MS          = 100;     // master tick re-issuing setPosition on every scattered item to fight per-frame engine snap-back (Transporter uses 500ms; items snap faster, so tighter)

    if (!RW.EasterItemHunt) RW.EasterItemHunt = {};
    var EasterItemHunt = RW.EasterItemHunt;

    EasterItemHunt._timer           = EasterItemHunt._timer || null;
    EasterItemHunt._tickTimer       = EasterItemHunt._tickTimer || null;
    EasterItemHunt._scatteredItems  = EasterItemHunt._scatteredItems || [];   // [{ entity, x, y, z }] — re-issued every MAINTAIN_TICK_MS to fight per-frame engine snap-back
    EasterItemHunt._remaining       = (typeof EasterItemHunt._remaining === 'number')   ? EasterItemHunt._remaining   : 0;
    EasterItemHunt._paused          = (typeof EasterItemHunt._paused === 'boolean')     ? EasterItemHunt._paused      : false;
    EasterItemHunt._radius          = (typeof EasterItemHunt._radius === 'number')      ? EasterItemHunt._radius      : 100;
    EasterItemHunt._logging         = (typeof EasterItemHunt._logging === 'boolean')    ? EasterItemHunt._logging     : true;
    EasterItemHunt._moveDelayMs     = (typeof EasterItemHunt._moveDelayMs === 'number') ? EasterItemHunt._moveDelayMs : MOVE_DELAY_DEFAULT_MS;

    // Re-load safety: clear any prior intervals before re-arming so an
    // edit-and-loadMod cycle doesn't leave orphaned ticks running.
    if (EasterItemHunt._timer) {
        try { clearInterval(EasterItemHunt._timer); } catch (e) {}
        EasterItemHunt._timer = null;
    }
    if (EasterItemHunt._tickTimer) {
        try { clearInterval(EasterItemHunt._tickTimer); } catch (e) {}
        EasterItemHunt._tickTimer = null;
    }

    // IIFE-time dep load. Hourglass has a chapter-timing constraint
    // (its ctor hook must arm before chapter setup), so loading it
    // here on `loadMod("easter_item_hunt")` means the user only has
    // to load THIS file before the chapter — not Hourglass separately.
    // Transporter has no timing constraint; loaded here for symmetry
    // / availability if we extend it later, but failure is non-fatal.
    try {
        if (!RW.Hourglass)   RW.loadPower("Hourglass");
        if (!RW.Transporter) RW.loadPower("Transporter");
    } catch (e) {
        console.log("[EasterItemHunt] dep load at IIFE time failed: " + e.message);
    }

    function preflight() {
        if (!RW.Player || typeof RW.Player.refresh !== 'function') {
            console.log("[EasterItemHunt] FATAL: RW.Player missing (rw_lab.js not loaded?)");
            return false;
        }
        if (!RW.Hourglass || typeof RW.Hourglass.spawnItem !== 'function') {
            console.log("[EasterItemHunt] FATAL: Hourglass not loaded — IIFE-time auto-load failed");
            return false;
        }
        if (!RW.Player.loc) {
            RW.Player.refresh();
            console.log("[EasterItemHunt] RW.Player.loc not captured — play one frame in-game then call start() again");
            return false;
        }
        return true;
    }

    function randomScatterFromPlayer(radius) {
        var p = RW.Player.loc;
        if (!p) return null;
        var angle = Math.random() * Math.PI * 2;
        var dist  = Math.random() * radius;
        return {
            x: p.x + Math.cos(angle) * dist,
            y: p.y,
            z: p.z + Math.sin(angle) * dist,
        };
    }

    // Same vtable[10] setPosition primitive Transporter uses internally,
    // called directly on the spawn target's ptr because Transporter's
    // public API is name-based and RW.Entity.find can't resolve a fresh
    // spawn that hasn't streamed into the encyclopedia yet.
    function setEntityPosition(entity, x, y, z) {
        var vt = entity.readPointer();
        var fn = new NativeFunction(vt.add(ENTITY_SETPOS_VT_OFF).readPointer(),
                                    'pointer', ['pointer', 'pointer']);
        var buf = Memory.alloc(12);
        buf.writeFloat(x);
        buf.add(4).writeFloat(y);
        buf.add(8).writeFloat(z);
        fn(entity, buf);
    }

    // Fire Hourglass and move the dropped item. The fire counts toward
    // the hunt limit regardless of whether we can move the item — the
    // user wanted "stops after N items"; that's measured by spawn
    // count, not move-success count.
    //
    // Locating the spawn: the broadcast-worker fire path appends each
    // spawned child to spawner.+0x210 (qword array, count u32 at
    // +0x218). We read the LAST entry — the most-recent push — and
    // setPosition it after a short delay so async asset streaming has
    // a chance to finish constructing it before the relocate.
    // Master tick: re-issue setPosition on every scattered item every
    // MAINTAIN_TICK_MS. Same pattern Transporter.warpEntity uses to
    // fight the engine's per-frame transform reset (see Transporter.js
    // MECHANISM block); items snap back faster than cauldrons so the
    // tick is tighter (100ms vs 500ms). One master interval handles
    // arbitrary N items — cheaper than per-item intervals.
    function startTickIfNeeded() {
        if (EasterItemHunt._tickTimer) return;
        EasterItemHunt._tickTimer = setInterval(function () {
            var items = EasterItemHunt._scatteredItems;
            for (var i = 0; i < items.length; i++) {
                try {
                    setEntityPosition(items[i].entity, items[i].x, items[i].y, items[i].z);
                } catch (e) { /* entity freed / pickup / despawn — silently skip */ }
            }
        }, MAINTAIN_TICK_MS);
    }

    function spawnAndScatter(radius) {
        var sp = RW.Hourglass.spawnItem();
        if (!sp) {
            if (EasterItemHunt._logging) console.log("[EasterItemHunt] spawnItem returned null");
            return false;
        }

        // The spawn fired — count it regardless of move outcome.
        var child = ptr(0);
        try {
            var count = sp.add(SPAWNER_SPAWNED_COUNT_OFF).readU32();
            if (count > 0) {
                var arr = sp.add(SPAWNER_SPAWNED_ARR_OFF).readPointer();
                if (arr && !arr.isNull()) {
                    child = arr.add((count - 1) * 8).readPointer();
                }
            }
        } catch (e) {}

        if (!child || child.isNull()) {
            if (EasterItemHunt._logging) {
                console.log("[EasterItemHunt] fired sp=" + sp + " — empty +0x210 array (item at hourglass)");
            }
            return true;
        }

        var pos = randomScatterFromPlayer(radius);
        if (!pos) {
            if (EasterItemHunt._logging) {
                console.log("[EasterItemHunt] fired sp=" + sp + " — RW.Player.loc not captured, skipping move");
            }
            return true;
        }

        var moveTarget = child;
        var movePos    = pos;
        RW.after(EasterItemHunt._moveDelayMs / 1000, function () {
            try {
                setEntityPosition(moveTarget, movePos.x, movePos.y, movePos.z);
                EasterItemHunt._scatteredItems.push({
                    entity: moveTarget, x: movePos.x, y: movePos.y, z: movePos.z,
                });
                startTickIfNeeded();
                if (EasterItemHunt._logging) {
                    console.log("[EasterItemHunt] moved " + moveTarget + " -> (" +
                                movePos.x.toFixed(1) + "," + movePos.y.toFixed(1) + "," +
                                movePos.z.toFixed(1) + ") (held by " + MAINTAIN_TICK_MS + "ms tick)");
                }
            } catch (e) {
                if (EasterItemHunt._logging) console.log("[EasterItemHunt] setPosition failed: " + e.message);
            }
        });
        return true;
    }

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.start(count: number, opts?: { intervalMs?: number, radius?: number, moveDelayMs?: number }): void
     *
     * Begin an item hunt: every intervalMs ms, fire the chapter
     * hourglass's reward spawner and (after moveDelayMs) move the
     * dropped item to a random point within `radius` units of the
     * player's current location (XZ random angle/dist; Y matched to
     * player). Stops automatically after `count` items have been
     * placed.
     *
     * Auto-loads Hourglass + Transporter on first call (idempotent).
     *
     * opts.intervalMs:   ms between spawns (default 1500).
     * opts.radius:       scatter radius around player (default 100).
     * opts.moveDelayMs:  ms after spawn fire before the FIRST
     *                    setPosition call (default 200). Short so we
     *                    move while the engine is still in
     *                    transform-driving mode. After that initial
     *                    move, a master tick re-issues setPosition
     *                    every MAINTAIN_TICK_MS to fight per-frame
     *                    snap-back (cauldron pattern). The tick runs
     *                    until clearMoves() is called.
     *
     * Result: starts an interval timer; logs progress per item if
     *   logging is on; stops automatically once `count` is reached.
     *   Calling start() again resets any in-progress hunt.
     *
     * Caveats:
     *   - Requires Hourglass prerequisites: power loaded before chapter,
     *     chapter loaded so the ctor hook captured the hourglass.
     *   - Requires RW.Player.loc captured. If not, refresh() is armed
     *     and the user is asked to play one frame and re-call start().
     *   - The maintain-tick keeps running for the lifetime of the
     *     Frida session unless clearMoves() is called. Every spawn
     *     ever scattered keeps getting re-asserted, so a long hunt
     *     means N parallel re-assertions per tick. Cheap (one master
     *     interval, one setPosition call per item per tick) but not
     *     free — tune MAINTAIN_TICK_MS up if it's noticeable.
     *   - Items will fight pickup attempts while the tick holds them
     *     in place. Call clearMoves() before trying to pick scattered
     *     items up.
     *   - If items don't move at all (no snap-back, just stay at the
     *     hourglass), the +0x210 array isn't returning the visible
     *     loot entity. See the file header for the locator mechanism.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.start = function (count, opts) {
        if (typeof count !== 'number' || count <= 0) {
            console.log("[EasterItemHunt.start] usage: start(count, { intervalMs?, radius? })");
            return;
        }
        if (!preflight()) return;

        var intervalMs   = (opts && typeof opts.intervalMs === 'number')   ? opts.intervalMs   : 1500;
        var radius       = (opts && typeof opts.radius === 'number')       ? opts.radius       : 100;
        var moveDelayMs  = (opts && typeof opts.moveDelayMs === 'number')  ? opts.moveDelayMs  : MOVE_DELAY_DEFAULT_MS;

        if (EasterItemHunt._timer) {
            try { clearInterval(EasterItemHunt._timer); } catch (e) {}
            EasterItemHunt._timer = null;
        }
        EasterItemHunt._remaining   = count;
        EasterItemHunt._paused      = false;
        EasterItemHunt._radius      = radius;
        EasterItemHunt._moveDelayMs = moveDelayMs;

        console.log("[EasterItemHunt.start] " + count + " items, intervalMs=" + intervalMs +
                    ", radius=" + radius + ", moveDelayMs=" + moveDelayMs);

        EasterItemHunt._timer = setInterval(function () {
            if (EasterItemHunt._paused) return;
            if (EasterItemHunt._remaining <= 0) {
                try { clearInterval(EasterItemHunt._timer); } catch (e) {}
                EasterItemHunt._timer = null;
                console.log("[EasterItemHunt] hunt complete");
                return;
            }
            try {
                if (spawnAndScatter(EasterItemHunt._radius)) {
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
     * silence the "[EasterItemHunt] item placed @ (x,y,z)" lines and
     * the per-tick failure messages.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.log = function (on) {
        EasterItemHunt._logging = !!on;
        console.log("[EasterItemHunt.log] per-item logging " + (EasterItemHunt._logging ? "ON" : "OFF"));
    };

    /*
     * ----------------------------------------------------------------
     * EasterItemHunt.clearMoves(): void
     *
     * Stop the maintain-tick that re-asserts each scattered item's
     * position every MAINTAIN_TICK_MS. Items will then resume
     * whatever the engine wants them to do (typically: snap back to
     * their natural drop transform on the next frame).
     *
     * Use to abort an in-progress hold without aborting the spawn
     * loop, or to release items so they can be picked up cleanly.
     * ----------------------------------------------------------------
     */
    EasterItemHunt.clearMoves = function () {
        if (EasterItemHunt._tickTimer) {
            try { clearInterval(EasterItemHunt._tickTimer); } catch (e) {}
            EasterItemHunt._tickTimer = null;
        }
        var n = EasterItemHunt._scatteredItems.length;
        EasterItemHunt._scatteredItems = [];
        console.log("[EasterItemHunt.clearMoves] released " + n + " items");
    };

    RW.registerMod("easter_item_hunt", version);
    console.log("[EasterItemHunt] " + version + " loaded.");
    console.log("[EasterItemHunt]   start(count, opts?)  — opts: intervalMs (1500), radius (100), moveDelayMs (200)");
    console.log("[EasterItemHunt]   pause() / resume()");
    console.log("[EasterItemHunt]   clearMoves()         — stop the maintain-tick (release scattered items)");
    console.log("[EasterItemHunt]   log(on: bool)        — toggle per-item placement log (default ON)");
    console.log("[EasterItemHunt]   auto-loads Hourglass + Transporter on start()");
})();

// Top-level alias for REPL convenience
var EasterItemHunt = RW.EasterItemHunt;
