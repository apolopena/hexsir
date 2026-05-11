// ARCHIVED — direct-factory approach abandoned 2026-05-10.
//
// Calling oCSpawner_createEntityFromSettings (RVA 0x6db260) directly with a
// hand-built oCEntitySpawnData accumulated three crashes (0x338, 0x10, then
// 0xffffffffffffffff) as each fix uncovered another missing piece of state
// that the engine's natural-fire wrapper layers (fireSpawnWithBroadcast →
// dispatchSpawn → allocateAndRegisterChild → factory) populate before
// reaching the factory. Static analysis alone wasn't enough to reverse-
// engineer the full required setup. Resolving would need WinDbg to trace a
// real spawn and dump exact arg state at the factory call site.
//
// Superseded by tools/frida/mods/poc_summon_enemy.js, which uses the
// proven broadcast-worker approach (FUN_1406f62b0) on pre-bound in-world
// spawners — same pattern as Hourglass.spawnItem() and spawner_probe.js
// v0.12.0.
//
// Kept for reference: this file already establishes the chapter-wide
// name -> oCEntitySettings* capture pattern, the +0x10 settings-binding
// correction (vs. doc's +0x18), and the resolveChapterSubobj walker.
//
// =============================================================================
//
// poc_ghoul_spawn.js — proof-of-concept: spawn an arbitrary entity at a
// chosen position via the engine's universal entity factory.
//
// Mechanism: oCSpawner_createEntityFromSettings (RVA 0x6db260) is the
// solo/canonical entity factory the engine uses for level-load Bark
// spawn and (transitively) every spawner-component fire. It accepts
// any oCEntitySettings* and produces a fully-constructed oCEntity at
// the position encoded in spawnData. We invoke it directly, using the
// chapter hourglass spawner-component as the host for the embedded
// oCSpawner sub-object at +0x68. No reward/MO/hourglass-specific
// wiring is touched.
//
// Bootstrap: hooks fire automatically during chapter setup, no user
// action required beyond loading the chapter:
//   - oCEntity::ctor             -> name -> oCEntitySettings* map
//   - oCEntityCpntEntitySpawner  -> hourglass spawner-component address
// oCEntitySpawnData::vftable address is hardcoded from a static
// disassembly of hero_inventory_create_magical_object.
//
// Caveats:
//   - Asset streaming finishes filling in mesh/AI/components 1-2 frames
//     after the call; entity is spawn-and-positioned synchronously.
//   - Multiplayer untested. Host-side calls SHOULD replicate via the
//     same world-binder natural spawns use, but spawnData's listener
//     block is zeroed (vs. populated for natural spawns). Peer-side
//     calls likely produce local-only entities.
//   - Map covers only entities whose oCEntity::ctor fires during
//     chapter load. Proximity-gated spawns (pigs, ghosts, wolves)
//     don't ctor at chapter start and won't appear in Ghoul.list().
//
// Depends on:
//   - rw_lab.js (RW.* hub)
//
// REPL surface (after loadMod("poc_ghoul_spawn")):
//   Ghoul.status(): void
//   Ghoul.list(filter?: string): void
//   Ghoul.spawn(name: string, x: number, y: number, z: number): NativePointer | null
//   Ghoul.spawnAtHourglass(name: string, dx?: number, dy?: number, dz?: number): NativePointer | null

(function () {
    var version = "0.3.0";
    if (typeof RW !== "object") {
        console.log("[Ghoul] FATAL: RW missing — load rw_lab.js first");
        return;
    }
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Ghoul] FATAL: no Ravenswatch.exe"); return; }
    var IMG = mod.base;

    // Domain vocabulary — every offset/RVA names a field on the engine
    // entity factory pipeline. Cross-references:
    //   rw/findings/entity-spawner-mechanism.md
    //   rw/findings/hourglass-arbitrary-spawn.md (in chat — not committed)
    var ENTITY_CTOR_RVA          = 0x6c96f0;   // oCEntity::ctor
    var SPAWNER_CTOR_RVA         = 0x2d0ee0;   // oCEntityCpntEntitySpawner_ctor
    var CREATE_ENTITY_RVA        = 0x6db260;   // oCSpawner_createEntityFromSettings
    var GET_CHAPTER_SUBOBJ_RVA   = 0x713c30;   // chapter master oCSpawner sub-object getter (no-arg)
    var SPAWNDATA_VTABLE_RVA     = 0xef6400;   // oCEntitySpawnData::vftable
    var SPAWNER_PARENT_OFF       = 0x08;       // spawner.+0x08 = parent oCEntity*
    var ENTITY_SETTINGS_OFF      = 0x28;       // entity.+0x28 = oCEntitySettings*
    var SETTINGS_NAME_PTR_OFF    = 0x08;       // settings.+0x08 = char*
    var SETTINGS_NAME_LEN_OFF    = 0x10;       // settings.+0x10 = u32 length
    var SPAWNDATA_SIZE           = 0x68;
    var SPAWNDATA_POS_OFF        = 0x10;       // position xyz at spawnData.+0x10
    var SPAWNDATA_ROT_OFF        = 0x1c;       // rotation quat (x,y,z,w) at spawnData.+0x1c..+0x2b
    var SPAWNDATA_ROT_W_OFF      = 0x28;       // quat w (must be 1.0 for identity, 0 = degenerate)
    var SPAWNDATA_SCALE_OFF      = 0x2c;       // scale xyz at spawnData.+0x2c (defaults to 1,1,1)
    var ENTITY_POS_OFF           = 0x324;      // entity.+0x324 = world position xyz
    var HOURGLASS_PARENT_NAME    = "NoModel+2Cpnt";
    var HOURGLASS_DEFAULT_DX     = 2;          // default offset along +X (~"in front")
    var HOURGLASS_DEFAULT_DY     = 0;
    var HOURGLASS_DEFAULT_DZ     = 0;

    if (!RW.Ghoul) RW.Ghoul = {};
    var Ghoul = RW.Ghoul;
    Ghoul._settingsByName = Ghoul._settingsByName || {};   // name -> oCEntitySettings*
    Ghoul._spawners       = Ghoul._spawners       || [];   // every captured spawner-component
    Ghoul._hourglass      = Ghoul._hourglass      || null; // resolved lazily on first spawn call
    Ghoul._chapterSubobj  = Ghoul._chapterSubobj  || null; // chapter scene oCSpawner sub-object
    Ghoul._hooks          = Ghoul._hooks          || [];

    // Re-load safety: detach prior hooks before re-arming. Captured state
    // persists so an edit-and-loadMod cycle doesn't lose the working set.
    Ghoul._hooks.forEach(function (h) { try { h.detach(); } catch (e) {} });
    Ghoul._hooks = [];

    var createEntity = new NativeFunction(
        IMG.add(CREATE_ENTITY_RVA),
        'pointer',
        ['pointer', 'pointer', 'pointer', 'pointer']
    );
    var getChapterSubobj = new NativeFunction(
        IMG.add(GET_CHAPTER_SUBOBJ_RVA),
        'pointer',
        ['pointer']    // takes the spawner-component as `this`
    );
    var spawnDataVT = IMG.add(SPAWNDATA_VTABLE_RVA);

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

    // Capture #1 — every entity's settings at ctor.
    Ghoul._hooks.push(Interceptor.attach(IMG.add(ENTITY_CTOR_RVA), {
        onEnter: function (args) {
            try {
                var settings = ptr(args[1]);
                var name = readSettingsName(settings);
                if (name && !Ghoul._settingsByName[name]) {
                    Ghoul._settingsByName[name] = settings;
                }
            } catch (e) {}
        }
    }));

    // Capture #2 — every spawner-component instance. Parent pointer at
    // spawner.+0x08 isn't set during ctor — it's bound later by
    // oCEntitySpawner_onAttachToParent. So we store all pointers here
    // and identify the hourglass lazily at use-time (resolveHourglass).
    Ghoul._hooks.push(Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
        onEnter: function (args) {
            try { Ghoul._spawners.push(ptr(args[0])); }
            catch (e) {}
        }
    }));

    // oCSpawner_getChapterContext(sp) returns either the chapter scene's
    // spawner sub-object (the wired one we want) OR the spawner-component's
    // own +0x68 (which has uninitialized child-list fields). Pick a
    // spawner whose settings flags route to the chapter sub-object branch
    // by checking that the returned ptr != sp + 0x68. Cache the result.
    function resolveChapterSubobj() {
        if (Ghoul._chapterSubobj) return true;
        for (var i = 0; i < Ghoul._spawners.length; i++) {
            var sp = Ghoul._spawners[i];
            try {
                var r = getChapterSubobj(sp);
                if (!r || r.isNull()) continue;
                if (r.toString() === '0xffffffffffffffff') continue;
                if (r.equals(sp.add(0x68))) continue;   // own sub-object — skip
                Ghoul._chapterSubobj = r;
                console.log("[Ghoul] chapter sub-object @ " + r +
                            "  (resolved via spawner #" + i + ")");
                return true;
            } catch (e) {}
        }
        console.log("[Ghoul] resolveChapterSubobj: no spawner routed to " +
                    "the chapter scene sub-object out of " +
                    Ghoul._spawners.length + " captured");
        return false;
    }

    function readSpawnerParentName(sp) {
        try {
            var parent = sp.add(SPAWNER_PARENT_OFF).readPointer();
            if (!parent || parent.isNull()) return null;
            if (parent.toString() === '0xffffffffffffffff') return null;
            var pSettings = parent.add(ENTITY_SETTINGS_OFF).readPointer();
            if (!pSettings || pSettings.isNull()) return null;
            return readSettingsName(pSettings);
        } catch (e) { return null; }
    }

    // Walk captured spawners, find the one whose parent.settings name
    // matches the hourglass via case-insensitive substring. Caches
    // result on Ghoul._hourglass.
    function resolveHourglass() {
        if (Ghoul._hourglass) return true;
        var key = HOURGLASS_PARENT_NAME.toLowerCase();
        var withParents = 0;
        for (var i = 0; i < Ghoul._spawners.length; i++) {
            var sp = Ghoul._spawners[i];
            var pName = readSpawnerParentName(sp);
            if (!pName) continue;
            withParents++;
            if (pName.toLowerCase().indexOf(key) >= 0) {
                Ghoul._hourglass = sp;
                console.log("[Ghoul] hourglass @ " + sp +
                            "  parent=\"" + pName + "\"" +
                            "  (resolved from " + Ghoul._spawners.length +
                            " spawners, " + withParents + " with parents)");
                return true;
            }
        }
        console.log("[Ghoul] resolveHourglass: 0/" + Ghoul._spawners.length +
                    " match \"" + HOURGLASS_PARENT_NAME + "\"" +
                    " (" + withParents + " had bound parents)");
        return false;
    }

    /*
     * ----------------------------------------------------------------
     * Ghoul.status(): void
     *
     * Print capture state: number of name->settings entries, hourglass
     * pointer, hardcoded spawnData::vftable address. Useful between
     * chapter load and first spawn() call to verify both captures armed.
     *
     * Result: prints one line. Never fails.
     * ----------------------------------------------------------------
     */
    Ghoul.status = function () {
        resolveHourglass();
        var n = Object.keys(Ghoul._settingsByName).length;
        console.log("[Ghoul] settingsByName=" + n + " entries" +
                    "  spawners=" + Ghoul._spawners.length +
                    "  hourglass=" + Ghoul._hourglass +
                    "  spawnDataVT=" + spawnDataVT + " (hardcoded)");
    };

    /*
     * ----------------------------------------------------------------
     * Ghoul.list(filter?: string): void
     *
     * List captured asset names, optionally filtered by case-insensitive
     * substring. Use to discover spawnable templates after chapter load.
     *
     * Usage:
     *   Ghoul.list()           // every captured name (likely > 1000)
     *   Ghoul.list("ghoul")    // names containing "ghoul"
     *   Ghoul.list("Elite_")   // names containing "Elite_"
     *
     * Result: prints one name per line, then a count.
     * Caveats: only entities whose oCEntity::ctor has fired during this
     *   session are listed. Proximity-gated spawns (pigs, ghosts) won't
     *   appear until you walk into their cell.
     * ----------------------------------------------------------------
     */
    /*
     * ----------------------------------------------------------------
     * Ghoul.dumpParents(filter?: string, limit?: number): void
     *
     * List unique parent.settings names across all captured spawners,
     * with hit counts. Use to discover the actual hourglass parent name
     * when the default HOURGLASS_PARENT_NAME doesn't match this build.
     *
     * Usage:
     *   Ghoul.dumpParents()              // every unique parent name
     *   Ghoul.dumpParents("hour")        // names containing "hour"
     *   Ghoul.dumpParents("", 30)        // first 30 (sorted by count desc)
     *
     * Result: prints one line per name, "NAME (count)".
     * ----------------------------------------------------------------
     */
    Ghoul.dumpParents = function (filter, limit) {
        var f = (filter || "").toLowerCase();
        var lim = (typeof limit === 'number') ? limit : 100;
        var counts = {};
        var noParent = 0;
        for (var i = 0; i < Ghoul._spawners.length; i++) {
            var pName = readSpawnerParentName(Ghoul._spawners[i]);
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
        console.log("[Ghoul.dumpParents] " + entries.length +
                    " unique name(s)" +
                    " from " + Ghoul._spawners.length + " spawners" +
                    " (" + noParent + " no parent yet" +
                    (entries.length > n ? ", showing top " + n : "") + ")");
    };

    Ghoul.list = function (filter) {
        var f = (filter || "").toLowerCase();
        var hits = [];
        Object.keys(Ghoul._settingsByName).forEach(function (name) {
            if (!f || name.toLowerCase().indexOf(f) >= 0) hits.push(name);
        });
        hits.sort();
        hits.forEach(function (n) { console.log("  " + n); });
        console.log("[Ghoul] " + hits.length + " match(es)");
    };

    /*
     * ----------------------------------------------------------------
     * Ghoul.spawn(name: string, x: number, y: number, z: number): NativePointer | null
     *
     * Spawn the named entity at world position (x, y, z) via the
     * engine's universal entity factory. Returns the new oCEntity
     * pointer on success, null on failure (with a diagnostic log line).
     *
     * Usage:
     *   Ghoul.spawn("Festering_Ghoul", 0, 2, 0)
     *   var p = RW.Player.entity.add(0x324);
     *   Ghoul.spawn("Festering_Ghoul", p.readFloat(),
     *               p.add(4).readFloat(), p.add(8).readFloat())
     *
     * Result:
     *   New entity is constructed, registered in the chapter scene,
     *   positioned at (x, y, z). Mesh/AI/components finish over the
     *   next 1-2 frames asynchronously.
     *
     * Caveats:
     *   - Name must be in the captured set (see Ghoul.list).
     *   - Hourglass spawner-component must have been captured (loaded
     *     this mod BEFORE chapter setup).
     *   - MP behavior untested. Host-side calls likely replicate; peer-
     *     side calls likely produce local-only entities.
     *   - Spawning a boss / quest-flagged entity may interact with quest
     *     state. Stick to standard enemies for first proofs.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   1. Look up settings by name in Ghoul._settingsByName
     *      (populated by oCEntity::ctor hook).
     *   2. Build oCEntitySpawnData (0x68 bytes) on Memory.alloc:
     *        +0x00 vtable = IMG + 0xef6400 (hardcoded — see file header)
     *        +0x10 position xyz = (x, y, z)
     *        +0x2c scale xyz = (1, 1, 1)
     *        rest zero (rotation identity, parent NULL, IDs/flags zero)
     *   3. Get oCSpawner sub-object from hourglass.+0x68.
     *   4. Call oCSpawner_createEntityFromSettings(subobj, settings,
     *      spawnData, NULL). Internally:
     *        - oCSpawnablePool_allocateNode(settings + 0x18) allocates
     *          and ctors the new oCEntity.
     *        - subobj.vtable[3] = oCSpawner_addEntityIntoWorld registers
     *          the entity in the chapter scene and calls
     *          entity.vtable[5] = entity_init_from_config_block(entity,
     *          spawnData) which consumes the spawnData and applies
     *          position/rotation/scale.
     */
    Ghoul.spawn = function (name, x, y, z) {
        if (typeof name !== 'string') {
            console.log("[Ghoul.spawn] need (name, x, y, z)");
            return null;
        }
        var settings = Ghoul._settingsByName[name];
        if (!settings) {
            console.log("[Ghoul.spawn] no settings for \"" + name +
                        "\" — try Ghoul.list(\"" + name + "\")");
            return null;
        }
        if (!resolveHourglass()) {
            console.log("[Ghoul.spawn] no hourglass found in " +
                        Ghoul._spawners.length + " captured spawners — " +
                        "load this mod BEFORE chapter setup, then reload");
            return null;
        }
        if (typeof x !== 'number' || typeof y !== 'number' ||
            typeof z !== 'number') {
            console.log("[Ghoul.spawn] need (name, x, y, z) numbers");
            return null;
        }

        var sd = Memory.alloc(SPAWNDATA_SIZE);
        sd.writePointer(spawnDataVT);
        sd.add(SPAWNDATA_POS_OFF     ).writeFloat(x);
        sd.add(SPAWNDATA_POS_OFF +  4).writeFloat(y);
        sd.add(SPAWNDATA_POS_OFF +  8).writeFloat(z);
        // Rotation as identity quaternion (x=0, y=0, z=0, w=1).
        // x,y,z already zero from Memory.alloc; only w needs writing.
        sd.add(SPAWNDATA_ROT_W_OFF    ).writeFloat(1.0);
        sd.add(SPAWNDATA_SCALE_OFF    ).writeFloat(1.0);
        sd.add(SPAWNDATA_SCALE_OFF + 4).writeFloat(1.0);
        sd.add(SPAWNDATA_SCALE_OFF + 8).writeFloat(1.0);

        if (!resolveChapterSubobj()) {
            console.log("[Ghoul.spawn] no chapter sub-object resolvable");
            return null;
        }
        var newEntity = createEntity(Ghoul._chapterSubobj, settings, sd, NULL);
        console.log("[Ghoul.spawn] " + name + " -> " + newEntity +
                    " @ (" + x.toFixed(2) + "," + y.toFixed(2) + "," +
                    z.toFixed(2) + ")");
        return newEntity;
    };

    /*
     * ----------------------------------------------------------------
     * Ghoul.spawnAtHourglass(name: string, dx?: number, dy?: number, dz?: number): NativePointer | null
     *
     * Spawn the named entity at the hourglass's world position plus an
     * offset. Default offset is (+2, 0, 0) — two units along world +X,
     * a rough proxy for "in front of the hourglass" without doing
     * rotation math.
     *
     * Usage:
     *   Ghoul.spawnAtHourglass("Festering_Ghoul")           // +X by 2
     *   Ghoul.spawnAtHourglass("Festering_Ghoul", 5)        // +X by 5
     *   Ghoul.spawnAtHourglass("Festering_Ghoul", 0, 0, 3)  // +Z by 3
     *
     * Result:
     *   New entity at (hourglass.x+dx, hourglass.y+dy, hourglass.z+dz).
     *   Returns the new oCEntity pointer, or null on failure (with a
     *   diagnostic log line).
     *
     * Caveats:
     *   - "In front" via +X is approximate; the hourglass model has its
     *     own facing direction. For true forward-relative offset you
     *     would need to read the hourglass quaternion at parent+0x308
     *     and rotate the offset.
     *   - Same name-resolution and hourglass-capture prerequisites as
     *     Ghoul.spawn — see that method's caveats.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads hourglass parent ptr from spawner.+0x08, reads world
     *   position from parent.+0x324..+0x32c, applies offset, delegates
     *   to Ghoul.spawn(name, x, y, z).
     */
    Ghoul.spawnAtHourglass = function (name, dx, dy, dz) {
        if (!resolveHourglass()) {
            console.log("[Ghoul.spawnAtHourglass] no hourglass found in " +
                        Ghoul._spawners.length + " captured spawners — " +
                        "load this mod BEFORE chapter setup, then reload");
            return null;
        }
        if (typeof dx !== 'number') dx = HOURGLASS_DEFAULT_DX;
        if (typeof dy !== 'number') dy = HOURGLASS_DEFAULT_DY;
        if (typeof dz !== 'number') dz = HOURGLASS_DEFAULT_DZ;
        try {
            var parent = Ghoul._hourglass.add(SPAWNER_PARENT_OFF).readPointer();
            if (parent.isNull()) {
                console.log("[Ghoul.spawnAtHourglass] hourglass parent is null");
                return null;
            }
            var p = parent.add(ENTITY_POS_OFF);
            var hx = p.readFloat();
            var hy = p.add(4).readFloat();
            var hz = p.add(8).readFloat();
            return Ghoul.spawn(name, hx + dx, hy + dy, hz + dz);
        } catch (e) {
            console.log("[Ghoul.spawnAtHourglass] threw: " + e.message);
            return null;
        }
    };

    RW.registerMod("mod:poc_ghoul_spawn", version);
    console.log("[Ghoul] " + version + " loaded.");
    console.log("[Ghoul]   status()                            — capture state");
    console.log("[Ghoul]   list(filter?)                       — list captured names");
    console.log("[Ghoul]   spawn(name, x, y, z)                — spawn at coords");
    console.log("[Ghoul]   spawnAtHourglass(name, dx?, dy?, dz?)  — spawn near hourglass (default +2x)");
})();

// Top-level alias for REPL convenience
var Ghoul = RW.Ghoul;
