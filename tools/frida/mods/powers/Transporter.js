// Transporter.js — warp entities or the player to specified world coords,
// with optional auto-restore after a roundtrip.
//
// Mechanism: the placement primitive is oCEntity::setPosition at vtable
// slot +0x50 (RVA 0x6ca7f0) — writes the entity's position field at
// +0x324 and broadcasts to subscribers (renderer, camera, minimap).
// For arbitrary entities the engine resets the transform per frame, so
// warpEntity re-issues setPosition on a 500ms tick interval. The player
// has its own movement controller that respects a single setPosition
// without ticking, so warpPlayer is one-shot.
//
// Caveat — invisible-anchor entities:
//   Some entries in the encyclopedia (e.g. "[Entity spawner] NoModel",
//   "[Entity spawner] Enemy Camp") are spawn-anchor entities with no
//   visible model attached. warpEntity will write their position field
//   silently — nothing visible moves. To visit those anchor positions,
//   warp the player there with warpPlayer instead.
//
// Caveat — game-progression entities:
//   "[Entity spawner] NoModel+2Cpnt" is the chapter hourglass — drives
//   the boss-timer "leave-arena flips it" mechanic and the early-boss-
//   kill reward chain. Moving it is not blocked, but understand the
//   side effects before you do.
//
// Depends on:
//   - RW.Player (hub helper — call RW.Player.refresh() first)
//   - RW.Entity (hub helper)
//
// REPL surface (after loadPower("Transporter")):
//   Transporter.warpEntity(name: string, x, y, z, roundtrip?): void
//   Transporter.warpPlayer(x, y, z, roundtrip?): void
//   Transporter.clear(): void

(function () {
    var version = "0.2.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Transporter] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    var POS_OFFSET      = 0x324;
    var SET_POS_VT_SLOT = 0x50;
    var TICK_MS         = 500;

    if (!RW.Transporter) RW.Transporter = {};
    var Transporter = RW.Transporter;

    // Cancel any leftover timers from a prior load
    if (Transporter._timers && Transporter._timers.length) {
        Transporter._timers.forEach(function (id) {
            try { clearInterval(id); } catch (e) {}
            try { clearTimeout(id);  } catch (e) {}
        });
    }
    Transporter._timers = [];

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p)    { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v)   { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }

    function setPosFor(ent) {
        var vt = ent.readPointer();
        return new NativeFunction(vt.add(SET_POS_VT_SLOT).readPointer(),
                                  'void', ['pointer', 'pointer']);
    }

    /*
     * ----------------------------------------------------------------
     * Transporter.warpEntity(name: string, x: number, y: number, z: number, roundtrip?: number): void
     *
     * Move the named entity to (x, y, z). If roundtrip is provided
     * (seconds), the entity is restored to its original position after
     * that interval; otherwise it stays at the new position.
     *
     * Name is a case-insensitive substring match against RW.Entity
     * (e.g., "cauldron" → "[Entity spawner] Cauldron").
     *
     * Caveats:
     *   - Invisible-anchor entities (camps, NoModel) move silently —
     *     nothing visible relocates. Use warpPlayer to visit them.
     *   - The chapter hourglass (NoModel+2Cpnt) drives the boss-timer
     *     leave-arena flip and the early-boss-reward chain — moving
     *     it has progression side effects, but the call is not blocked.
     *
     * Result:
     *   On success the entity visibly relocates (if it has a renderer),
     *   tick-locked at the new position. If roundtrip given, restores
     *   to its captured original after that many seconds.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Resolves name via RW.Entity.find. Reads the oCEntity at
     *   settings+0x48, calls vtable[+0x50] (RVA 0x6ca7f0 setPosition)
     *   on a 500ms setInterval (defeats per-frame transform reset).
     *   On roundtrip expiry clears the interval and calls setPosition
     *   with the captured original position.
     */
    Transporter.warpEntity = function (name, x, y, z, roundtrip) {
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[Transporter] RW.Entity missing");
            return;
        }
        var hit = RW.Entity.find(name);
        if (!hit) { console.log("[Transporter] no match for \"" + name + "\""); return; }
        if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') {
            console.log("[Transporter] x, y, z must be numbers");
            return;
        }

        var origPos = vec3(hit.entity.add(POS_OFFSET));
        var setPos = setPosFor(hit.entity);
        var buf = Memory.alloc(12);

        function place() {
            buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
            setPos(hit.entity, buf);
        }
        place();
        var roundtripStr = (typeof roundtrip === 'number') ? " (roundtrip " + roundtrip + "s)" : " (no auto-restore)";
        console.log("[Transporter.warpEntity] " + hit.name + " -> " + v3str([x,y,z]) + roundtripStr);

        var tick = setInterval(place, TICK_MS);
        Transporter._timers.push(tick);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                clearInterval(tick);
                buf.writeFloat(origPos[0]); buf.add(4).writeFloat(origPos[1]); buf.add(8).writeFloat(origPos[2]);
                setPos(hit.entity, buf);
                console.log("[Transporter.warpEntity] " + hit.name + " restored to " + v3str(origPos));
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.warpPlayer(x: number, y: number, z: number, roundtrip?: number): void
     *
     * Warp the player to (x, y, z). If roundtrip is provided (seconds),
     * the player is returned to their original position after that
     * interval; otherwise they stay at the destination.
     *
     * Caveat: warping into an active enemy camp will get the player
     * killed — enemies are pre-spawned and aggressive. Keep roundtrips
     * short for combat-zone warps (the player can be killed before the
     * return fires).
     *
     * Result:
     *   Player visibly snaps to the destination on the next frame.
     *   With roundtrip, snaps back to the captured original after
     *   that many seconds.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads RW.Player.entity, captures original position from
     *   player+0x324, calls vtable[+0x50] (RVA 0x6ca7f0 setPosition)
     *   with the destination. Schedules a single setPosition with the
     *   original position after roundtrip seconds — no tick loop
     *   needed (player movement controller respects a one-shot write).
     */
    Transporter.warpPlayer = function (x, y, z, roundtrip) {
        if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
            console.log("[Transporter] RW.Player not captured — try RW.Player.refresh() and play one frame");
            return;
        }
        if (typeof x !== 'number' || typeof y !== 'number' || typeof z !== 'number') {
            console.log("[Transporter] x, y, z must be numbers");
            return;
        }
        var player = RW.Player.entity;
        var origPos = vec3(player.add(POS_OFFSET));
        var setPos = setPosFor(player);
        var buf = Memory.alloc(12);

        buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
        setPos(player, buf);
        var roundtripStr = (typeof roundtrip === 'number') ? " (return in " + roundtrip + "s)" : " (no auto-return)";
        console.log("[Transporter.warpPlayer] player -> " + v3str([x,y,z]) + roundtripStr);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                buf.writeFloat(origPos[0]); buf.add(4).writeFloat(origPos[1]); buf.add(8).writeFloat(origPos[2]);
                setPos(player, buf);
                console.log("[Transporter.warpPlayer] player returned to " + v3str(origPos));
            }, roundtrip * 1000);
            Transporter._timers.push(t);
        }
    };

    /*
     * ----------------------------------------------------------------
     * Transporter.clear(): void
     *
     * Cancel every active warpEntity tick interval and pending
     * roundtrip timer. Does NOT restore positions — entities and the
     * player stay wherever they were when clear() was called. Useful
     * for aborting in-flight roundtrips before a power reload.
     * ----------------------------------------------------------------
     */
    Transporter.clear = function () {
        Transporter._timers.forEach(function (id) {
            try { clearInterval(id); } catch (e) {}
            try { clearTimeout(id);  } catch (e) {}
        });
        Transporter._timers = [];
        console.log("[Transporter] all active operations cleared (no position restore)");
    };

    RW.registerMod("power:Transporter", version);
    console.log("[Transporter] " + version + " loaded.");
    console.log("[Transporter]   warpEntity(name, x, y, z, roundtrip?)");
    console.log("[Transporter]   warpPlayer(x, y, z, roundtrip?)");
})();

// Top-level alias for REPL convenience
var Transporter = RW.Transporter;
