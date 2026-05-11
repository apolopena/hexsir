// ARCHIVED — broadcast-worker / enableAndSpawn approach abandoned 2026-05-10.
//
// The premise was that camp anchors hold pre-bound spawners that, when fired,
// produce enemies. Live testing showed that direct calls to either the
// broadcast worker (FUN_1406f62b0) or enableAndSpawn (FUN_1406f04b0) on
// dormant streaming-grid spawners crash with sentinel-pointer reads — the
// state isn't initialized until the player walks into the spawner's cell.
//
// Reframe (verified by ctor dump): enemy oCEntity instances are CONSTRUCTED
// at chapter load (Festering_Ghoul, Devouring_Ghoul, etc. all appear in the
// chapter-load oCEntity::ctor capture). The streaming grid does NOT spawn
// them — it activates their AI on proximity. They exist throughout the
// chapter in dormant state at their camp positions.
//
// Superseded by tools/frida/mods/poc_warp_enemy.js, which warps the existing
// enemy entities to the player's cell — AI activates naturally on proximity,
// no spawner manipulation needed.
//
// =============================================================================
//
// poc_summon_enemy.js — proof-of-concept: fire any pre-bound in-world
// spawner via the broadcast worker.
//
// Mechanism: chapter init populates the world with pre-bound
// oCEntityCpntEntitySpawner instances — camp anchors, reward bags,
// the hourglass, etc. Each is bound at load time to whatever it spawns
// (enemy class, MO drop, prop, etc.). We capture every spawner ctor
// at chapter load, filter by parent-entity name, and fire the
// broadcast worker (FUN_1406f62b0 = oCEntitySpawner_fireSpawnWithBroadcast,
// RVA 0x6f62b0) directly on the chosen one.
//
// This is the same proven pattern used by:
//   - tools/frida/mods/spawner_probe.js v0.12.0 (expr_summonAtPlayer)
//   - tools/frida/mods/powers/Hourglass.js v0.4.0 (Hourglass.spawnItem)
//
// The output appears at the spawner's natural bound transform — for
// camp anchors, that's the camp's location. To get the spawn near the
// player, either warp the spawner's parent first (Transporter.warpEntity)
// or use spawner_probe's expr_summonAtPlayer which composes the warp.
//
// Bootstrap: hook fires automatically during chapter setup. Load this
// mod BEFORE chapter setup so the ctor hook captures the full spawner
// set. State persists across re-loadMod calls.
//
// Caveats:
//   - Only un-fired spawners can be re-fired through this path.
//     Direct call on a CONSUMED spawner (bit 3 of +0x64 set) crashes
//     per entity-spawner-mechanism.md §"What didn't work."
//   - Output entity type is whatever the engine pre-bound to the
//     spawner. We don't choose the type from a name string — we choose
//     a spawner whose binding produces the type we want.
//   - Spawn position is the spawner's bound transform. Override by
//     warping the parent before firing, or compose with Transporter.
//
// Depends on:
//   - rw_lab.js (RW.* hub)
//
// REPL surface (after loadMod("poc_summon_enemy")):
//   Summon.status(): void
//   Summon.list(filter?: string, limit?: number): void
//   Summon.fire(parentNameSubstring: string, index?: number): NativePointer | null
//   Summon.fireAtHourglass(parentNameSubstring: string, index?: number,
//                          dx?: number, dy?: number, dz?: number): NativePointer | null
//   Summon.lastChild(spawner): NativePointer | null

(function () {
    var version = "0.1.0";
    if (typeof RW !== "object") {
        console.log("[Summon] FATAL: RW missing — load rw_lab.js first");
        return;
    }
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Summon] FATAL: no Ravenswatch.exe"); return; }
    var IMG = mod.base;

    // Cross-references:
    //   rw/findings/entity-spawner-mechanism.md
    var SPAWNER_CTOR_RVA       = 0x2d0ee0;     // oCEntityCpntEntitySpawner ctor
    var BROADCAST_FIRE_RVA     = 0x6f62b0;     // oCEntitySpawner_fireSpawnWithBroadcast
    var ENABLE_AND_SPAWN_RVA   = 0x6f04b0;     // oCEntitySpawner_enableAndSpawn (streaming-grid activation)
    var SPAWNER_PARENT_OFF     = 0x08;         // spawner.+0x08 = parent oCEntity*
    var SPAWNER_FLAGS_OFF      = 0x64;         // spawner.+0x64 byte; bit 3 = consumed
    var SPAWNER_CONSUMED_BIT   = 0x08;
    var SPAWNER_ACTIVE_OFF     = 0x168;        // spawner.+0x168 byte = active flag
    var SPAWNER_ENABLE_OFF     = 0x169;        // spawner.+0x169 byte = enable / replicated-active flag
    var SPAWNER_CHILDREN_OFF   = 0x210;        // spawner.+0x210 = child entity ptr array
    var SPAWNER_CHILD_COUNT    = 0x218;        // spawner.+0x218 = u32 count
    var ENTITY_SETTINGS_OFF    = 0x28;         // entity.+0x28 = oCEntitySettings*
    var ENTITY_POS_OFF         = 0x324;        // entity.+0x324 = world position xyz
    var SETPOS_VT_SLOT         = 0x50;         // entity.vtable[+0x50] = oCEntity::setPosition
    var SETTINGS_NAME_PTR_OFF  = 0x08;
    var SETTINGS_NAME_LEN_OFF  = 0x10;
    var HOURGLASS_PARENT_NAME  = "NoModel+2Cpnt";
    var HOURGLASS_DEFAULT_DX   = 2;
    var HOURGLASS_DEFAULT_DY   = 0;
    var HOURGLASS_DEFAULT_DZ   = 0;

    if (!RW.Summon) RW.Summon = {};
    var Summon = RW.Summon;
    Summon._spawners  = Summon._spawners  || [];   // every captured spawner
    Summon._hourglass = Summon._hourglass || null; // resolved lazily
    Summon._hooks     = Summon._hooks     || [];

    // Re-load safety: detach prior hooks. Captures persist across re-loads.
    Summon._hooks.forEach(function (h) { try { h.detach(); } catch (e) {} });
    Summon._hooks = [];

    var fireFn = new NativeFunction(
        IMG.add(BROADCAST_FIRE_RVA),
        'void',
        ['pointer']
    );
    var enableAndSpawnFn = new NativeFunction(
        IMG.add(ENABLE_AND_SPAWN_RVA),
        'void',
        ['pointer']
    );

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

    function readParentName(sp) {
        try {
            var parent = sp.add(SPAWNER_PARENT_OFF).readPointer();
            if (!parent || parent.isNull()) return null;
            if (parent.toString() === '0xffffffffffffffff') return null;
            var pSettings = parent.add(ENTITY_SETTINGS_OFF).readPointer();
            if (!pSettings || pSettings.isNull()) return null;
            return readSettingsName(pSettings);
        } catch (e) { return null; }
    }

    function isConsumed(sp) {
        try {
            return (sp.add(SPAWNER_FLAGS_OFF).readU8() & SPAWNER_CONSUMED_BIT) !== 0;
        } catch (e) { return true; }
    }

    // Lazy-resolve the hourglass spawner-component by parent-name substring.
    function resolveHourglass() {
        if (Summon._hourglass) return true;
        var key = HOURGLASS_PARENT_NAME.toLowerCase();
        for (var i = 0; i < Summon._spawners.length; i++) {
            var sp = Summon._spawners[i];
            var pName = readParentName(sp);
            if (!pName) continue;
            if (pName.toLowerCase().indexOf(key) >= 0) {
                Summon._hourglass = sp;
                return true;
            }
        }
        return false;
    }

    // Set position on any oCEntity via vtable[10] (setPosition).
    function setEntityPos(entity, x, y, z) {
        var vt = entity.readPointer();
        var fn = new NativeFunction(
            vt.add(SETPOS_VT_SLOT).readPointer(),
            'void',
            ['pointer', 'pointer']
        );
        var buf = Memory.alloc(12);
        buf.writeFloat(x);
        buf.add(4).writeFloat(y);
        buf.add(8).writeFloat(z);
        fn(entity, buf);
    }

    // Capture every spawner-component instance at ctor time.
    Summon._hooks.push(Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
        onEnter: function (args) {
            try { Summon._spawners.push(ptr(args[0])); }
            catch (e) {}
        }
    }));

    /*
     * ----------------------------------------------------------------
     * Summon.status(): void
     *
     * Print capture count. Useful between chapter load and first fire
     * to verify the ctor hook armed in time.
     * ----------------------------------------------------------------
     */
    Summon.status = function () {
        console.log("[Summon] " + Summon._spawners.length + " spawners captured");
    };

    /*
     * ----------------------------------------------------------------
     * Summon.list(filter?: string, limit?: number): void
     *
     * List unique parent names across captured spawners with hit
     * counts. Skip spawners with no bound parent (still in mid-attach).
     * Sorted by count descending.
     *
     * Usage:
     *   Summon.list()              // top 100 by count
     *   Summon.list("Enemy Camp")  // names containing "Enemy Camp"
     *   Summon.list("", 30)        // top 30 across all
     *
     * Result: prints "  NAME (count)" per line, then summary.
     * ----------------------------------------------------------------
     */
    Summon.list = function (filter, limit) {
        var f = (filter || "").toLowerCase();
        var lim = (typeof limit === 'number') ? limit : 100;
        var counts = {};
        var noParent = 0;
        for (var i = 0; i < Summon._spawners.length; i++) {
            var pName = readParentName(Summon._spawners[i]);
            if (!pName) { noParent++; continue; }
            counts[pName] = (counts[pName] || 0) + 1;
        }
        var entries = [];
        Object.keys(counts).forEach(function (name) {
            if (!f || name.toLowerCase().indexOf(f) >= 0) {
                entries.push([name, counts[name]]);
            }
        });
        entries.sort(function (a, b) { return b[1] - a[1]; });
        var n = Math.min(entries.length, lim);
        for (var j = 0; j < n; j++) {
            console.log("  " + entries[j][0] + " (" + entries[j][1] + ")");
        }
        console.log("[Summon.list] " + entries.length +
                    " unique name(s) from " + Summon._spawners.length +
                    " spawners (" + noParent + " no parent yet" +
                    (entries.length > n ? ", showing top " + n : "") + ")");
    };

    /*
     * ----------------------------------------------------------------
     * Summon.fire(parentNameSubstring: string, index?: number): NativePointer | null
     *
     * Find the Nth un-fired spawner whose parent.settings name contains
     * the substring (case-insensitive), then fire its broadcast worker.
     * Returns the spawner pointer on success, null on no-match or fire-
     * failure.
     *
     * Usage:
     *   Summon.fire("Enemy Camp")               // first un-fired match
     *   Summon.fire("Enemy Camp", 2)            // 3rd un-fired match
     *   Summon.fire("Cauldron", 0)              // cauldron sub-spawner 0
     *   Summon.fire("NoModel+2Cpnt")            // hourglass equivalent
     *
     * Result:
     *   Engine processes the spawn. The new entity is appended to
     *   spawner.+0x210 (count at +0x218); read it via Summon.lastChild.
     *   The new entity appears at the spawner's bound transform —
     *   typically the camp anchor / hourglass position / etc.
     *
     * Caveats:
     *   - Skips consumed spawners (bit 3 of +0x64 set).
     *   - Output entity type is whatever the engine pre-bound at chapter
     *     init; we don't choose by name here.
     *   - For position-near-player, warp the spawner's parent first via
     *     Transporter.warpEntity(parentName, x, y, z) before firing.
     * ----------------------------------------------------------------
     */
    Summon.fire = function (parentNameSubstring, index) {
        if (typeof parentNameSubstring !== 'string') {
            console.log("[Summon.fire] need (parentNameSubstring, index?)");
            return null;
        }
        var key = parentNameSubstring.toLowerCase();
        var idx = (typeof index === 'number') ? index : 0;
        var matched = -1;
        for (var i = 0; i < Summon._spawners.length; i++) {
            var sp = Summon._spawners[i];
            if (isConsumed(sp)) continue;
            var pName = readParentName(sp);
            if (!pName) continue;
            if (pName.toLowerCase().indexOf(key) < 0) continue;
            matched++;
            if (matched !== idx) continue;
            try {
                fireFn(sp);
                console.log("[Summon.fire] " + pName + " (#" + idx +
                            ", spawner=" + sp + ") -> fired");
                return sp;
            } catch (e) {
                console.log("[Summon.fire] threw: " + e.message);
                return null;
            }
        }
        console.log("[Summon.fire] no un-fired match for \"" +
                    parentNameSubstring + "\" (index " + idx + ")");
        return null;
    };

    /*
     * ----------------------------------------------------------------
     * Summon.fireAtHourglass(parentNameSubstring: string, index?: number,
     *                       dx?: number, dy?: number, dz?: number): NativePointer | null
     *
     * Like Summon.fire, but warps the matched spawner's parent entity
     * to the hourglass's position + (dx, dy, dz) BEFORE firing. Default
     * offset is (+2, 0, 0). The new entity then spawns at that
     * relocated transform — visible right next to the hourglass.
     *
     * Usage:
     *   Summon.fireAtHourglass("Enemy Camp")             // first match, +2x
     *   Summon.fireAtHourglass("Enemy Camp", 0, 5, 0, 0) // 5 units +x
     *   Summon.fireAtHourglass("Ghoul Enemy Camp", 1)    // 2nd match
     *
     * Result:
     *   Spawner's parent oCEntity is repositioned, broadcast worker
     *   fires, child appears at the new transform. Returns spawner ptr.
     *
     * Caveats:
     *   - The parent stays warped after this call. If you re-fire the
     *     same spawner later it'll spawn at the same warped spot, not
     *     its original camp anchor.
     *   - Same un-fired-only / pre-bound-output / consumed-bit caveats
     *     as Summon.fire.
     * ----------------------------------------------------------------
     */
    Summon.fireAtHourglass = function (parentNameSubstring, index, dx, dy, dz) {
        if (typeof parentNameSubstring !== 'string') {
            console.log("[Summon.fireAtHourglass] need (parentNameSubstring, index?, dx?, dy?, dz?)");
            return null;
        }
        if (!resolveHourglass()) {
            console.log("[Summon.fireAtHourglass] no hourglass found in " +
                        Summon._spawners.length + " captured spawners");
            return null;
        }
        if (typeof dx !== 'number') dx = HOURGLASS_DEFAULT_DX;
        if (typeof dy !== 'number') dy = HOURGLASS_DEFAULT_DY;
        if (typeof dz !== 'number') dz = HOURGLASS_DEFAULT_DZ;

        // Read hourglass parent position
        var hgParent;
        try {
            hgParent = Summon._hourglass.add(SPAWNER_PARENT_OFF).readPointer();
        } catch (e) { hgParent = null; }
        if (!hgParent || hgParent.isNull()) {
            console.log("[Summon.fireAtHourglass] hourglass parent unbound");
            return null;
        }
        var pos = hgParent.add(ENTITY_POS_OFF);
        var hx = pos.readFloat();
        var hy = pos.add(4).readFloat();
        var hz = pos.add(8).readFloat();
        var tx = hx + dx, ty = hy + dy, tz = hz + dz;

        // Find Nth un-fired matching spawner
        var key = parentNameSubstring.toLowerCase();
        var idx = (typeof index === 'number') ? index : 0;
        var matched = -1;
        for (var i = 0; i < Summon._spawners.length; i++) {
            var sp = Summon._spawners[i];
            if (isConsumed(sp)) continue;
            var pName = readParentName(sp);
            if (!pName) continue;
            if (pName.toLowerCase().indexOf(key) < 0) continue;
            matched++;
            if (matched !== idx) continue;

            try {
                var spParent = sp.add(SPAWNER_PARENT_OFF).readPointer();
                if (spParent.isNull()) {
                    console.log("[Summon.fireAtHourglass] match has unbound parent");
                    return null;
                }
                // 1. Warp the parent to the chosen spot.
                setEntityPos(spParent, tx, ty, tz);
                // 2. Fire via enableAndSpawn — the engine entry point for
                //    streaming-grid activation. Should handle dormant-state
                //    setup that the bare broadcast worker doesn't.
                enableAndSpawnFn(sp);
                console.log("[Summon.fireAtHourglass] " + pName + " (#" + idx +
                            ") parent warped to (" + tx.toFixed(2) + "," +
                            ty.toFixed(2) + "," + tz.toFixed(2) +
                            "), enableAndSpawn fired");
                return sp;
            } catch (e) {
                console.log("[Summon.fireAtHourglass] threw: " + e.message);
                return null;
            }
        }
        console.log("[Summon.fireAtHourglass] no un-fired match for \"" +
                    parentNameSubstring + "\" (index " + idx + ")");
        return null;
    };

    /*
     * ----------------------------------------------------------------
     * Summon.lastChild(spawner: NativePointer): NativePointer | null
     *
     * Read the most-recent spawned child entity from the spawner's
     * +0x210 array (count at +0x218). The broadcast worker writes here
     * after firing.
     *
     * Usage:
     *   var sp = Summon.fire("Enemy Camp");
     *   var child = Summon.lastChild(sp);
     *
     * Returns null if the count is zero (nothing fired yet) or on read
     * error.
     * ----------------------------------------------------------------
     */
    Summon.lastChild = function (spawner) {
        try {
            var count = spawner.add(SPAWNER_CHILD_COUNT).readU32();
            if (count === 0) return null;
            var arr = spawner.add(SPAWNER_CHILDREN_OFF).readPointer();
            if (arr.isNull()) return null;
            return arr.add((count - 1) * 8).readPointer();
        } catch (e) {
            console.log("[Summon.lastChild] threw: " + e.message);
            return null;
        }
    };

    RW.registerMod("mod:poc_summon_enemy", version);
    console.log("[Summon] " + version + " loaded.");
    console.log("[Summon]   status()                                       — capture count");
    console.log("[Summon]   list(filter?, limit?)                          — parent names");
    console.log("[Summon]   fire(name, index?)                             — fire at spawner's position");
    console.log("[Summon]   fireAtHourglass(name, index?, dx?, dy?, dz?)   — warp + fire near hourglass");
    console.log("[Summon]   lastChild(spawner)                             — most-recent spawn");
})();

// Top-level alias for REPL convenience
var Summon = RW.Summon;
