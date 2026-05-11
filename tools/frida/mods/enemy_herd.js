// enemy_herd.js — herd live enemies into a tight cluster every N seconds.
//
// Reads SpawnCapture's buffer, filters to entities that (a) have an
// EnemyController component and (b) pass the +0x620 self-pointer
// liveness check. Every intervalSec, picks roster[0] as anchor and
// warps every other enemy to within `radius` units of it (random
// scatter, XZ plane, Y preserved from anchor). Loops until the roster
// is empty (validated each tick), then auto-stops.
//
// Prereq: SpawnCapture must have captured the enemy entities. That
// works for cauldron types that spawn enemies dynamically during the
// fight (e.g., Cultist/Summoner). Doesn't work for chapter-load-
// pre-existing enemies (e.g., spider bosses) unless you arm
// SpawnCapture before chapter-load.
//
// Depends on:
//   - SpawnCapture (mod)  — for the capture buffer

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[EnemyHerd] FATAL: no Ravenswatch.exe"); return; }

    var POS_OFFSET        = 0x324;
    var SELF_REF_OFFSET   = 0x620;
    var SET_POS_VT_SLOT   = 0x50;
    var ENEMY_COMP_SUBSTR = "EnemyController";

    if (!RW.EnemyHerd) RW.EnemyHerd = {};
    var EnemyHerd = RW.EnemyHerd;

    // Cancel any leftover timer from a prior load
    if (EnemyHerd._timer) {
        try { clearInterval(EnemyHerd._timer); } catch (e) {}
    }
    EnemyHerd._timer  = null;
    EnemyHerd._roster = EnemyHerd._roster || [];
    EnemyHerd._buf    = EnemyHerd._buf    || Memory.alloc(12);

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p)    { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v)   { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }

    function isAlive(entity) {
        try {
            var selfRef = entity.add(SELF_REF_OFFSET).readPointer();
            return selfRef.equals(entity);
        } catch (e) { return false; }
    }

    function rttiName(obj) {
        try {
            var vt = obj.readPointer();
            var col = vt.sub(8).readPointer();
            var tdRva = col.add(0x0c).readU32();
            var selfRva = col.add(0x14).readU32();
            var imgBase = col.sub(selfRva);
            return imgBase.add(tdRva).add(0x10).readCString();
        } catch (e) { return "?"; }
    }

    function entityComponentNames(entity) {
        try {
            var ctrlPtr = entity.add(0x5e8).readPointer();
            var valsPtr = entity.add(0x5f0).readPointer();
            var count   = entity.add(0x5f8).readU64().toNumber();
            var capMask = entity.add(0x600).readU64().toNumber();
            if (ctrlPtr.isNull() || valsPtr.isNull() || count === 0 || capMask < 0) return [];
            var capacity = capMask + 1;
            if (capacity > 1024) return [];
            var names = [];
            for (var i = 0; i < capacity && names.length < 32; i++) {
                var ctrl;
                try { ctrl = ctrlPtr.add(i).readU8(); } catch (er) { break; }
                if (ctrl >= 0x80) continue;
                try {
                    var entry = valsPtr.add(i * 16);
                    var compPtr = entry.add(8).readPointer();
                    if (compPtr.isNull()) continue;
                    names.push(rttiName(compPtr));
                } catch (er) {}
            }
            return names;
        } catch (e) { return []; }
    }

    function isEnemy(entity) {
        var names = entityComponentNames(entity);
        for (var i = 0; i < names.length; i++) {
            if (names[i].indexOf(ENEMY_COMP_SUBSTR) >= 0) return true;
        }
        return false;
    }

    function settingsName(initArg) {
        try {
            if (initArg.isNull()) return null;
            var strPtr = initArg.add(0x08).readPointer();
            var len    = initArg.add(0x10).readU32();
            if (len <= 0 || len > 512) return null;
            return strPtr.readUtf8String(len);
        } catch (e) { return null; }
    }

    function warpTo(entity, x, y, z) {
        try {
            var vt = entity.readPointer();
            var setPosFn = vt.add(SET_POS_VT_SLOT).readPointer();
            var setPos = new NativeFunction(setPosFn, 'void', ['pointer', 'pointer']);
            EnemyHerd._buf.writeFloat(x);
            EnemyHerd._buf.add(4).writeFloat(y);
            EnemyHerd._buf.add(8).writeFloat(z);
            setPos(entity, EnemyHerd._buf);
            return true;
        } catch (e) { return false; }
    }

    /*
     * ----------------------------------------------------------------
     * EnemyHerd.start(opts?: { radius?: number, intervalSec?: number, templateSubstring?: string }): void
     *
     * Build a roster from SpawnCapture._captures: entities that have
     * an EnemyController component AND a valid +0x620 self-pointer.
     * Every intervalSec, drop dead roster entries, then warp every
     * surviving enemy except roster[0] (the anchor) to within `radius`
     * units of the anchor (random XZ scatter, anchor's Y preserved).
     * Auto-stops when the roster empties.
     *
     * opts.radius          Max scatter radius around anchor (default 2).
     * opts.intervalSec     Cycle period in seconds (default 5).
     * opts.templateSubstring  Optional case-insensitive substring filter
     *   against settings name (e.g. "Snake" to herd just snakes).
     *
     * Result:
     *   On success: prints "[EnemyHerd] armed N enemies"; tick runs
     *   in the background; control returns to REPL immediately.
     *   On failure (no captures, no enemies match, already running):
     *   prints a clear message and bails — no timer started.
     *
     * Caveats:
     *   - Roster is the snapshot at start() time. New spawns later in
     *     the fight are NOT auto-added. Call stop()+start() to refresh.
     *   - Roster comes from SpawnCapture._captures, so chapter-load-
     *     pre-existing enemies (not captured by oCEntity ctor) won't
     *     be herded unless SpawnCapture was armed before chapter-load.
     *   - Tick fires on host clock; pausing the game pauses visible
     *     effect but timer keeps firing.
     *   - Roster[0] is the anchor and never moves (others orbit it).
     *     If anchor dies, next tick it gets dropped and the new
     *     roster[0] takes over.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Filter SpawnCapture._captures via entityComponentNames() →
     *   match "EnemyController" substring → optional name filter →
     *   isAlive() (+0x620 self-pointer). Tick: filter roster by
     *   isAlive(), pick [0] as anchor, read pos at +0x324, for each
     *   other call vtable[+0x50] setPosition with anchor.pos +
     *   uniform-disc scatter (sqrt(rand()) * radius). Stop on empty.
     */
    EnemyHerd.start = function (opts) {
        if (EnemyHerd._timer) {
            console.log("[EnemyHerd] already running — call stop() first");
            return;
        }
        if (!RW.SpawnCapture || !RW.SpawnCapture._captures) {
            console.log("[EnemyHerd] SpawnCapture not loaded or no buffer — load and run a capture first");
            return;
        }

        var radius      = (opts && typeof opts.radius      === 'number') ? opts.radius      : 2;
        var intervalSec = (opts && typeof opts.intervalSec === 'number') ? opts.intervalSec : 5;
        var nameFilter  = (opts && opts.templateSubstring) ? String(opts.templateSubstring).toLowerCase() : null;

        var captures = RW.SpawnCapture._captures;
        var roster = [];
        var named  = [];
        captures.forEach(function (e) {
            if (!isAlive(e.entity)) return;
            if (!isEnemy(e.entity)) return;
            if (nameFilter) {
                var n = settingsName(e.initArg);
                if (!n || n.toLowerCase().indexOf(nameFilter) < 0) return;
            }
            roster.push(e.entity);
            named.push(settingsName(e.initArg) || "?");
        });

        if (!roster.length) {
            console.log("[EnemyHerd] no live enemies in SpawnCapture buffer" +
                        (nameFilter ? " matching \"" + nameFilter + "\"" : ""));
            return;
        }

        EnemyHerd._roster = roster;
        console.log("[EnemyHerd] armed " + roster.length + " enemies; herding every " +
                    intervalSec + "s within " + radius + "u of roster[0]:");
        roster.forEach(function (e, i) {
            console.log("  [" + i + "] " + e + "  " + named[i] + (i === 0 ? "  (anchor)" : ""));
        });

        function tick() {
            EnemyHerd._roster = EnemyHerd._roster.filter(isAlive);
            var live = EnemyHerd._roster;
            if (!live.length) {
                console.log("[EnemyHerd] all enemies gone, stopping");
                EnemyHerd.stop();
                return;
            }

            var anchor = live[0];
            var pos = vec3(anchor.add(POS_OFFSET));
            if (isNaN(pos[0])) {
                console.log("[EnemyHerd] anchor position read failed, skipping tick");
                return;
            }

            var moved = 0;
            for (var i = 1; i < live.length; i++) {
                var angle = Math.random() * Math.PI * 2;
                var r     = Math.sqrt(Math.random()) * radius;
                var x     = pos[0] + Math.cos(angle) * r;
                var z     = pos[2] + Math.sin(angle) * r;
                if (warpTo(live[i], x, pos[1], z)) moved++;
            }
            console.log("[EnemyHerd] tick: " + moved + "/" + (live.length - 1) +
                        " herded around anchor " + anchor + " " + v3str(pos));
        }

        EnemyHerd._timer = setInterval(tick, intervalSec * 1000);
    };

    /*
     * ----------------------------------------------------------------
     * EnemyHerd.stop(): void
     *
     * Cancel the tick loop. Enemies stay wherever they were last
     * placed — no position restore.
     * ----------------------------------------------------------------
     */
    EnemyHerd.stop = function () {
        if (!EnemyHerd._timer) {
            console.log("[EnemyHerd] not running");
            return;
        }
        try { clearInterval(EnemyHerd._timer); } catch (e) {}
        EnemyHerd._timer = null;
        console.log("[EnemyHerd] stopped");
    };

    RW.registerMod("enemy_herd", version);
    console.log("[EnemyHerd] " + version + " loaded. start(opts?) / stop()");
})();

// Top-level alias
var EnemyHerd = RW.EnemyHerd;
