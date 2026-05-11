// hero_move_probe.js — identify the per-tick caller of oCEntity::setPosition
// for the player.
//
// Mechanism: hooks oCEntity::setPosition (RVA 0x6ca7f0) with a filter on
// args[0] == RW.Player.entity. On every player-side fire, dumps the top
// frames of the call stack as RVAs (image-base relative). Compare hit
// counts and stack patterns between idle and movement to identify what
// drives the player's controller tick — and pin the function that issues
// the grounded-resolve write.
//
// Depends on:
//   - RW.Player (call RW.Player.refresh() and play one frame first)
//
// REPL surface (after loadMod("hero_move_probe")):
//   HeroMoveProbe.start({ depth?, cap? }): void
//   HeroMoveProbe.stop(): void
//   HeroMoveProbe.status(): void
//   HeroMoveProbe.reset(): void

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[hero_move_probe] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    var SET_POS_RVA   = 0x6ca7f0;
    var DEFAULT_DEPTH = 8;
    var DEFAULT_CAP   = 30;

    if (!RW.HeroMoveProbe) RW.HeroMoveProbe = {};
    var Probe = RW.HeroMoveProbe;

    if (Probe._hook) {
        try { Probe._hook.detach(); } catch (e) {}
        Probe._hook = null;
    }

    Probe._hits  = Probe._hits  || 0;
    Probe._depth = Probe._depth || DEFAULT_DEPTH;
    Probe._cap   = Probe._cap   || DEFAULT_CAP;

    function fmtRva(addr) {
        try {
            var off = addr.sub(imageBase);
            return "0x" + off.toString(16);
        } catch (e) { return String(addr); }
    }

    /*
     * ----------------------------------------------------------------
     * HeroMoveProbe.start(opts?: { depth?: number, cap?: number }): void
     *
     * Arm the setPosition hook with a player-only filter. Each hit logs
     * the top `depth` stack frames as image-base-relative RVAs. Stops
     * logging after `cap` hits to avoid REPL flood (use status() to see
     * the running count; reset() to re-arm).
     *
     * Defaults: depth=8, cap=30.
     *
     * Result: prints `[hero_move_probe] armed`, then per-hit stack
     * dumps as the player's setPosition fires.
     * Caveats: requires RW.Player.entity captured (refresh + one frame).
     * ----------------------------------------------------------------
     */
    Probe.start = function (opts) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[hero_move_probe] RW.Player not captured — RW.Player.refresh() and play one frame");
            return;
        }
        opts = opts || {};
        Probe._depth = (typeof opts.depth === 'number') ? opts.depth : DEFAULT_DEPTH;
        Probe._cap   = (typeof opts.cap   === 'number') ? opts.cap   : DEFAULT_CAP;
        Probe._hits  = 0;

        var player = RW.Player.entity;
        var addr = imageBase.add(SET_POS_RVA);

        Probe._hook = Interceptor.attach(addr, {
            onEnter: function (args) {
                if (!args[0].equals(player)) return;
                Probe._hits++;
                if (Probe._hits > Probe._cap) return;
                var bt;
                try { bt = Thread.backtrace(this.context, Backtracer.ACCURATE); }
                catch (e) { bt = []; }
                var n = Math.min(bt.length, Probe._depth);
                console.log("[hero_move_probe] #" + Probe._hits + " setPosition stack:");
                for (var i = 0; i < n; i++) {
                    console.log("  " + fmtRva(bt[i]));
                }
            }
        });
        console.log("[hero_move_probe] armed (depth=" + Probe._depth + " cap=" + Probe._cap + ")");
    };

    /*
     * ----------------------------------------------------------------
     * HeroMoveProbe.stop(): void
     *
     * Detach the hook. Hit count is preserved; call reset() to clear.
     * ----------------------------------------------------------------
     */
    Probe.stop = function () {
        if (Probe._hook) {
            try { Probe._hook.detach(); } catch (e) {}
            Probe._hook = null;
        }
        console.log("[hero_move_probe] stopped after " + Probe._hits + " hits");
    };

    /*
     * ----------------------------------------------------------------
     * HeroMoveProbe.status(): void
     *
     * Print current hit count and whether the hook is armed.
     * ----------------------------------------------------------------
     */
    Probe.status = function () {
        console.log("[hero_move_probe] armed=" + (Probe._hook !== null) +
                    " hits=" + Probe._hits + " cap=" + Probe._cap);
    };

    /*
     * ----------------------------------------------------------------
     * HeroMoveProbe.reset(): void
     *
     * Clear the hit counter without detaching. Useful between idle and
     * movement test phases.
     * ----------------------------------------------------------------
     */
    Probe.reset = function () {
        Probe._hits = 0;
        console.log("[hero_move_probe] hit counter reset");
    };

    RW.registerMod("mod:hero_move_probe", version);
    console.log("[hero_move_probe] " + version + " loaded — call HeroMoveProbe.start()");
})();

var HeroMoveProbe = RW.HeroMoveProbe;
