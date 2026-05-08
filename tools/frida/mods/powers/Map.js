// Map.js — pure coordinate getters for the chapter's geometry.
//
// Returns data; never warps, never fires. All actions (warp, drop) live
// in Transporter. Compose: `Transporter.dropPlayer(Map.center())`.
//
// SETUP-BOUND: load BEFORE chapter load. Map's IIFE auto-loads its
// dependency util/EntitySpawners (which arms a ctor hook), so loading
// Map post-chapter-init misses every spawner ctor for that chapter and
// landmark-derived getters (sandmanShop, center, point, randomPoint,
// peakY) return null. Map.bounds and Map.size only need scene_manager
// captured (any RW.Entity.find call once primes it).
//
// REPL surface (after loadPower("Map")):
//   Map.bounds():       {xMin, zMin, xMax, zMax, width, length} | null
//   Map.size():         {width, length} | null
//   Map.center():       {x, y, z} | null      Gpn-cube geometric center
//   Map.sandmanShop():  {x, y, z} | null      safe-zone return-plate
//   Map.point(dx, dz):  {x, y, z} | null      center + (dx, dz); Y = center.y
//   Map.randomPoint(r?):{x, y, z} | null      random within r of center; Y = center.y
//   Map.peakY():        number | null         max parent-Y across captured spawners
//   Map.resetChapter(): void                  clear cached center / shop
//
// Reference frame:
//   Center XZ = ((xMin+xMax)/2, (zMin+zMax)/2) from oCGpnSceneContext.
//   The Gpn-cube is the tight terrain-section-union AABB inflated
//   symmetrically into a square (factor DAT_140fa3cf4 = 0.5 on both
//   sides of the shorter axis), so the cube center equals the un-padded
//   terrain center — no padding bias. Field offsets +0xb8/+0xc0/+0xc4/
//   +0xcc; +0xbc/+0xc8 hold ±1.0 axis-unit sentinels (Y unbounded). See
//   update_partitioning_boundings + gpn_set_chapter_bounds in Ghidra.
//
//   Center Y inherits from sandmanShop.y. The Gpn doesn't store Y, and
//   the safe-zone plate is the most reliable on-terrain Y reference per
//   chapter — designer-placed, never warped by us.

(function () {
    var version = "0.9.0";

    if (typeof RW !== "object") {
        console.log("[Map] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    // Auto-load shared spawner-capture util. Map's landmark getters depend
    // on it, but the user never has to know — the util's ctor hook arms at
    // its own IIFE time.
    if (!RW.EntitySpawners || !RW.EntitySpawners._all) {
        if (typeof RW.loadUtil === 'function') {
            RW.loadUtil("EntitySpawners");
        } else {
            console.log("[Map] WARN: RW.loadUtil missing — landmark getters will be null");
        }
    }

    var rwMod = Process.findModuleByName("Ravenswatch.exe");
    if (!rwMod) { console.log("[Map] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = rwMod.base;

    var FIND_BY_TYPE_RVA       = 0x653f80;
    var GPN_TESTER_VFTABLE_RVA = 0xee4a38;
    var GPN_TYPE_ID_PTR_RVA    = 0x1447ae0;

    var GPN_X_MIN_OFF = 0xb8;
    var GPN_Z_MIN_OFF = 0xc0;
    var GPN_X_MAX_OFF = 0xc4;
    var GPN_Z_MAX_OFF = 0xcc;

    var ENTITY_POS_Y_OFF       = 0x328;
    var SPAWNER_PARENT_OFF     = 0x08;

    var SHOP_PARENT_NAME_MATCH = "teleporter_start";
    var DEFAULT_RANDOM_RADIUS  = 50;

    if (!RW.Map) RW.Map = {};
    var Map = RW.Map;

    if (!Map._tester) {
        var t = Memory.alloc(16);
        t.writePointer(imageBase.add(GPN_TESTER_VFTABLE_RVA));
        t.add(8).writePointer(imageBase.add(GPN_TYPE_ID_PTR_RVA).readPointer());
        Map._tester = t;
    }

    var smFindByType = new NativeFunction(imageBase.add(FIND_BY_TYPE_RVA),
        "pointer", ["pointer", "pointer"]);

    function findGpnCtx() {
        var sm = RW.Entity && RW.Entity._sm;
        if (!sm) {
            console.log("[Map] scene_manager not captured yet — call RW.Entity.find(\"x\") once to arm the hook");
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

    function spawnersReady() {
        return RW.EntitySpawners && RW.EntitySpawners._all && RW.EntitySpawners._all.length > 0;
    }

    function spawnersHint(method) {
        if (!RW.EntitySpawners || !RW.EntitySpawners._all) {
            return "[Map." + method + "] RW.EntitySpawners missing — was Map loaded before chapter? util should have auto-loaded";
        }
        return "[Map." + method + "] EntitySpawners has zero captures — was Map loaded BEFORE chapter load? Re-enter the chapter with Map already loaded.";
    }

    /*
     * ----------------------------------------------------------------
     * Map.bounds(): {xMin, zMin, xMax, zMax, width, length} | null
     *
     * The chapter's authoritative XZ bounding rectangle from
     * oCGpnSceneContext, plus derived width (X) and length (Z).
     * Returns null until the chapter's "Update partitioning boundings"
     * load step has run.
     *
     * Caveats:
     *   - Bounds are slightly larger than the strictly playable area
     *     (engine pads symmetrically into a cube). Random points inside
     *     usually hit terrain but can hit padding voids near edges.
     *   - Y is unbounded — see Map.center / Map.peakY for Y references.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Resolves oCGpnSceneContext via scene_manager_find_context_by_type
     *   (RVA 0x653f80) using a {vftable=0x140ee4a38, type_id=*0x141447ae0}
     *   tester struct. Reads 4 floats at ctx +0xb8 (X-min), +0xc0 (Z-min),
     *   +0xc4 (X-max), +0xcc (Z-max). Per gpn_set_chapter_bounds plate
     *   comment in Ghidra.
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
     * Shorthand for the dimensions of the bounding rectangle.
     * ----------------------------------------------------------------
     */
    Map.size = function () {
        var b = readBounds();
        return b ? { width: b.width, length: b.length } : null;
    };

    /*
     * ----------------------------------------------------------------
     * Map.sandmanShop(): {x, y, z} | null
     *
     * The chapter-start return-teleporter plate at the safe area —
     * where the player spawns and the Sandman is placed. Resolved
     * via EntitySpawners.find on the parentName "Teleporter_Start"
     * (matches every chapter suffix: Dark_Hills / Storm_Island / Avalon).
     *
     * Cached for the chapter on first successful read. Call
     * Map.resetChapter() on chapter transition.
     *
     * Returns null if Map wasn't loaded before chapter init (no captures).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   EntitySpawners.find("teleporter_start") returns
     *   {ptr, parent, parentName, parentLoc}. We pass through parentLoc
     *   as the sandman-shop position.
     */
    Map.sandmanShop = function () {
        if (Map._shop) return Map._shop;
        if (!spawnersReady()) {
            console.log(spawnersHint("sandmanShop"));
            return null;
        }
        var hit = RW.EntitySpawners.find(SHOP_PARENT_NAME_MATCH);
        if (!hit || !hit.parentLoc) {
            console.log("[Map.sandmanShop] no capture matching parentName ~ \"" +
                        SHOP_PARENT_NAME_MATCH + "\"");
            return null;
        }
        Map._shop = { x: hit.parentLoc.x, y: hit.parentLoc.y, z: hit.parentLoc.z };
        console.log("[Map.sandmanShop] (" + Map._shop.x.toFixed(2) + "," +
                    Map._shop.y.toFixed(2) + "," + Map._shop.z.toFixed(2) +
                    ")  parentName=\"" + hit.parentName + "\"");
        return Map._shop;
    };

    /*
     * ----------------------------------------------------------------
     * Map.center(): {x, y, z} | null
     *
     * Chapter geometric center: Gpn-cube center XZ + sandman-shop Y.
     * Cached for the chapter on first successful read.
     *
     * Returns null if bounds aren't loaded or sandmanShop can't resolve.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   X = (xMin + xMax) / 2; Z = (zMin + zMax) / 2 from Map.bounds.
     *   Symmetric Gpn-cube padding preserves center, so this equals the
     *   un-padded terrain-AABB center. Y inherits from Map.sandmanShop —
     *   the Gpn doesn't store Y, and the safe-zone plate is the most
     *   reliable on-terrain Y reference per chapter.
     */
    Map.center = function () {
        if (Map._center) return Map._center;
        var b = readBounds();
        if (!b) return null;
        var shop = Map.sandmanShop();
        if (!shop) return null;
        Map._center = {
            x: (b.xMin + b.xMax) / 2,
            y: shop.y,
            z: (b.zMin + b.zMax) / 2
        };
        console.log("[Map.center] (" + Map._center.x.toFixed(2) + "," +
                    Map._center.y.toFixed(2) + "," + Map._center.z.toFixed(2) + ")");
        return Map._center;
    };

    /*
     * ----------------------------------------------------------------
     * Map.point(dx, dz): {x, y, z} | null
     *
     * Center-relative point. Pass deltas from map center; X/Z are
     * clamped to Gpn bounds. Y inherits center.y. Pass (0, 0) for the
     * exact center.
     *
     * Result is in engine world coords — pass directly to
     * Transporter.warpPlayer / Transporter.dropPlayer.
     * ----------------------------------------------------------------
     */
    Map.point = function (dx, dz) {
        var c = Map.center();
        if (!c) return null;
        var b = readBounds();
        if (!b) return null;
        if (typeof dx !== 'number') dx = 0;
        if (typeof dz !== 'number') dz = 0;
        var rawX = c.x + dx;
        var rawZ = c.z + dz;
        var cx = Math.max(b.xMin, Math.min(b.xMax, rawX));
        var cz = Math.max(b.zMin, Math.min(b.zMax, rawZ));
        var clamped = (cx !== rawX || cz !== rawZ);
        var pt = { x: cx, y: c.y, z: cz };
        console.log("[Map.point] (" + cx.toFixed(1) + "," + c.y.toFixed(2) + "," + cz.toFixed(1) +
                    ")  center+(" + dx + "," + dz + ")" +
                    (clamped ? " [clamped to bounds]" : ""));
        return pt;
    };

    /*
     * ----------------------------------------------------------------
     * Map.randomPoint(radius?): {x, y, z} | null
     *
     * Uniformly-random point inside a square of side 2*radius (default
     * 50) centered on Map.center XZ, clamped to Gpn bounds. Y inherits
     * center.y.
     *
     * Caveats:
     *   - Square (not circular) sampling — corners reach radius*sqrt(2).
     *   - The Gpn rectangle has internal voids; some points still hit
     *     non-walkable terrain. Authoritative "always lands on terrain"
     *     needs raycast — wishlisted.
     * ----------------------------------------------------------------
     */
    Map.randomPoint = function (radius) {
        var c = Map.center();
        if (!c) return null;
        var b = readBounds();
        if (!b) return null;
        var rad = (typeof radius === 'number') ? radius : DEFAULT_RANDOM_RADIUS;
        if (rad < 0) rad = 0;
        var dx = (Math.random() * 2 - 1) * rad;
        var dz = (Math.random() * 2 - 1) * rad;
        var rx = Math.max(b.xMin, Math.min(b.xMax, c.x + dx));
        var rz = Math.max(b.zMin, Math.min(b.zMax, c.z + dz));
        var pt = { x: rx, y: c.y, z: rz };
        console.log("[Map.randomPoint] (" + rx.toFixed(1) + "," + c.y.toFixed(2) + "," + rz.toFixed(1) +
                    ")  center+(" + dx.toFixed(1) + "," + dz.toFixed(1) + ") radius=" + rad);
        return pt;
    };

    /*
     * ----------------------------------------------------------------
     * Map.peakY(): number | null
     *
     * Highest parent Y across all captured spawners — approximates the
     * tallest entity-bearing point on the map. Useful for reasoning
     * about safe drop altitudes (drops at peakY + small offset clear
     * all spawner-bearing geometry).
     *
     * Caveats:
     *   - Misses pure decoration / static geometry (walls, towers
     *     without spawner components). Lower bound on true map height.
     *   - Not cached; recomputes on each call (~12k captures, fast).
     * ----------------------------------------------------------------
     */
    Map.peakY = function () {
        if (!spawnersReady()) {
            console.log(spawnersHint("peakY"));
            return null;
        }
        var pool = RW.EntitySpawners._all;
        var maxY = -Infinity, maxParent = null;
        for (var i = 0; i < pool.length; i++) {
            var sp = pool[i];
            try {
                var parent = sp.add(SPAWNER_PARENT_OFF).readPointer();
                if (!parent || parent.isNull() || parent.toString() === '0xffffffffffffffff') continue;
                var y = parent.add(ENTITY_POS_Y_OFF).readFloat();
                if (!isFinite(y)) continue;
                if (y > maxY) { maxY = y; maxParent = parent; }
            } catch (e) {}
        }
        if (!isFinite(maxY)) {
            console.log("[Map.peakY] no readable parent Y values across " + pool.length + " captures");
            return null;
        }
        var name = null;
        if (maxParent) {
            try {
                var s = maxParent.add(0x28).readPointer();
                if (!s.isNull() && s.toString() !== '0xffffffffffffffff') {
                    var n = s.add(8).readPointer();
                    var l = s.add(0x10).readU32();
                    if (l > 0 && l < 256) name = n.readUtf8String(l);
                }
            } catch (e) {}
        }
        console.log("[Map.peakY] " + maxY.toFixed(2) + "  parentName=\"" + name + "\"");
        return maxY;
    };

    /*
     * ----------------------------------------------------------------
     * Map.resetChapter(): void
     *
     * Clear cached center / shop. Call after a chapter transition (or
     * any time you want recomputed values).
     * ----------------------------------------------------------------
     */
    Map.resetChapter = function () {
        Map._center = null;
        Map._shop   = null;
        console.log("[Map.resetChapter] center / shop caches cleared");
    };

    RW.registerMod("power:Map", version);
    console.log("[Map] " + version + " loaded. Try: Map.center()");
})();

// Top-level alias for REPL convenience
var Map = RW.Map;
