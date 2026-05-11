// poc_warp_enemy.js — warp pre-spawned (dormant) enemy entities to the
// player's cell. Uses ctor-captured entity pointers because RW.Entity.find
// only sees the streamed-in encyclopedia (~15-30 entries near the player)
// — dormant ghouls in distant cells aren't there.
//
// Premise (verified by ctor dump): chapter init ctors every enemy in
// every camp at chapter load (Festering_Ghoul, Devouring_Ghoul, etc.
// all fire oCEntity::ctor during setup). They sit dormant in their
// camp positions until the streaming grid activates them on player
// proximity.
//
// Warp mechanism: ported from tools/frida/mods/powers/Transporter.js
// — same setPosition primitive (vtable[+0x50], RVA 0x6ca7f0), same
// 500ms re-apply tick, same per-entity tick dedup map. Difference is
// only the name-resolution path: Transporter uses RW.Entity.find;
// this mod uses a ctor-built name -> [oCEntity*, ...] map so dormant
// entities are reachable.
//
// Bootstrap: load this mod BEFORE chapter setup so the oCEntity::ctor
// hook captures every entity. State persists across re-loadMod.
//
// REPL surface (after loadMod("poc_warp_enemy")):
//   Warp.status(): void
//   Warp.list(filter?: string, limit?: number): void
//   Warp.warpToPlayer(name: string, index?: number,
//                     dx?: number, dy?: number, dz?: number,
//                     roundtrip?: number): NativePointer | null
//   Warp.clear(): void

(function () {
    var version = "0.11.1";
    if (typeof RW !== "object") {
        console.log("[Warp] FATAL: RW missing — load rw_lab.js first");
        return;
    }
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Warp] FATAL: no Ravenswatch.exe"); return; }
    var IMG = mod.base;

    var ENTITY_CTOR_RVA       = 0x6c96f0;     // oCEntity::ctor
    var SPAWNER_CTOR_RVA      = 0x2d0ee0;     // oCEntityCpntEntitySpawner ctor
    var ENTITY_SETTINGS_OFF   = 0x28;         // entity.+0x28 = oCEntitySettings*
    var ENTITY_POS_OFF        = 0x324;        // entity.+0x324 = world position xyz (renderer/AI move)
    var ENTITY_ANCHOR_OFF     = 0x2e0;        // entity.+0x2e0 = bound/anchor position (leash reference)
    var SET_POS_VT_SLOT       = 0x50;         // entity.vtable[+0x50] = setPosition
    var SPAWNER_PARENT_OFF    = 0x08;         // spawner.+0x08 = parent oCEntity*
    var SPAWNER_CACHED_OFF    = 0x160;        // spawner.+0x160 = cached output entity*
    var SPAWNER_CHILDREN_OFF  = 0x210;        // spawner.+0x210 = child entity ptr array
    var SPAWNER_CHILD_COUNT   = 0x218;        // spawner.+0x218 = u32 count
    var SETTINGS_NAME_PTR_OFF = 0x08;
    var SETTINGS_NAME_LEN_OFF = 0x10;
    var TICK_MS               = 500;          // Transporter's proven cadence
    var DEFAULT_DX            = 2;
    var DEFAULT_DY            = 0;
    var DEFAULT_DZ            = 0;

    if (!RW.Warp) RW.Warp = {};
    var Warp = RW.Warp;
    Warp._byName       = Warp._byName       || {};   // resolved: name -> [oCEntity*, ...]
    Warp._pending      = Warp._pending      || [];   // unresolved: [{entity, settings, attempts}, ...]
    Warp._spawners     = Warp._spawners     || [];   // every captured oCEntityCpntEntitySpawner
    Warp._lastScan     = Warp._lastScan     || [];   // scanActive output: [{name, index, ptr, origX/Y/Z}, ...]
    Warp._lastCamp     = Warp._lastCamp     || null; // {name, entity, origX, origY, origZ} from last summon
    Warp._timers       = Warp._timers       || [];   // every active interval/timeout id
    Warp._entityTicks  = Warp._entityTicks  || {};   // "warp:0xPTR" -> intervalId (warp dedup)
    Warp._hooks        = Warp._hooks        || [];

    // Re-load safety: detach prior hooks + clear active ticks. _byName
    // and _pending persist across re-loads.
    Warp._hooks.forEach(function (h) { try { h.detach(); } catch (e) {} });
    Warp._hooks = [];
    Warp._timers.forEach(function (id) {
        try { clearInterval(id); } catch (e) {}
        try { clearTimeout(id); } catch (e) {}
    });
    Warp._timers = [];
    Warp._entityTicks = {};

    function readSettingsName(settings) {
        try {
            if (!settings || settings.isNull()) return null;
            if (settings.toString() === '0xffffffffffffffff') return null;
            var p = settings.add(SETTINGS_NAME_PTR_OFF).readPointer();
            var n = settings.add(SETTINGS_NAME_LEN_OFF).readU32();
            if (n <= 0 || n > 512) return null;
            return p.readUtf8String(n);
        } catch (e) { return null; }
    }

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p)    { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v)   { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }

    function setPosFor(ent) {
        var vt = ent.readPointer();
        return new NativeFunction(
            vt.add(SET_POS_VT_SLOT).readPointer(),
            'void', ['pointer', 'pointer']
        );
    }

    function clearEntityTick(key) {
        var t = Warp._entityTicks[key];
        if (t !== undefined) {
            try { clearInterval(t); } catch (e) {}
            delete Warp._entityTicks[key];
        }
    }

    function setEntityTick(key, place) {
        clearEntityTick(key);
        var tick = setInterval(place, TICK_MS);
        Warp._entityTicks[key] = tick;
        Warp._timers.push(tick);
        return tick;
    }

    function getPlayerPos() {
        try {
            if (!RW.Player || !RW.Player.entity || RW.Player.entity.isNull()) {
                return null;
            }
            return vec3(RW.Player.entity.add(ENTITY_POS_OFF));
        } catch (e) { return null; }
    }

    // Capture every spawner-component instance — used for the spawner-
    // children walk when active enemies aren't in _byName directly.
    Warp._hooks.push(Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
        onEnter: function (args) {
            try { Warp._spawners.push(ptr(args[0])); }
            catch (e) {}
        }
    }));

    // Capture every (entity, settings) pair from oCEntity::ctor.
    // Hot-path: minimal work, just buffer pointers. Names are read
    // later by the resolver tick — settings asset names aren't always
    // streamed in by the time ctor fires, so reading at onEnter time
    // would silently drop most ctors (the bug v0.2.0 had).
    Warp._hooks.push(Interceptor.attach(IMG.add(ENTITY_CTOR_RVA), {
        onEnter: function (args) {
            try {
                Warp._pending.push({
                    entity:   ptr(args[0]),
                    settings: ptr(args[1]),
                    attempts: 0,
                });
            } catch (e) {}
        }
    }));

    // Resolver tick: walk _pending, try to read each settings name now
    // that async streaming has caught up. Resolved entries move to
    // _byName. Unresolved entries get retried up to RESOLVE_MAX_ATTEMPTS
    // (~15 sec at 500ms) before being dropped — covers most async-streaming
    // delays without growing _pending unboundedly.
    var RESOLVE_INTERVAL_MS = 500;
    var RESOLVE_MAX_ATTEMPTS = 30;   // 30 * 500ms = 15s
    var resolverTick = setInterval(function () {
        if (Warp._pending.length === 0) return;
        var stillPending = [];
        for (var i = 0; i < Warp._pending.length; i++) {
            var rec = Warp._pending[i];
            var name;
            try { name = readSettingsName(rec.settings); }
            catch (e) { name = null; }
            if (name) {
                if (!Warp._byName[name]) Warp._byName[name] = [];
                Warp._byName[name].push(rec.entity);
            } else if (rec.attempts < RESOLVE_MAX_ATTEMPTS) {
                rec.attempts++;
                stillPending.push(rec);
            }
            // else: drop (entity destroyed, or settings never streamed)
        }
        Warp._pending = stillPending;
    }, RESOLVE_INTERVAL_MS);
    Warp._timers.push(resolverTick);

    /*
     * ----------------------------------------------------------------
     * Warp.status(): void
     *
     * Print capture state: number of unique names, total entities,
     * active warp ticks.
     * ----------------------------------------------------------------
     */
    Warp.status = function () {
        var nameCount = Object.keys(Warp._byName).length;
        var totalEntities = 0;
        Object.keys(Warp._byName).forEach(function (n) {
            totalEntities += Warp._byName[n].length;
        });
        var active = Object.keys(Warp._entityTicks).length;
        console.log("[Warp] " + nameCount + " unique names, " +
                    totalEntities + " resolved entities, " +
                    Warp._pending.length + " pending name-resolve, " +
                    active + " active warp tick(s)");
    };

    /*
     * ----------------------------------------------------------------
     * Warp.list(filter?: string, limit?: number): void
     *
     * List captured entity names with multi-instance counts.
     *
     * Usage:
     *   Warp.list("ghoul")
     *   Warp.list("Standard_")
     *   Warp.list("", 30)
     * ----------------------------------------------------------------
     */
    Warp.list = function (filter, limit) {
        var f = (filter || "").toLowerCase();
        var lim = (typeof limit === 'number') ? limit : 100;
        var entries = [];
        Object.keys(Warp._byName).forEach(function (name) {
            if (!f || name.toLowerCase().indexOf(f) >= 0) {
                entries.push([name, Warp._byName[name].length]);
            }
        });
        entries.sort(function (a, b) { return b[1] - a[1]; });
        var n = Math.min(entries.length, lim);
        for (var j = 0; j < n; j++) {
            console.log("  " + entries[j][0] + " (" + entries[j][1] + ")");
        }
        console.log("[Warp.list] " + entries.length + " match(es)" +
                    (entries.length > n ? ", showing top " + n : ""));
    };

    /*
     * ----------------------------------------------------------------
     * Warp.warpToPlayer(name: string, index?: number,
     *                   dx?: number, dy?: number, dz?: number,
     *                   roundtrip?: number): NativePointer | null
     *
     * Warp the index-th captured entity of the given name to
     * (player + offset), then re-apply via 500ms tick to defeat any
     * per-frame engine reset. If roundtrip > 0, restore the entity
     * to its original position after that many seconds.
     *
     * Mirrors Transporter.warpEntity exactly — same setPosition vtable
     * slot, same TICK_MS cadence, same per-entity tick dedup. The only
     * difference is name-resolution: this uses ctor-captured pointers
     * so dormant enemies are reachable (RW.Entity.find can't see them).
     *
     * Usage:
     *   Warp.warpToPlayer("Festering_Ghoul")              // first match, +2x
     *   Warp.warpToPlayer("Festering_Ghoul", 2)           // 3rd captured
     *   Warp.warpToPlayer("Festering_Ghoul", 0, 5)        // 5 units +x
     *   Warp.warpToPlayer("Festering_Ghoul", 0, 2, 0, 0, 10)  // restore in 10s
     *
     * Result:
     *   Returns the warped entity pointer on success. Position field
     *   is rewritten every 500ms to defeat per-frame snap-back. With
     *   roundtrip, restores after that many seconds.
     *
     * Caveats:
     *   - Name must exactly match the asset name (case-sensitive).
     *     Use Warp.list to discover.
     *   - Re-calling on the same entity replaces the prior tick
     *     (no stacked loops).
     *   - Entity may still be invisible if rendering is cell-gated
     *     by streaming-grid membership — moving the entity doesn't
     *     update its grid registration. If invisible after warp,
     *     that's a separate dig.
     * ----------------------------------------------------------------
     */
    Warp.warpToPlayer = function (name, index, dx, dy, dz, roundtrip) {
        if (typeof name !== 'string') {
            console.log("[Warp.warpToPlayer] need (name, index?, dx?, dy?, dz?, roundtrip?)");
            return null;
        }
        var idx = (typeof index === 'number') ? index : 0;
        if (typeof dx !== 'number') dx = DEFAULT_DX;
        if (typeof dy !== 'number') dy = DEFAULT_DY;
        if (typeof dz !== 'number') dz = DEFAULT_DZ;

        var pp = getPlayerPos();
        if (!pp) {
            console.log("[Warp.warpToPlayer] no player — RW.Player.refresh() first");
            return null;
        }
        var list = Warp._byName[name];
        if (!list || list.length === 0) {
            console.log("[Warp.warpToPlayer] no \"" + name + "\" captured — try " +
                        "Warp.list(\"" + name + "\")");
            return null;
        }
        if (idx >= list.length) {
            console.log("[Warp.warpToPlayer] only " + list.length + " \"" + name +
                        "\" captured; index " + idx + " out of range");
            return null;
        }

        var entity = list[idx];
        var tx = pp[0] + dx, ty = pp[1] + dy, tz = pp[2] + dz;
        var origPos = vec3(entity.add(ENTITY_POS_OFF));
        var setPos = setPosFor(entity);
        var buf = Memory.alloc(12);

        // Capture target at warp-time. Tick re-applies the SAME coords
        // every 500ms to defeat per-frame snap-back, but the entity
        // does NOT track the player — it sits where the player was
        // when warpToPlayer was called.
        function place() {
            buf.writeFloat(tx);
            buf.add(4).writeFloat(ty);
            buf.add(8).writeFloat(tz);
            setPos(entity, buf);
        }
        place();
        var roundtripStr = (typeof roundtrip === 'number')
            ? " (roundtrip " + roundtrip + "s)"
            : " (no auto-restore)";
        console.log("[Warp.warpToPlayer] " + name + " #" + idx +
                    " -> " + v3str([tx, ty, tz]) + roundtripStr);

        var key = "warp:" + entity.toString();
        setEntityTick(key, place);

        if (typeof roundtrip === 'number' && roundtrip > 0) {
            var t = setTimeout(function () {
                clearEntityTick(key);
                buf.writeFloat(origPos[0]);
                buf.add(4).writeFloat(origPos[1]);
                buf.add(8).writeFloat(origPos[2]);
                setPos(entity, buf);
                console.log("[Warp.warpToPlayer] " + name + " #" + idx +
                            " restored to " + v3str(origPos));
            }, roundtrip * 1000);
            Warp._timers.push(t);
        }
        return entity;
    };

    /*
     * ----------------------------------------------------------------
     * Warp.scanActive(radius?: number, nameFilter?: string): number
     *
     * Walk all captured entities, find those whose +0x324 position is
     * non-zero and within `radius` of the player, save them to
     * Warp._lastScan. Optionally substring-filter by name.
     *
     * Use to capture activated entities (full component setup, AI on,
     * rendering on) right after walking into a camp. Once captured,
     * the player can warp away and later use warpScannedToPlayer to
     * pull all scanned entities to a new location — they retain their
     * active state across the warp.
     *
     * Defaults: radius=15, nameFilter=null (no filter).
     *
     * Usage:
     *   Warp.scanActive()              // every active entity within 15u
     *   Warp.scanActive(20, "Hog")     // hogs within 20u
     *   Warp.scanActive(10, "Standard_Undead_Hog")  // exact prefix
     *
     * Returns the number of entities scanned.
     * ----------------------------------------------------------------
     */
    Warp.scanActive = function (radius, nameFilter) {
        var r = (typeof radius === 'number') ? radius : 15;
        var f = (typeof nameFilter === 'string') ? nameFilter.toLowerCase() : null;
        var pp = getPlayerPos();
        if (!pp) {
            console.log("[Warp.scanActive] no player — RW.Player.refresh()");
            return 0;
        }
        var scan = [];
        Object.keys(Warp._byName).forEach(function (name) {
            if (f && name.toLowerCase().indexOf(f) < 0) return;
            Warp._byName[name].forEach(function (e, i) {
                try {
                    var ep = e.add(ENTITY_POS_OFF);
                    var ex = ep.readFloat();
                    var ey = ep.add(4).readFloat();
                    var ez = ep.add(8).readFloat();
                    if (Math.abs(ex) < 0.01 && Math.abs(ey) < 0.01 &&
                        Math.abs(ez) < 0.01) return;   // skip pool stubs
                    var dx = ex - pp[0], dz = ez - pp[2];
                    var d = Math.sqrt(dx*dx + dz*dz);
                    if (d > r) return;
                    scan.push({ name: name, index: i, ptr: e,
                                origX: ex, origY: ey, origZ: ez, dist: d });
                } catch (err) {}
            });
        });
        scan.sort(function (a, b) { return a.dist - b.dist; });
        Warp._lastScan = scan;
        scan.forEach(function (s) {
            console.log("  " + s.name + "#" + s.index + " d=" + s.dist.toFixed(1));
        });
        console.log("[Warp.scanActive] " + scan.length + " entities saved to Warp._lastScan");
        return scan.length;
    };

    /*
     * ----------------------------------------------------------------
     * Warp.warpScannedToPlayer(spreadRadius?: number): number
     *
     * Warp every entity in Warp._lastScan to a fan around the player.
     * Uses each entity's setPosition (vtable[+0x50]) directly. No tick
     * loop — these are already-active entities; their controllers will
     * keep them where they are unless they pursue the player.
     *
     * Default spreadRadius=4 (4 units around player center).
     *
     * Usage:
     *   Warp.scanActive(15, "Hog")    // scan first
     *   <warp player elsewhere>
     *   Warp.warpScannedToPlayer()    // bring them all
     *
     * Returns the number of entities successfully warped.
     * ----------------------------------------------------------------
     */
    Warp.warpScannedToPlayer = function (spreadRadius) {
        var r = (typeof spreadRadius === 'number') ? spreadRadius : 4;
        var pp = getPlayerPos();
        if (!pp) {
            console.log("[Warp.warpScannedToPlayer] no player");
            return 0;
        }
        if (!Warp._lastScan || Warp._lastScan.length === 0) {
            console.log("[Warp.warpScannedToPlayer] no scan — call Warp.scanActive() first");
            return 0;
        }
        var ok = 0;
        for (var i = 0; i < Warp._lastScan.length; i++) {
            var s = Warp._lastScan[i];
            try {
                var angle = i * 0.7;
                var dist = 1 + (i * r) / Warp._lastScan.length;
                var tx = pp[0] + Math.cos(angle) * dist;
                var ty = pp[1];
                var tz = pp[2] + Math.sin(angle) * dist;
                // Update the bound/anchor position FIRST so the leash
                // logic doesn't immediately see "I'm far from anchor"
                // and start pulling the entity back. Then setPosition
                // updates the broadcast/render position field.
                s.ptr.add(ENTITY_ANCHOR_OFF     ).writeFloat(tx);
                s.ptr.add(ENTITY_ANCHOR_OFF +  4).writeFloat(ty);
                s.ptr.add(ENTITY_ANCHOR_OFF +  8).writeFloat(tz);
                var setPos = setPosFor(s.ptr);
                var buf = Memory.alloc(12);
                buf.writeFloat(tx);
                buf.add(4).writeFloat(ty);
                buf.add(8).writeFloat(tz);
                setPos(s.ptr, buf);
                ok++;
            } catch (err) {}
        }
        console.log("[Warp.warpScannedToPlayer] warped " + ok + "/" +
                    Warp._lastScan.length + " active entities to player");
        return ok;
    };

    /*
     * ----------------------------------------------------------------
     * Warp.restoreCamp(): boolean
     *
     * Move the most-recent summoned camp anchor back to its original
     * (pre-summon) position. Cleans up the "invisible mesh in safe
     * zone" side effect of summon's anchor-warp step. No-op if no
     * summon has been run.
     * ----------------------------------------------------------------
     */
    Warp.restoreCamp = function () {
        var c = Warp._lastCamp;
        if (!c) {
            console.log("[Warp.restoreCamp] no camp saved — run Warp.summon first");
            return false;
        }
        function restoreOne(entity, name, x, y, z) {
            try {
                var setPos = setPosFor(entity);
                var buf = Memory.alloc(12);
                buf.writeFloat(x);
                buf.add(4).writeFloat(y);
                buf.add(8).writeFloat(z);
                setPos(entity, buf);
                console.log("[Warp.restoreCamp] " + name + " -> (" +
                            x.toFixed(1) + "," + y.toFixed(1) + "," + z.toFixed(1) + ")");
                return true;
            } catch (e) {
                console.log("[Warp.restoreCamp] " + name + " threw: " + e.message);
                return false;
            }
        }
        var ok = restoreOne(c.entity, c.name, c.origX, c.origY, c.origZ) ? 1 : 0;
        if (c.related) {
            c.related.forEach(function (r) {
                if (restoreOne(r.entity, r.name, r.origX, r.origY, r.origZ)) ok++;
            });
        }
        return ok > 0;
    };

    /*
     * ----------------------------------------------------------------
     * Warp.restoreScanned(): number
     *
     * For every entity in Warp._lastScan, restore both its anchor
     * (+0x2e0) and its world position (+0x324) to the values captured
     * at scan time. Returns the count restored.
     * ----------------------------------------------------------------
     */
    Warp.restoreScanned = function () {
        if (!Warp._lastScan || Warp._lastScan.length === 0) {
            console.log("[Warp.restoreScanned] no scan");
            return 0;
        }
        var ok = 0;
        for (var i = 0; i < Warp._lastScan.length; i++) {
            var s = Warp._lastScan[i];
            try {
                s.ptr.add(ENTITY_ANCHOR_OFF     ).writeFloat(s.origX);
                s.ptr.add(ENTITY_ANCHOR_OFF +  4).writeFloat(s.origY);
                s.ptr.add(ENTITY_ANCHOR_OFF +  8).writeFloat(s.origZ);
                var setPos = setPosFor(s.ptr);
                var buf = Memory.alloc(12);
                buf.writeFloat(s.origX);
                buf.add(4).writeFloat(s.origY);
                buf.add(8).writeFloat(s.origZ);
                setPos(s.ptr, buf);
                ok++;
            } catch (e) {}
        }
        console.log("[Warp.restoreScanned] restored " + ok + "/" + Warp._lastScan.length);
        return ok;
    };

    /*
     * ----------------------------------------------------------------
     * Warp.summon(campNameSubstring: string, nameFilter?: string,
     *             opts?: { arriveMs?, returnMs?, scanRadius?, autoWarp?, spreadRadius? }): void
     *
     * The full automated workaround. Saves player position as "home",
     * warps to a camp, waits arriveMs for the streaming grid to
     * activate the cell, scans active enemies, warps back home, then
     * (if autoWarp) fans the scanned ones around the player.
     *
     * Default opts:
     *   arriveMs:     5000   (player runs around dodging during this)
     *   returnMs:      500   (delay between scan and return)
     *   scanRadius:     15
     *   autoWarp:     true   (fan scanned around player after return)
     *   spreadRadius:    4   (fan radius)
     *
     * Usage:
     *   Warp.summon("Hog Enemy Camp", "Hog")
     *   Warp.summon("Hog Enemy Camp", "Hog", { arriveMs: 8000 })
     *   Warp.summon("Hog Enemy Camp Wandering", "Hog", { autoWarp: false })
     *
     * The first arg is a substring of the CAMP name (e.g.,
     * "[Entity spawner] Hog Enemy Camp 01"). The second is an enemy
     * name substring filter for the scan.
     * ----------------------------------------------------------------
     */
    Warp.summon = function (campNameSubstring, nameFilter, opts) {
        opts = opts || {};
        var arriveMs    = (typeof opts.arriveMs    === 'number') ? opts.arriveMs    : 5000;
        var returnMs    = (typeof opts.returnMs    === 'number') ? opts.returnMs    :  500;
        var scanRadius  = (typeof opts.scanRadius  === 'number') ? opts.scanRadius  :   15;
        var spreadRadius= (typeof opts.spreadRadius=== 'number') ? opts.spreadRadius:    4;
        var autoWarp    = (opts.autoWarp    !== false);
        var autoRestore = (opts.autoRestore !== false);
        if (typeof campNameSubstring !== 'string') {
            console.log("[Warp.summon] need (campNameSubstring, nameFilter?, opts?)");
            return;
        }
        // Auto-restore from previous summon before starting a new one.
        // Defeats accumulated drift across runs.
        if (autoRestore) {
            if (Warp._lastCamp)               Warp.restoreCamp();
            if (Warp._lastScan.length)        Warp.restoreScanned();
        }
        if (!RW.Transporter || typeof RW.Transporter.warpPlayer !== 'function') {
            console.log("[Warp.summon] Transporter not loaded — loadPower(\"Transporter\")");
            return;
        }
        var home = getPlayerPos();
        if (!home) {
            console.log("[Warp.summon] no player position — RW.Player.refresh()");
            return;
        }
        // Find the primary camp by name (entity at non-zero coords)
        var campKey = campNameSubstring.toLowerCase();
        var camp = null;
        Object.keys(Warp._byName).forEach(function (name) {
            if (camp) return;
            if (name.toLowerCase().indexOf(campKey) < 0) return;
            try {
                var e = Warp._byName[name][0];
                var p = e.add(ENTITY_POS_OFF);
                var cx = p.readFloat(), cy = p.add(4).readFloat(), cz = p.add(8).readFloat();
                if (cx !== 0 || cy !== 0 || cz !== 0) {
                    camp = { name: name, entity: e, x: cx, y: cy, z: cz };
                }
            } catch (e) {}
        });
        if (!camp) {
            console.log("[Warp.summon] no camp matching \"" + campNameSubstring + "\"");
            return;
        }

        // Note: an earlier version auto-found related anchors (tile
        // camps, alt spawners) and moved them too. That dragged 64x64
        // tile collision into the safe zone and stuck the player.
        // Keep this empty — only the primary spawner-anchor moves now.
        var related = [];

        // Save anchor positions so restoreCamp can undo all of them.
        Warp._lastCamp = {
            name:    camp.name,
            entity:  camp.entity,
            origX:   camp.x,
            origY:   camp.y,
            origZ:   camp.z,
            related: related,
        };
        console.log("[Warp.summon] home=(" + home[0].toFixed(1) + "," + home[1].toFixed(1) + "," + home[2].toFixed(1) + ")");
        console.log("[Warp.summon] warping to " + camp.name + " (" + camp.x.toFixed(1) + "," + camp.y.toFixed(1) + "," + camp.z.toFixed(1) + ")");
        console.log("[Warp.summon] dodge for " + arriveMs + "ms...");
        RW.Transporter.warpPlayer(camp.x, camp.y, camp.z);

        var anchorWarp = (opts.anchorWarp !== false);   // default true

        var tScan = setTimeout(function () {
            var n = Warp.scanActive(scanRadius, nameFilter);
            var tHome = setTimeout(function () {
                console.log("[Warp.summon] returning home");
                RW.Transporter.warpPlayer(home[0], home[1], home[2]);
                if (autoWarp && n > 0) {
                    var tFan = setTimeout(function () {
                        // Drag the primary camp anchor AND every related
                        // tile/anchor to home. Leash logic may reference
                        // any of them — move them all to the player's
                        // current cell.
                        if (anchorWarp) {
                            function moveTo(ent, x, y, z, label) {
                                try {
                                    var setPos = setPosFor(ent);
                                    var buf = Memory.alloc(12);
                                    buf.writeFloat(x);
                                    buf.add(4).writeFloat(y);
                                    buf.add(8).writeFloat(z);
                                    setPos(ent, buf);
                                    console.log("[Warp.summon] " + label + " -> home");
                                } catch (e) {
                                    console.log("[Warp.summon] " + label + " threw: " + e.message);
                                }
                            }
                            moveTo(camp.entity, home[0], home[1], home[2], camp.name);
                            related.forEach(function (r) {
                                moveTo(r.entity, home[0], home[1], home[2], r.name);
                            });
                        }
                        Warp.warpScannedToPlayer(spreadRadius);
                    }, 500);
                    Warp._timers.push(tFan);
                }
            }, returnMs);
            Warp._timers.push(tHome);
        }, arriveMs);
        Warp._timers.push(tScan);
    };

    /*
     * ----------------------------------------------------------------
     * Warp.diff(nameA: string, idxA: number,
     *           nameB: string, idxB: number,
     *           len?: number): void
     *
     * Read `len` bytes from each entity and print offsets where bytes
     * differ. Consecutive differing bytes are grouped into ranges with
     * hex values shown for both sides. Used to find activation flags
     * by diffing an active enemy against a dormant one of the same class.
     *
     * Default len = 0x600 (1536 bytes — covers component-hashmap region).
     *
     * Usage:
     *   // Active hog (near player) vs pool stub (at 0,0,0):
     *   Warp.diff("Standard_Undead_Hog_Reaper", 2, "Standard_Undead_Hog_Reaper", 5)
     *
     *   // Active vs dormant-bound (different camp):
     *   Warp.diff("Standard_Undead_Hog_Fisherman", 3, "Standard_Undead_Hog_Fisherman", 0)
     *
     *   // Bigger range:
     *   Warp.diff("Standard_Undead_Hog_Reaper", 2, "Standard_Undead_Hog_Reaper", 5, 0x1000)
     *
     * Result: prints "0xOFFSET (N bytes): A=hex  B=hex" per range, then
     * a count of ranges + total differing bytes.
     * ----------------------------------------------------------------
     */
    Warp.diff = function (nameA, idxA, nameB, idxB, len) {
        var listA = Warp._byName[nameA];
        var listB = Warp._byName[nameB];
        if (!listA || idxA >= listA.length) {
            console.log("[Warp.diff] no \"" + nameA + "\" at index " + idxA);
            return;
        }
        if (!listB || idxB >= listB.length) {
            console.log("[Warp.diff] no \"" + nameB + "\" at index " + idxB);
            return;
        }
        var L = (typeof len === 'number') ? len : 0x600;
        var a, b;
        try {
            a = new Uint8Array(listA[idxA].readByteArray(L));
            b = new Uint8Array(listB[idxB].readByteArray(L));
        } catch (e) {
            console.log("[Warp.diff] read threw: " + e.message);
            return;
        }
        function hex(v) { return ('0' + v.toString(16)).slice(-2); }
        var ranges = [];
        var rStart = -1;
        for (var i = 0; i < L; i++) {
            if (a[i] !== b[i]) {
                if (rStart < 0) rStart = i;
            } else if (rStart >= 0) {
                ranges.push([rStart, i]);
                rStart = -1;
            }
        }
        if (rStart >= 0) ranges.push([rStart, L]);
        var totalBytes = 0;
        for (var j = 0; j < ranges.length; j++) {
            var s = ranges[j][0], e = ranges[j][1];
            var n = e - s;
            totalBytes += n;
            var ah = '', bh = '';
            for (var k = s; k < e && k - s < 16; k++) {
                ah += hex(a[k]) + ' ';
                bh += hex(b[k]) + ' ';
            }
            if (e - s > 16) { ah += '...'; bh += '...'; }
            console.log("0x" + ('000' + s.toString(16)).slice(-4) +
                        " (" + n + " bytes): A=" + ah.trim() + "  B=" + bh.trim());
        }
        console.log("[Warp.diff] " + ranges.length + " range(s), " +
                    totalBytes + " bytes differ over " + L + " scanned");
    };

    /*
     * ----------------------------------------------------------------
     * Warp.warpMeTo(name: string, index?: number,
     *               dx?: number, dy?: number, dz?: number): boolean
     *
     * Warp the PLAYER to (entity + offset). Default offset (5, 0, 0)
     * so the player lands a few units from the entity, not on top of
     * it. Reads the captured entity's +0x324 position and defers to
     * Transporter.warpPlayer for the actual move.
     *
     * Usage:
     *   Warp.warpMeTo("Festering_Ghoul")             // ghoul #0, +5x
     *   Warp.warpMeTo("Festering_Ghoul", 3)          // ghoul #3
     *   Warp.warpMeTo("Boss_Marsh_Ghoul", 0, 0, 0, -10)  // -10z
     *
     * Returns true on success, false if Transporter isn't loaded or
     * the entity isn't captured.
     * ----------------------------------------------------------------
     */
    Warp.warpMeTo = function (name, index, dx, dy, dz) {
        if (typeof name !== 'string') {
            console.log("[Warp.warpMeTo] need (name, index?, dx?, dy?, dz?)");
            return false;
        }
        if (!RW.Transporter || typeof RW.Transporter.warpPlayer !== 'function') {
            console.log("[Warp.warpMeTo] Transporter not loaded — loadPower(\"Transporter\")");
            return false;
        }
        var idx = (typeof index === 'number') ? index : 0;
        if (typeof dx !== 'number') dx = 5;
        if (typeof dy !== 'number') dy = 0;
        if (typeof dz !== 'number') dz = 0;
        var list = Warp._byName[name];
        if (!list || idx >= list.length) {
            console.log("[Warp.warpMeTo] no \"" + name + "\" at index " + idx);
            return false;
        }
        try {
            var entity = list[idx];
            var p = entity.add(ENTITY_POS_OFF);
            var ex = p.readFloat();
            var ey = p.add(4).readFloat();
            var ez = p.add(8).readFloat();
            RW.Transporter.warpPlayer(ex + dx, ey + dy, ez + dz);
            console.log("[Warp.warpMeTo] " + name + " #" + idx +
                        " is at (" + ex.toFixed(2) + "," + ey.toFixed(2) +
                        "," + ez.toFixed(2) + ") — player warped to offset");
            return true;
        } catch (e) {
            console.log("[Warp.warpMeTo] threw: " + e.message);
            return false;
        }
    };

    /*
     * ----------------------------------------------------------------
     * Warp.clear(): void
     *
     * Cancel every active warp tick and pending roundtrip timer. Does
     * NOT restore positions — entities stay wherever they were when
     * clear() was called. Mirror of Transporter.clear().
     * ----------------------------------------------------------------
     */
    Warp.clear = function () {
        Warp._timers.forEach(function (id) {
            try { clearInterval(id); } catch (e) {}
            try { clearTimeout(id); } catch (e) {}
        });
        Warp._timers = [];
        Warp._entityTicks = {};
        console.log("[Warp] all active operations cleared (no position restore)");
    };

    RW.registerMod("mod:poc_warp_enemy", version);
    console.log("[Warp] " + version + " loaded.");
    console.log("[Warp]   status()");
    console.log("[Warp]   list(filter?, limit?)");
    console.log("[Warp]   warpToPlayer(name, index?, dx?, dy?, dz?, roundtrip?)");
    console.log("[Warp]   warpMeTo(name, index?, dx?, dy?, dz?)        — warp player to entity");
    console.log("[Warp]   diff(nameA, idxA, nameB, idxB, len?)         — byte-diff two entities");
    console.log("[Warp]   scanActive(radius?, nameFilter?)             — capture active enemies near you");
    console.log("[Warp]   warpScannedToPlayer(spreadRadius?)           — fan scanned ones around player");
    console.log("[Warp]   summon(campSubstr, filter?, opts?)           — auto: warp→scan→return→fan");
    console.log("[Warp]   restoreCamp()                                — undo last summon's camp warp");
    console.log("[Warp]   restoreScanned()                             — undo warps on scanned entities");
    console.log("[Warp]   clear()");
})();

// Top-level alias for REPL convenience
var Warp = RW.Warp;
