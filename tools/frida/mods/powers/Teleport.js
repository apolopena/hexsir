// Teleport.js — player teleport primitive.
//
// Mechanism: the player parent oCEntity has setPosition at vtable[+0x50]
// (RVA 0x6ca7f0). Calling it with a Vec3 writes +0x324 (canonical position)
// and broadcasts to subscribers (renderer, camera). The visible character
// follows. Verified runtime 2026-05-05.
//
// Notes:
//   - Small deltas (<5 units) may animate smoothly and look like a glide,
//     not a snap. Large deltas (>10) are clearly visible teleports.
//   - Y is the vertical axis. Chapter-1 ground around Y=0; preserve Y
//     unless you specifically want to change vertical (Y=0 in some areas
//     puts you below ground = void = falling).
//   - Fog-of-war does NOT auto-reveal on teleport (movement-bound). POI
//     markers DO reveal on teleport when you land near one (proximity-
//     based).
//
// REPL surface (after loadPower("Teleport")):
//   Teleport.refresh(): void
//   Teleport.position(): [number, number, number] | null
//   Teleport.to(x: number, y: number, z: number): void
//   Teleport.by(dx: number, dy: number, dz: number): void
//   Teleport.delayTo(seconds: number, x: number, y: number, z: number): void
//   Teleport.delayBy(seconds: number, dx: number, dy: number, dz: number): void
//   Teleport.toSpawn(): void
//   Teleport.player: NativePointer | null   — player parent oCEntity (= hc + 0x08)
//   Teleport.hc:     NativePointer | null   — HeroController-persistent (HC) pointer
//
// Teleport.hc is exposed as a cross-power borrow point — a known
// kludge. Other powers (currently Currency) need the HC pointer for
// direct field writes; Teleport's HC_per_frame_update hook is the
// cheapest place to capture it, so they reach into Teleport.hc as a
// fallback. The proper fix is to promote HC capture to a shared
// utility (RW.hc) once a third consumer appears. Read-only —
// downstream consumers must NEVER write to Teleport.hc. See
// CODE_STANDARDS.md §Cross-power state sharing.

(function () {
    var version = "0.2.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Teleport] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    // Used by multiple methods (refresh, position, by, to via vec3 reads).
    var POS_OFFSET = 0x324;

    if (!RW.Teleport) RW.Teleport = {};
    var Teleport = RW.Teleport;

    Teleport.player = null;        // NativePointer | null — the player oCEntity*
    Teleport.hc     = null;        // NativePointer | null — HeroController-persistent;
                                   // exposed for cross-power composition (Currency)
    Teleport._setPosFn = null;     // cached NativeFunction wrapper
    Teleport._captureHook = null;  // active HC_per_frame_update hook (or null)

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p) { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v) { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }

    function bindSetPos() {
        var SET_POS_VT_SLOT = 0x50;    // oCEntity::setPosition (RVA 0x6ca7f0)

        if (Teleport.player === null) return;
        var vt = Teleport.player.readPointer();
        Teleport._setPosFn = new NativeFunction(vt.add(SET_POS_VT_SLOT).readPointer(),
                                                'void', ['pointer', 'pointer']);
    }

    /*
     * ----------------------------------------------------------------
     * Teleport.refresh(): void
     *
     * Arm a one-shot Interceptor that captures the player's parent
     * oCEntity pointer on the next ticked frame, then detaches itself.
     * Required before any of to/by/toSpawn/position can be used.
     * Re-run after a chapter reload (heap addresses change).
     *
     * Result:
     *   On the next frame the game ticks (game must be unpaused),
     *   Teleport.player is populated and the cached setPos NativeFunction
     *   is bound. Logs the captured address + current position.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Hooks HC_per_frame_update at RVA 0x38e260. param_2 is the HC
     *   array header (count at +0x00, array ptr at +0x08). HC[0]+0x08
     *   is the player's parent oCEntity. The oCEntity's vtable[+0x50]
     *   is setPosition (RVA 0x6ca7f0); we pre-bind a NativeFunction
     *   wrapper to it so to()/by() are zero-allocation calls.
     */
    Teleport.refresh = function () {
        var HC_PER_FRAME_RVA = 0x38e260;

        if (Teleport._captureHook) {
            try { Teleport._captureHook.detach(); } catch (e) {}
            Teleport._captureHook = null;
        }
        Teleport.player = null;
        Teleport._setPosFn = null;
        Teleport._captureHook = Interceptor.attach(imageBase.add(HC_PER_FRAME_RVA), {
            onEnter: function (args) {
                if (Teleport.player !== null) return;
                try {
                    var hdr = ptr(args[1]);
                    var len = hdr.readU32();
                    if (len <= 0) return;
                    var arr = hdr.add(0x08).readPointer();
                    var hc = arr.readPointer();
                    Teleport.hc = hc;                              // shared with Currency
                    Teleport.player = hc.add(0x08).readPointer();
                    bindSetPos();
                    console.log("[Teleport] captured player=" + Teleport.player +
                                " hc=" + Teleport.hc +
                                " pos=" + v3str(vec3(Teleport.player.add(POS_OFFSET))));
                    Teleport._captureHook.detach();
                    Teleport._captureHook = null;
                } catch (e) { console.log("[Teleport] capture EXC: " + e.message); }
            },
        });
        console.log("[Teleport] refresh armed; play one frame to capture");
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.position(): [number, number, number] | null
     *
     * Read the player's current world position.
     *
     * Result:
     *   Logs "[Teleport] pos=(x,y,z)" and returns [x, y, z] as a JS
     *   array of 3 floats. Returns null if Teleport.refresh() hasn't
     *   captured the player yet.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads three contiguous float32s from oCEntity+0x324. The same
     *   field that setPosition writes (vtable[+0x50]) and that
     *   HC_per_frame_update reads via vtable[+0x48].
     */
    Teleport.position = function () {
        if (Teleport.player === null) {
            console.log("[Teleport] no player; call Teleport.refresh()");
            return null;
        }
        var v = vec3(Teleport.player.add(POS_OFFSET));
        console.log("[Teleport] pos=" + v3str(v));
        return v;
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.to(x: number, y: number, z: number): void
     *
     * Absolute teleport — visible character snaps to (x, y, z) on the
     * next render frame.
     *
     * Coordinate notes:
     *   - Chapter-1 spawn area is around (125, 0, -200). The map has
     *     finite bounds; landing off-map puts you in the void with no
     *     collision floor (you fall). Use toSpawn() to recover.
     *
     * Result:
     *   Logs "[Teleport] to (x,y,z)". Returns void.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Calls oCEntity::setPosition at vtable[+0x50] (RVA 0x6ca7f0).
     *   The engine writes the canonical position field at +0x324 and
     *   broadcasts to subscribers on the +0x3a8 handler list (camera,
     *   renderer, etc.). Verified runtime 2026-05-05.
     */
    Teleport.to = function (x, y, z) {
        if (Teleport.player === null || Teleport._setPosFn === null) {
            console.log("[Teleport] no player; call Teleport.refresh()");
            return;
        }
        var buf = Memory.alloc(12);
        buf.writeFloat(x); buf.add(4).writeFloat(y); buf.add(8).writeFloat(z);
        Teleport._setPosFn(Teleport.player, buf);
        console.log("[Teleport] to " + v3str([x, y, z]));
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.by(dx: number, dy: number, dz: number): void
     *
     * Relative teleport. Pass 0 on the axes you don't want to change.
     *
     * Examples:
     *   Teleport.by(5, 0, 0)    // shift +5 X, preserve Y and Z
     *   Teleport.by(0, 10, 0)   // float up 10 units
     *   Teleport.by(-3, 0, -3)  // shift northwest in world coords
     *
     * Result:
     *   Same as to() — visual character snaps on the next frame.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads current position from oCEntity+0x324, adds the 3-axis
     *   delta, calls Teleport.to() with the absolute result.
     */
    Teleport.by = function (dx, dy, dz) {
        if (Teleport.player === null) {
            console.log("[Teleport] no player; call Teleport.refresh()");
            return;
        }
        var c = vec3(Teleport.player.add(POS_OFFSET));
        Teleport.to(c[0] + dx, c[1] + dy, c[2] + dz);
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.delayTo(seconds: number, x: number, y: number, z: number): void
     *
     * Delayed Teleport.to. See CODE_STANDARDS.md §Delays.
     * ----------------------------------------------------------------
     */
    Teleport.delayTo = function (seconds, x, y, z) {
        console.log("[Teleport.delayTo] scheduled " + seconds.toFixed(2) +
                    "s -> to(" + x + "," + y + "," + z + ")");
        RW.after(seconds, function () { Teleport.to(x, y, z); });
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.delayBy(seconds: number, dx: number, dy: number, dz: number): void
     *
     * Delayed Teleport.by. See CODE_STANDARDS.md §Delays.
     * ----------------------------------------------------------------
     */
    Teleport.delayBy = function (seconds, dx, dy, dz) {
        console.log("[Teleport.delayBy] scheduled " + seconds.toFixed(2) +
                    "s -> by(" + dx + "," + dy + "," + dz + ")");
        RW.after(seconds, function () { Teleport.by(dx, dy, dz); });
    };

    /*
     * ----------------------------------------------------------------
     * Teleport.toSpawn(): void
     *
     * Recover to chapter-1's known-safe coordinates (125, 0, -200).
     * Useful after an off-map test puts you in the void and you want
     * to land back on solid ground without closing the chapter.
     *
     * Caveat:
     *   Coordinates are hard-coded for chapter 1 (Dark Hills). Other
     *   chapters need their own anchor — extend this when needed.
     *
     * Result:
     *   Same as to() — visual character snaps on the next frame.
     * ----------------------------------------------------------------
     */
    Teleport.toSpawn = function () {
        Teleport.to(125, 0, -200);
    };

    RW.registerMod("power:Teleport", version);
    console.log("[Teleport] " + version + " loaded. Try: Teleport.refresh(); Teleport.position(); Teleport.by(5, 0, 0)");
})();

// Top-level alias for REPL convenience
var Teleport = RW.Teleport;
