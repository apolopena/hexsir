// Map.js — read the chapter's authoritative XZ bounding rectangle and
// produce safe drop-from-above spawn points.
//
// Backed by oCGpnSceneContext, the engine's per-chapter spatial-partition
// context. After level load, four floats at offsets +0xb8/+0xc0/+0xc4/+0xcc
// hold (X-min, Z-min, X-max, Z-max) — the playable horizontal extent the
// engine itself uses for streaming, navmesh, and culling. Y is intentionally
// unbounded by the Gpn (the +0xbc/+0xc8 slots hold ±1.0 axis-unit sentinels).
// See update_partitioning_boundings + gpn_set_chapter_bounds in Ghidra.
//
// REPL surface (after loadPower("Map")):
//   Map.bounds(): {xMin, zMin, xMax, zMax, width, length} | null
//   Map.dropAbove(x: number, z: number, dropY?: number): {x, y, z} | null
//   Map.dropRandom(dropY?: number): {x, y, z} | null
//   Map.size(): {width, length} | null      shorthand for max-min on each axis
//
// Design notes:
//   - Y axis is engine-unbounded; for drops, we pick a fixed high Y
//     (default 9999) and let gravity carry the entity to terrain.
//   - Bounds are valid AFTER the chapter's "Update partitioning boundings"
//     load step runs. If you call before that (early in chapter load),
//     bounds() returns null and logs a hint.
//   - Per rw/findings/telemetry-surface-and-warden.md... wait wrong doc;
//     this is fresh from the dig in this session — annotate with a
//     finding doc later.

(function () {
    var version = "0.5.1";

    if (typeof RW !== "object") {
        console.log("[Map] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    var rwMod = Process.findModuleByName("Ravenswatch.exe");
    if (!rwMod) { console.log("[Map] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = rwMod.base;

    // RVAs — fixed-tuning constants for this build.
    // From Ghidra: update_partitioning_boundings @ 0x1df540 calls
    // scene_manager_find_context_by_type with a tester struct built from
    // vftable @ 0xee4a38 + type-id pointer @ 0x1447ae0.
    var FIND_BY_TYPE_RVA       = 0x653f80;   // scene_manager_find_context_by_type(sm, tester) -> ctx
    var GPN_TESTER_VFTABLE_RVA = 0xee4a38;   // _oCTKindOfTypeTester<oCGpnSceneContext,...> vftable
    var GPN_TYPE_ID_PTR_RVA    = 0x1447ae0;  // runtime-init pointer slot holding the Gpn type ID

    // Field offsets on oCGpnSceneContext (verified from gpn_set_chapter_bounds).
    var GPN_X_MIN_OFF = 0xb8;
    var GPN_Z_MIN_OFF = 0xc0;
    var GPN_X_MAX_OFF = 0xc4;
    var GPN_Z_MAX_OFF = 0xcc;

    // Drop height policy: drops are always relative to the player's current
    // Y (which is, by definition, on valid terrain). Maximum offset is 20
    // units above the player — small enough to stay inside the rendered
    // frustum, big enough to give an observable ~0.5s fall. Higher values
    // hit skybox/cull issues and can land inside cliff geometry; constant
    // absolute Y values are categorically broken because the engine
    // doesn't bound Y and per-chapter elevation varies.
    var MAX_DROP_OFFSET = 20;

    // Drop horizontal radius policy: random drops pick (X, Z) within this
    // many units of the player's current X / Z (clamped to map bounds).
    // Keeps drops visible, observable, and inside the region the player
    // has already validated as on-map. Whole-map random drops produce
    // extreme distances from the player and waste cycles on points the
    // user can't even see land.
    var DEFAULT_DROP_RADIUS = 50;

    // Resolve current player Y; null if RW.Player hasn't captured yet.
    function _playerY() {
        if (!RW.Player || !RW.Player.loc) return null;
        var l = RW.Player.loc;
        if (!l || typeof l.y !== 'number') return null;
        return l.y;
    }

    if (!RW.Map) RW.Map = {};
    var Map = RW.Map;

    // Re-load safety: tester struct is per-process, build once.
    if (!Map._tester) {
        var t = Memory.alloc(16);
        t.writePointer(imageBase.add(GPN_TESTER_VFTABLE_RVA));
        t.add(8).writePointer(imageBase.add(GPN_TYPE_ID_PTR_RVA).readPointer());
        Map._tester = t;
    }

    var smFindByType = new NativeFunction(imageBase.add(FIND_BY_TYPE_RVA),
        "pointer", ["pointer", "pointer"]);

    // Resolve the GpnSceneContext using whichever scene_manager has been
    // captured by RW.Entity (the lab hub already arms a one-shot capture
    // hook on the find-by-type RVA). Returns null if not yet captured —
    // calling RW.Entity.list() once primes the capture.
    function findGpnCtx() {
        var sm = RW.Entity && RW.Entity._sm;
        if (!sm) {
            console.log("[Map] scene_manager not captured yet — call RW.Entity.list() once, then retry");
            return null;
        }
        try {
            var ctx = smFindByType(sm, Map._tester);
            if (ctx.isNull()) return null;
            return ctx;
        } catch (e) {
            console.log("[Map] findGpnCtx EXC: " + e.message);
            return null;
        }
    }

    function readBounds() {
        var ctx = findGpnCtx();
        if (!ctx) return null;
        try {
            var xMin = ctx.add(GPN_X_MIN_OFF).readFloat();
            var zMin = ctx.add(GPN_Z_MIN_OFF).readFloat();
            var xMax = ctx.add(GPN_X_MAX_OFF).readFloat();
            var zMax = ctx.add(GPN_Z_MAX_OFF).readFloat();
            // Sanity: if all four are zero, bounds haven't been set yet
            // (Update partitioning boundings hasn't run, or chapter just
            // started loading).
            if (xMin === 0 && zMin === 0 && xMax === 0 && zMax === 0) {
                console.log("[Map] bounds are all zero — Update partitioning boundings hasn't run yet");
                return null;
            }
            return {
                xMin: xMin, zMin: zMin, xMax: xMax, zMax: zMax,
                width: xMax - xMin, length: zMax - zMin
            };
        } catch (e) {
            console.log("[Map] readBounds EXC: " + e.message);
            return null;
        }
    }

    /*
     * ----------------------------------------------------------------
     * Map.bounds(): {xMin, zMin, xMax, zMax, width, length} | null
     *
     * Read the chapter's authoritative horizontal bounding rectangle
     * from oCGpnSceneContext. Returns the four corner coords plus
     * derived width (X) and length (Z). Returns null if the chapter
     * hasn't finished loading (Update partitioning boundings step not
     * yet run) or if scene_manager hasn't been captured yet.
     *
     * Result:
     *   Logs the bounds object on success; returns it. No log on
     *   failure paths — they print specific hints instead.
     *
     * Caveats:
     *   - Bounds are slightly larger than the strictly playable area
     *     (the engine pads by a factor in update_partitioning_boundings).
     *     Random points within bounds USUALLY hit terrain but can occasionally
     *     fall into voids near map edges. Run multiple drops and check.
     *   - Y is unbounded by the Gpn — see Map.dropAbove for the drop pattern.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Resolves oCGpnSceneContext via scene_manager_find_context_by_type
     *   (RVA 0x653f80) using a {vftable=0x140ee4a38, type_id=*0x141447ae0}
     *   tester struct. Reads 4 floats at ctx +0xb8 (X-min), +0xc0 (Z-min),
     *   +0xc4 (X-max), +0xcc (Z-max). Per gpn_set_chapter_bounds plate
     *   comment in Ghidra. Slots +0xbc / +0xc8 hold -1.0/+1.0 axis-unit
     *   sentinels (NOT Y bounds — Y is unbounded).
     */
    Map.bounds = function () {
        var b = readBounds();
        if (b) {
            console.log("[Map.bounds] X=[" + b.xMin.toFixed(1) + "," + b.xMax.toFixed(1) +
                        "] Z=[" + b.zMin.toFixed(1) + "," + b.zMax.toFixed(1) +
                        "] (width=" + b.width.toFixed(1) + ", length=" + b.length.toFixed(1) + ")");
        }
        return b;
    };

    /*
     * ----------------------------------------------------------------
     * Map.size(): {width, length} | null
     *
     * Shorthand for the dimensions of the bounding rectangle. Returns
     * { width: xMax-xMin, length: zMax-zMin } or null.
     * ----------------------------------------------------------------
     */
    Map.size = function () {
        var b = readBounds();
        return b ? { width: b.width, length: b.length } : null;
    };

    /*
     * ----------------------------------------------------------------
     * Map.dropAbove(x: number, z: number, dropY?: number): {x, y, z} | null
     *
     * Build a drop-from-above spawn point at the given (x, z). Clamps
     * x/z to the map's bounds before returning. Y defaults to 9999 (above
     * any reasonable terrain elevation).
     *
     * Usage:
     *   Map.dropAbove(0, 0)              // drop at world origin, Y = playerY + 20
     *   Map.dropAbove(100, -200)         // drop at (100, playerY+20, -200)
     *   Map.dropAbove(100, -200, 5)      // smaller offset (clamped to ≤ 20)
     *
     * Out-of-bounds inputs are clamped: passing (xMax + 1000, z) returns
     * the spawn at the X edge.
     *
     * Result:
     *   Logs the chosen point; returns {x, y, z}. Null if bounds aren't
     *   available yet.
     * ----------------------------------------------------------------
     */
    Map.dropAbove = function (x, z, offset) {
        var b = readBounds();
        if (!b) return null;
        var py = _playerY();
        if (py === null) {
            console.log("[Map.dropAbove] need RW.Player.loc — call RW.Player.refresh() and play one frame");
            return null;
        }
        var off = (typeof offset === 'number') ? offset : MAX_DROP_OFFSET;
        if (off > MAX_DROP_OFFSET) off = MAX_DROP_OFFSET;
        if (off < 0) off = 0;
        var cx = Math.max(b.xMin, Math.min(b.xMax, x));
        var cz = Math.max(b.zMin, Math.min(b.zMax, z));
        var clamped = (cx !== x || cz !== z);
        var dy = py + off;
        var pt = { x: cx, y: dy, z: cz };
        console.log("[Map.dropAbove] (" + cx.toFixed(1) + ", " + dy.toFixed(2) +
                    ", " + cz.toFixed(1) + ")  playerY=" + py.toFixed(2) + "+" + off +
                    (clamped ? " (clamped from " + x + "," + z + ")" : ""));
        return pt;
    };

    // Compute a tight XZ bounding box from the streaming asset cache.
    // Every encyclopedia entry is designer-placed on real terrain, so
    // their bounding box is guaranteed to enclose only valid map area —
    // unlike the Gpn rectangle which is padded into a cube and includes
    // off-terrain voids. Approximation: this BB still has internal
    // voids (irregular shape between entries), but its OUTER boundary
    // is reliably on-map. Tightens as more entries stream in during play.
    //
    // Cached because RW.Entity.list() is verbose (prints every entry
    // each call). Use Map.refreshBB() to recompute after exploration.
    Map._bbCache = Map._bbCache || null;

    function _encyclopediaBB(forceRefresh) {
        if (Map._bbCache && !forceRefresh) return Map._bbCache;
        if (!RW.Entity || typeof RW.Entity.list !== 'function') {
            console.log("[Map._BB] RW.Entity or .list missing");
            return null;
        }
        var entries;
        try { entries = RW.Entity.list(); }
        catch (e) {
            console.log("[Map._BB] list threw: " + e.message);
            return null;
        }
        if (!entries) { console.log("[Map._BB] list returned undefined"); return null; }
        if (!entries.length) { console.log("[Map._BB] list returned empty array"); return null; }
        var xMin = Infinity, xMax = -Infinity, zMin = Infinity, zMax = -Infinity, withLoc = 0;
        for (var i = 0; i < entries.length; i++) {
            var l = entries[i].loc;
            if (!l) continue;
            withLoc++;
            if (l.x < xMin) xMin = l.x;
            if (l.x > xMax) xMax = l.x;
            if (l.z < zMin) zMin = l.z;
            if (l.z > zMax) zMax = l.z;
        }
        if (!isFinite(xMin)) {
            console.log("[Map._BB] xMin/zMin never updated despite withLoc=" + withLoc +
                        " of " + entries.length);
            // Dump first entry to see what shape we're getting
            if (entries.length > 0) {
                var first = entries[0];
                console.log("[Map._BB] entries[0].name=" + first.name +
                            " loc=" + JSON.stringify(first.loc) +
                            " typeof loc.x=" + typeof (first.loc && first.loc.x));
            }
            return null;
        }
        Map._bbCache = {
            xMin: xMin, xMax: xMax, zMin: zMin, zMax: zMax,
            width: xMax - xMin, length: zMax - zMin,
            count: withLoc
        };
        return Map._bbCache;
    }

    /*
     * ----------------------------------------------------------------
     * Map.recover(): {x, y, z} | null
     *
     * Warp the player to the first encyclopedia entry — guaranteed to
     * be on real terrain at a sane Y. Use this when your player has
     * drifted into the sky / underground / off-map from prior bad
     * warps. After recover(), RW.Player.loc.y is a valid baseline for
     * subsequent drops.
     *
     * Result:
     *   Logs the chosen anchor + coords; returns the {x,y,z}. Null if
     *   encyclopedia is empty or RW.Player can't be captured.
     * ----------------------------------------------------------------
     */
    Map.recover = function () {
        var entries;
        try { entries = RW.Entity.list(); }
        catch (e) { console.log("[Map.recover] list threw: " + e.message); return null; }
        if (!entries || !entries.length) {
            console.log("[Map.recover] no encyclopedia entries — chapter not loaded?");
            return null;
        }
        var anchor = entries[0];
        var l = anchor.loc;
        if (!l) { console.log("[Map.recover] entries[0] has no loc"); return null; }
        if (RW.Transporter && typeof RW.Transporter.warpPlayer === 'function') {
            RW.Transporter.warpPlayer(l.x, l.y, l.z);
        } else {
            console.log("[Map.recover] RW.Transporter not loaded — loadPower(\"Transporter\")");
            return null;
        }
        console.log("[Map.recover] warped to '" + anchor.name + "' at (" +
                    l.x.toFixed(1) + "," + l.y.toFixed(1) + "," + l.z.toFixed(1) + ")");
        return l;
    };

    /*
     * ----------------------------------------------------------------
     * Map.refreshBB(): {xMin, zMin, xMax, zMax, count} | null
     *
     * Force a recompute of the encyclopedia-derived bounding box.
     * Useful after walking around in-game to stream in more anchors —
     * the BB widens as more entries appear in RW.Entity.list().
     * Walks RW.Entity.list() (which prints all entries) and caches the
     * resulting BB for subsequent Map.dropRandom() calls.
     * ----------------------------------------------------------------
     */
    Map.refreshBB = function () {
        Map._bbCache = null;
        var bb = _encyclopediaBB();
        if (bb) {
            console.log("[Map.refreshBB] X=[" + bb.xMin.toFixed(1) + "," + bb.xMax.toFixed(1) +
                        "] Z=[" + bb.zMin.toFixed(1) + "," + bb.zMax.toFixed(1) +
                        "] from " + bb.count + " encyclopedia entries");
        }
        return bb;
    };

    /*
     * ----------------------------------------------------------------
     * Map.dropRandom(dropY?: number): {x, y, z} | null
     *
     * Pick a uniformly-random (x, z) inside the encyclopedia-anchor
     * bounding box (NOT the Gpn rectangle from Map.bounds() — that one
     * includes engine padding that lands you off-map). drop-Y high above.
     *
     * Usage:
     *   Map.dropRandom()         // random in BB, Y = playerY + 20
     *   Map.dropRandom(5)        // smaller offset (clamped to ≤ 20)
     *
     * Result:
     *   Logs the chosen point + which BB was used; returns {x, y, z}.
     *
     * Caveats:
     *   - The encyclopedia bounding box is only as wide as the streamed
     *     entries reach. Early in a chapter you'll see ~15-30 entries
     *     near the player, growing to ~2000 deep into exploration. Drop
     *     points come from THAT region — not the full map. Walk around
     *     before calling for fuller coverage.
     *   - The BB still has internal voids (irregular terrain shape
     *     between anchors). Some drops still hit voids. Authoritative
     *     "always lands on terrain" needs raycast — wishlisted.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Walks RW.Entity.list() (encyclopedia walker), takes min/max of
     *   each entry's `loc.x` and `loc.z`. Falls back to Gpn rectangle if
     *   encyclopedia is empty or RW.Entity isn't loaded.
     */
    Map.dropRandom = function (radius, offset) {
        var bb = readBounds();
        if (!bb) return null;
        var p = (RW.Player && RW.Player.loc) || null;
        if (!p || typeof p.x !== 'number') {
            console.log("[Map.dropRandom] need RW.Player.loc — call RW.Player.refresh() and play one frame");
            return null;
        }
        var rad = (typeof radius === 'number') ? radius : DEFAULT_DROP_RADIUS;
        if (rad < 0) rad = 0;
        var off = (typeof offset === 'number') ? offset : MAX_DROP_OFFSET;
        if (off > MAX_DROP_OFFSET) off = MAX_DROP_OFFSET;
        if (off < 0) off = 0;
        var dx = (Math.random() * 2 - 1) * rad;
        var dz = (Math.random() * 2 - 1) * rad;
        var rx = Math.max(bb.xMin, Math.min(bb.xMax, p.x + dx));
        var rz = Math.max(bb.zMin, Math.min(bb.zMax, p.z + dz));
        var dy = p.y + off;
        var pt = { x: rx, y: dy, z: rz };
        console.log("[Map.dropRandom] (" + rx.toFixed(1) + ", " + dy.toFixed(2) +
                    ", " + rz.toFixed(1) + ")  playerY=" + p.y.toFixed(2) + "+" + off +
                    " radius=" + rad);
        return pt;
    };

    RW.registerMod("power:Map", version);
    console.log("[Map] " + version + " loaded. Try: Map.bounds()");
})();

// Top-level alias for REPL convenience
var Map = RW.Map;
