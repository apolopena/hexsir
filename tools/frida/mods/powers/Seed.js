// Seed.js — force the chapter master seed at chapter load.
//
// Hooks apply_session_seed_to_scene_contexts (RVA 0x26af00) — the function
// that takes the master seed and distributes it to per-context subseed slots
// (MapSceneContext+0x80, EntitySceneContext+0x3b8, two globals at
// 0x141446a78 / 0x141446a98). When armed, overwrites the master at
// args[1] + 0x1c BEFORE the function reads it. All four downstream subseeds
// derive from our value, so the entire chapter (camps, locations, content,
// rewards, drops) becomes deterministic.
//
// SETUP-BOUND: the hook must be attached before chapter load. Load before
// triggering the chapter you want forced.
//
// Working flow:
//   loadPower("Seed")          // BEFORE chapter load — installs hook
//   Seed.set(1720768478)        // arm: override master to this value on next load
//   <reload chapter>            // engine calls our hook → master overridden
//   Seed.clear()                // disarm; future loads run unmodified
//   Seed.status()               // armed/disarmed + value
//
// Background: rw/findings/rng-behavior.md (per-event RNG model),
// apply_session_seed_to_scene_contexts plate comment in Ghidra.

(function () {
    var version = "0.1.0";
    if (typeof RW !== "object") {
        console.log("[Seed] FATAL: RW missing — load rw_lab.js first");
        return;
    }
    var rwMod = Process.findModuleByName("Ravenswatch.exe");
    if (!rwMod) { console.log("[Seed] FATAL: no Ravenswatch.exe"); return; }
    var IMG = rwMod.base;

    var APPLY_SESSION_SEED_RVA = 0x26af00;   // apply_session_seed_to_scene_contexts
    var MASTER_OFF             = 0x1c;       // u32 master seed at args[1] + 0x1c
    var U32_MAX                = 0xffffffff;

    if (!RW.Seed) RW.Seed = {};
    var Seed = RW.Seed;

    // Re-load safe state. Preserve across re-eval.
    Seed._hook  = Seed._hook  || null;
    Seed._armed = Seed._armed || false;
    Seed._value = (typeof Seed._value === 'number') ? Seed._value : null;

    // Detach prior hook on re-eval to avoid stacking.
    if (Seed._hook) {
        try { Seed._hook.detach(); } catch (e) {}
        Seed._hook = null;
    }

    Seed._hook = Interceptor.attach(IMG.add(APPLY_SESSION_SEED_RVA), {
        onEnter: function (args) {
            if (!Seed._armed) return;
            try {
                var payload = ptr(args[1]);
                var prev = payload.add(MASTER_OFF).readU32();
                payload.add(MASTER_OFF).writeU32(Seed._value >>> 0);
                console.log("[Seed] forced master 0x" + prev.toString(16) +
                            " -> 0x" + (Seed._value >>> 0).toString(16) +
                            " (" + (Seed._value >>> 0) + ")");
            } catch (e) {
                console.log("[Seed] hook write FAILED: " + e.message);
            }
        },
    });

    /*
     * ----------------------------------------------------------------
     * Seed.set(value: number): void
     *
     * Arm the hook to overwrite the chapter master seed on the next
     * (and every subsequent) chapter load. Accepts decimal or hex
     * (0x6690d7de). Truncated to u32.
     *
     * Result:
     *   Logs "[Seed] armed = 0x... (decimal)". Stays armed across
     *   chapter loads until clear() is called or Frida exits.
     *
     * Caveat: SETUP-BOUND. Must call set() before the chapter load
     * you want forced. If you call set() mid-chapter, it takes effect
     * on the next chapter-load event, not immediately.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Stores value on Seed._value, sets Seed._armed = true. The hook
     *   on apply_session_seed_to_scene_contexts onEnter writes
     *   args[1] + 0x1c with this value BEFORE the function reads it.
     *   The function then derives all four per-context subseeds from
     *   our value via a single PCG step, giving full determinism
     *   downstream (camps, locations, rewards, drops, talent rolls).
     */
    Seed.set = function (value) {
        if (typeof value !== 'number' || !isFinite(value) || Math.floor(value) !== value) {
            console.log("[Seed.set] usage: Seed.set(uint32)  e.g. Seed.set(1720768478) or Seed.set(0x6690d7de)");
            return;
        }
        var v = value >>> 0;   // truncate to u32
        Seed._value = v;
        Seed._armed = true;
        console.log("[Seed] armed = 0x" + v.toString(16) + " (" + v + ")");
    };

    /*
     * ----------------------------------------------------------------
     * Seed.clear(): void
     *
     * Disarm. Subsequent chapter loads run with the engine's natural
     * seed. Forgets the previously-set value — call set() again to
     * re-arm.
     *
     * Result: logs "[Seed] cleared".
     * ----------------------------------------------------------------
     */
    Seed.clear = function () {
        Seed._armed = false;
        Seed._value = null;
        console.log("[Seed] cleared");
    };

    /*
     * ----------------------------------------------------------------
     * Seed.status(): { armed: boolean, value: number | null }
     *
     * Snapshot of current state. Logs a one-liner and returns the
     * object for programmatic use.
     * ----------------------------------------------------------------
     */
    Seed.status = function () {
        if (Seed._armed) {
            console.log("[Seed.status] armed = 0x" + Seed._value.toString(16) +
                        " (" + Seed._value + ")");
        } else {
            console.log("[Seed.status] not armed");
        }
        return { armed: Seed._armed, value: Seed._value };
    };

    RW.registerMod("power:Seed", version);
    console.log("[Seed] " + version + " loaded — load BEFORE chapter for the force to take effect");
    console.log("[Seed]   set(value)   — arm: override master on next chapter load");
    console.log("[Seed]   clear()      — disarm");
    console.log("[Seed]   status()     — { armed, value }");
})();

// Top-level alias for REPL convenience.
var Seed = RW.Seed;
