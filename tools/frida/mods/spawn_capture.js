// spawn_capture.js — capture every oCEntity creation during a window.
//
// Hooks the oCEntity constructor at RVA 0x6c96f0 (FUN_1406c96f0). Every
// oCEntity-derived class's constructor chains through this — so this
// hook fires exactly once per entity creation across all subclasses
// (pigs, ghouls, barriers, props, anything inheriting oCEntity).
//
// Verified via Ghidra decompile 2026-05-06: function sets parent
// oCSpawnable::vftable then later overrides with oCEntity::vftable,
// initializes ~200 fields. Two distinct writes of vtable RVA 0xf4cc40
// at 0x1406c987b and 0x1406c9882 — both inside this function.
//
// Args:
//   param_1 (args[0]): the entity buffer being constructed
//   param_2 (args[1]): construction-time init parameter (stored at +0x28)
//
// State at onLeave:
//   - oCEntity::vftable is installed (vtable[0] = 0xf4cc40)
//   - But DERIVED class constructors haven't run yet — final RTTI,
//     position, and component map aren't populated
//
// Strategy: capture the entity address at hook time. Read state
// (vtable, RTTI, position) lazily at dump time when entities are
// fully constructed.
//
// Usage:
//   loadMod("spawn_capture")
//   SpawnCapture.start()
//   <activate the cauldron / approach the camp / etc.>
//   SpawnCapture.stop()
//   SpawnCapture.dump()        // raw view: every entity, grouped by RTTI
//   SpawnCapture.analyze()     // smart view: filtered + grouped by template
//                              //   + component class names per group

(function () {
    var version = "0.5.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[SpawnCapture] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;
    var imageEnd  = imageBase.add(mod.size);

    var ENTITY_CTOR_RVA = 0x6c96f0;
    var ENTITY_POS_OFF  = 0x324;

    if (!RW.SpawnCapture) RW.SpawnCapture = {};
    var SpawnCapture = RW.SpawnCapture;

    if (SpawnCapture._hook) { try { SpawnCapture._hook.detach(); } catch (e) {} }
    SpawnCapture._hook = null;
    SpawnCapture._captures = SpawnCapture._captures || [];

    function readF32(p) { try { return p.readFloat(); } catch (e) { return NaN; } }
    function vec3(p) { return [readF32(p), readF32(p.add(4)), readF32(p.add(8))]; }
    function v3str(v) { return "(" + v[0].toFixed(2) + "," + v[1].toFixed(2) + "," + v[2].toFixed(2) + ")"; }
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
    function vtRva(obj) {
        try {
            var vt = obj.readPointer();
            if (vt.compare(imageBase) >= 0 && vt.compare(imageEnd) < 0) {
                return vt.sub(imageBase).toInt32();
            }
        } catch (e) {}
        return -1;
    }

    SpawnCapture.start = function () {
        SpawnCapture._captures = [];
        if (SpawnCapture._hook) { try { SpawnCapture._hook.detach(); } catch (e) {} }
        SpawnCapture._hook = Interceptor.attach(imageBase.add(ENTITY_CTOR_RVA), {
            onEnter: function (args) {
                try {
                    this._entity  = ptr(args[0]);
                    this._initArg = ptr(args[1]);
                    this._ts      = Date.now();
                } catch (e) { this._entity = null; }
            },
            onLeave: function () {
                if (!this._entity) return;
                SpawnCapture._captures.push({
                    ts: this._ts,
                    entity: this._entity,
                    initArg: this._initArg,
                });
            },
        });
        console.log("[SpawnCapture] armed at oCEntity constructor (RVA 0x" + ENTITY_CTOR_RVA.toString(16) + ")");
    };

    SpawnCapture.stop = function () {
        if (SpawnCapture._hook) { try { SpawnCapture._hook.detach(); } catch (e) {} }
        SpawnCapture._hook = null;
        console.log("[SpawnCapture] detached. " + SpawnCapture._captures.length + " entities captured");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnCapture.dump(): void
     *
     * Print every captured entity (one line each) grouped by RTTI
     * class name. Each entry shows entity address, vtable RVA, current
     * world position, and the construction-time initArg. Raw view —
     * useful for the full firehose.
     *
     * Run after entities have fully constructed (i.e., after stop()
     * and a moment for the engine to finalize component setup).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   For each capture, reads vtable from entity[0], RTTI via the
     *   COL pointer at vtable[-1], position from entity+0x324. In
     *   Ravenswatch's pure-ECS architecture, every entity is base
     *   oCEntity (vtRva 0xf4cc40) — what differentiates a "pig" from a
     *   "barrier" is the components attached, not the class. Use
     *   analyze() to group by initArg (the settings template) instead.
     */
    SpawnCapture.dump = function () {
        var c = SpawnCapture._captures;
        if (!c.length) { console.log("[SpawnCapture] no captures"); return; }
        console.log("[SpawnCapture] " + c.length + " entities created:");

        var byRtti = {};
        c.forEach(function (e) {
            var key = rttiName(e.entity);
            if (!byRtti[key]) byRtti[key] = [];
            byRtti[key].push(e);
        });

        Object.keys(byRtti).sort().forEach(function (rtti) {
            var group = byRtti[rtti];
            console.log("\n[SpawnCapture] === " + group.length + "x " + rtti + " ===");
            group.forEach(function (e, i) {
                var rva = vtRva(e.entity);
                var pos = "?";
                try { pos = v3str(vec3(e.entity.add(ENTITY_POS_OFF))); } catch (er) {}
                console.log("  [" + i + "] " + e.entity +
                            " vtRva=0x" + rva.toString(16) +
                            " pos=" + pos +
                            " initArg=" + e.initArg);
            });
        });
    };

    // Component-map walker shared between analyze() and its filter.
    // Returns { count, comps: [{key, name}] } or null on read failure.
    function _readComponents(entity) {
        try {
            var ctrlPtr = entity.add(0x5e8).readPointer();
            var valsPtr = entity.add(0x5f0).readPointer();
            var count   = entity.add(0x5f8).readU64().toNumber();
            var capMask = entity.add(0x600).readU64().toNumber();
            if (ctrlPtr.isNull() || valsPtr.isNull() || count === 0 || capMask < 0) return null;
            var capacity = capMask + 1;
            if (capacity > 1024) return null;
            var comps = [];
            for (var i = 0; i < capacity && comps.length < 32; i++) {
                var ctrl;
                try { ctrl = ctrlPtr.add(i).readU8(); } catch (er) { break; }
                if (ctrl >= 0x80) continue;
                try {
                    var entry = valsPtr.add(i * 16);
                    var hashKey = entry.readU32();
                    var compPtr = entry.add(8).readPointer();
                    if (compPtr.isNull()) continue;
                    comps.push({ key: hashKey, name: rttiName(compPtr) });
                } catch (er) {}
            }
            if (!comps.length) return null;
            return { count: count, comps: comps };
        } catch (e) { return null; }
    }

    /*
     * ----------------------------------------------------------------
     * SpawnCapture.analyze(opts?: { requireComponent?: string }): void
     *
     * Smart filtered view: drops zero-position entities, groups by
     * initArg (the settings template), sorts groups by size descending,
     * and walks each group's first entity's component hashmap to show
     * component class names. Use this to identify which template is
     * "pigs" vs "barriers" vs "shards" via the components attached.
     *
     * opts.requireComponent: case-insensitive substring filter against
     * component RTTI names. Only groups whose first entity has at least
     * one component matching the filter are printed. Use to focus on
     * enemies (e.g., "EnemyController") and skip static / despawned /
     * effect entities. Groups whose component map can't be read are
     * dropped when a filter is set (no name to match).
     *
     * Run after entities have fully constructed; for cleanest data,
     * stop() and analyze() before fighting / killing the cauldron.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Filters captures to those with non-zero entity+0x324 position.
     *   Groups by initArg (param_2 of the constructor — the per-entity
     *   settings template, equal across instances of the same enemy
     *   type). Walks the component hashmap on the first entity of each
     *   group: ctrl_bytes at +0x5e8, values at +0x5f0 (16-byte entries
     *   {u32 hash, u32 pad, void* component}), capacity_mask at +0x600.
     *   For each occupied slot (Swiss-Tables ctrl byte < 0x80), reads
     *   the component pointer and resolves its RTTI.
     */
    SpawnCapture.analyze = function (opts) {
        var c = SpawnCapture._captures;
        if (!c.length) { console.log("[SpawnCapture] no captures"); return; }

        var filter = (opts && opts.requireComponent) ? String(opts.requireComponent).toLowerCase() : null;

        var withPos = c.filter(function (e) {
            try {
                var v = vec3(e.entity.add(ENTITY_POS_OFF));
                return v[0] !== 0 || v[1] !== 0 || v[2] !== 0;
            } catch (er) { return false; }
        });

        var byTemplate = {};
        withPos.forEach(function (e) {
            var key = e.initArg.toString();
            if (!byTemplate[key]) byTemplate[key] = { initArg: e.initArg, entries: [] };
            byTemplate[key].entries.push(e);
        });

        var groups = Object.keys(byTemplate).map(function (k) { return byTemplate[k]; });
        groups.sort(function (a, b) { return b.entries.length - a.entries.length; });

        // Walk components for each group's first entity (once)
        groups.forEach(function (g) { g.compInfo = _readComponents(g.entries[0].entity); });

        // Apply filter if requested
        var visible = groups;
        if (filter) {
            visible = groups.filter(function (g) {
                if (!g.compInfo) return false;
                return g.compInfo.comps.some(function (cm) {
                    return cm.name.toLowerCase().indexOf(filter) >= 0;
                });
            });
        }

        var header = "[SpawnCapture.analyze] " + c.length + " total, " + withPos.length + " with non-zero pos";
        if (filter) header += "; " + visible.length + "/" + groups.length + " templates match \"" + opts.requireComponent + "\"";
        console.log(header);

        visible.forEach(function (g) {
            console.log("\n[SpawnCapture.analyze] === template " + g.initArg +
                        " (" + g.entries.length + " entities) ===");
            g.entries.slice(0, 3).forEach(function (e, i) {
                var pos;
                try { pos = v3str(vec3(e.entity.add(ENTITY_POS_OFF))); } catch (er) { pos = "?"; }
                console.log("  [" + i + "] " + e.entity + " pos=" + pos);
            });
            if (g.entries.length > 3) console.log("  ... +" + (g.entries.length - 3) + " more");

            if (!g.compInfo) {
                console.log("  components: (none / map empty)");
                return;
            }
            console.log("  components (" + g.compInfo.count + "):");
            g.compInfo.comps.forEach(function (cm) {
                console.log("    - " + cm.name + "  (key 0x" + cm.key.toString(16) + ")");
            });
        });
    };

    // Live captures array exposed for programmatic use.
    SpawnCapture.events = SpawnCapture._captures;

    RW.registerMod("spawn_capture", version);
    console.log("[SpawnCapture] " + version + " loaded. start() / stop() / dump() / analyze()");
})();

// Top-level alias
var SpawnCapture = RW.SpawnCapture;
