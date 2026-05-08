// cauldron_test.js — script the manual cauldron-spawn-capture protocol.
//
// Manual flow has 9+ REPL lines and three procedural pitfalls (skipping
// RW.Player.refresh, double-start wiping captures, forgetting to verify
// a cauldron exists). This mod reduces it to:
//
//   loadMod("cauldron_test")
//   CauldronTest.start()    // resolves prereqs, warps cauldron, instructs
//   <walk to cauldron, activate it, fight at least one wave>
//   CauldronTest.finish()   // clears warp, stops capture, analyzes
//
// Auto-loads its deps on start() (Transporter power, spawn_capture mod)
// the same way SmokeTest pre-flights — the user only has to load this
// one file.
//
// Depends on:
//   - RW.Player  (hub helper in rw_lab.js)
//   - RW.Entity  (hub helper in rw_lab.js)
//   - Transporter (power, auto-loaded)
//   - SpawnCapture (mod, auto-loaded)

(function () {
    var version = "0.1.0";
    if (typeof RW !== "object") {
        console.log("[CauldronTest] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    var DEFAULT_OFFSET = 3;

    if (!RW.CauldronTest) RW.CauldronTest = {};
    var CauldronTest = RW.CauldronTest;

    // Preserve run-state across reloads.
    CauldronTest._armed         = CauldronTest._armed         || false;
    CauldronTest._cauldronName  = CauldronTest._cauldronName  || null;

    function preflight() {
        if (!RW.Player || typeof RW.Player.refresh !== 'function') {
            console.log("[CauldronTest] FATAL: RW.Player missing (rw_lab.js not loaded?)");
            return false;
        }
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[CauldronTest] FATAL: RW.Entity missing (rw_lab.js not loaded?)");
            return false;
        }
        try {
            if (!RW.Transporter)  RW.loadPower("Transporter");
            if (!RW.SpawnCapture) RW.loadMod("spawn_capture");
        } catch (e) {
            console.log("[CauldronTest] dependency load failed: " + e.message);
            return false;
        }
        if (!RW.Transporter || typeof RW.Transporter.warpEntity !== 'function') {
            console.log("[CauldronTest] FATAL: Transporter did not load");
            return false;
        }
        if (!RW.SpawnCapture || typeof RW.SpawnCapture.start !== 'function') {
            console.log("[CauldronTest] FATAL: SpawnCapture did not load");
            return false;
        }
        return true;
    }

    /*
     * ----------------------------------------------------------------
     * CauldronTest.start(opts?: { offset?: number }): void
     *
     * Stage one of the cauldron-spawn-capture protocol. Auto-loads
     * Transporter and SpawnCapture, verifies the player is captured
     * and a cauldron exists in this chapter, arms SpawnCapture, then
     * warps the cauldron next to the player on +X.
     *
     * opts.offset: distance in +X from the player to drop the cauldron
     *   (default 3). Use a smaller value if the chapter has a wall
     *   close to the player.
     *
     * Usage:
     *   CauldronTest.start()
     *   <walk to cauldron, activate, fight at least one wave>
     *   CauldronTest.finish()
     *
     * Result:
     *   On success: cauldron visibly relocates, SpawnCapture is armed,
     *   REPL prints next-step instructions, sets _armed = true.
     *   On any failure (no player, no cauldron, missing deps): prints
     *   a clear remediation message and bails — no partial state is
     *   left around (SpawnCapture is not armed, cauldron is not warped).
     *
     * Caveats:
     *   - Calling start() again before finish() is refused — would
     *     wipe prior captures. Run finish() first.
     *   - If RW.Player.entity isn't captured yet, calls
     *     RW.Player.refresh() and asks you to nudge in-game then
     *     re-run start().
     *   - Cauldron presence in a chapter is procgen. If no cauldron
     *     is present, prints "reload the chapter" and bails.
     *   - The warp tick keeps the cauldron pinned at the destination
     *     until finish() (or any Transporter.clear()) — its position
     *     stays where finish() leaves it; positions are not restored.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sequence: preflight (auto-load deps) → check RW.Player.loc
     *   (refresh + bail if null) → RW.Entity.find("cauldron") via the
     *   encyclopedia walker → SpawnCapture.start() (oCEntity ctor hook
     *   at RVA 0x6c96f0) → Transporter.warpEntity("cauldron",
     *   p.x+offset, p.y, p.z) (vtable[+0x50] setPosition on a 500ms
     *   tick) → set _armed.
     */
    CauldronTest.start = function (opts) {
        if (CauldronTest._armed) {
            console.log("[CauldronTest] already armed — call finish() before starting again");
            return;
        }

        // Cauldron-presence gate FIRST, before paying for any dep loading
        // or player capture. Only RW.Entity is required for the scan.
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[CauldronTest] FATAL: RW.Entity missing — load rw_lab.js first");
            return;
        }
        var hit = RW.Entity.find("cauldron");
        if (hit === undefined) {
            console.log("[CauldronTest] scene_manager not captured yet — play one frame, then call start() again");
            return;
        }
        if (!hit) {
            console.log("[CauldronTest] no cauldron in this chapter — reload the chapter (procgen) and try again");
            return;
        }

        // Cauldron exists. Load deps + resolve player so we can warp it in.
        if (!preflight()) return;

        var offset = (opts && typeof opts.offset === 'number') ? opts.offset : DEFAULT_OFFSET;
        var p = RW.Player.loc;
        if (!p) {
            RW.Player.refresh();
            console.log("[CauldronTest] player not captured — nudge in-game one frame, then call start() again");
            return;
        }

        console.log("[CauldronTest] player @ (" + p.x.toFixed(1) + "," + p.y.toFixed(1) + "," + p.z.toFixed(1) + ")");
        console.log("[CauldronTest] cauldron found: " + hit.name);

        RW.SpawnCapture.start();
        RW.Transporter.warpEntity("cauldron", p.x + offset, p.y, p.z);
        CauldronTest._armed        = true;
        CauldronTest._cauldronName = hit.name;

        console.log("[CauldronTest] armed. Walk to the cauldron, activate it, fight at least one wave,");
        console.log("[CauldronTest] then call CauldronTest.finish() to stop capture and analyze.");
    };

    /*
     * ----------------------------------------------------------------
     * CauldronTest.finish(): void
     *
     * Stage two: cancel the cauldron warp tick, stop SpawnCapture,
     * and run analyze() filtered by EnemyController. Clears _armed
     * so a fresh start() can run.
     *
     * Result: prints SpawnCapture.analyze output (templates grouped
     * by initArg, filtered to those whose first entity carries an
     * oCDtEntityCpntEnemyController). The cauldron stays wherever it
     * is — Transporter.clear() does not restore positions.
     *
     * Caveats:
     *   - No-op if not armed.
     *   - Captures from before the cauldron activation are still in
     *     the buffer; ambient entities may show alongside spawn waves.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Transporter.clear() (cancels 500ms tick + any roundtrip
     *   timers) → SpawnCapture.stop() (detaches oCEntity ctor hook) →
     *   SpawnCapture.analyze({ requireComponent: "EnemyController" })
     *   (groups by initArg, walks component hashmap on first entity,
     *   filters by RTTI substring).
     */
    CauldronTest.finish = function () {
        if (!CauldronTest._armed) {
            console.log("[CauldronTest] not armed — call start() first");
            return;
        }
        if (!preflight()) return;

        RW.Transporter.clear();
        RW.SpawnCapture.stop();
        RW.SpawnCapture.analyze({ requireComponent: "EnemyController" });
        CauldronTest._armed        = false;
        CauldronTest._cauldronName = null;
    };

    RW.registerMod("cauldron_test", version);
    console.log("[CauldronTest] " + version + " loaded.");
    console.log("[CauldronTest]   start(opts?)  finish()");
    console.log("[CauldronTest]   auto-loads Transporter + spawn_capture on start()");
})();

// Top-level alias for REPL convenience
var CauldronTest = RW.CauldronTest;
