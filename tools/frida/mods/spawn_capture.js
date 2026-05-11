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
    var version = "0.8.1";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[SpawnCapture] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;
    var imageEnd  = imageBase.add(mod.size);

    var ENTITY_CTOR_RVA  = 0x6c96f0;
    var ENTITY_POS_OFF   = 0x324;
    var OCENTITY_VT_RVA  = 0xf4cc40;

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
                    this._caller  = this.returnAddress;
                    this._ts      = Date.now();
                    // Walk a few frames up — caller is inside the allocator;
                    // the actual spawn site is two frames up. Backtracer.ACCURATE
                    // is slow but on a low-frequency hook (~tens-of-Hz), fine.
                    try {
                        this._stack = Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 4);
                    } catch (er) { this._stack = null; }
                } catch (e) { this._entity = null; }
            },
            onLeave: function () {
                if (!this._entity) return;
                SpawnCapture._captures.push({
                    ts: this._ts,
                    entity: this._entity,
                    initArg: this._initArg,
                    caller: this._caller,
                    stack:  this._stack,
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

    // Read display name from an oCEntitySettingsResource pointer.
    // Mirrors the encyclopedia walker pattern: strPtr at +0x08,
    // u32 length at +0x10, decoded via readUtf8String. Returns null
    // on any read failure (initArg may be null, freed, or non-settings).
    function _readSettingsName(initArg) {
        try {
            if (initArg.isNull()) return null;
            var strPtr = initArg.add(0x08).readPointer();
            var len    = initArg.add(0x10).readU32();
            if (len <= 0 || len > 512) return null;
            return strPtr.readUtf8String(len);
        } catch (e) { return null; }
    }

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

        // Group by template across ALL captures (not just non-zero-pos).
        // Dead-enemy slabs get zeroed by the time we read — filtering by
        // current position would drop the templates we most want to see.
        var byTemplate = {};
        c.forEach(function (e) {
            var key = e.initArg.toString();
            if (!byTemplate[key]) byTemplate[key] = { initArg: e.initArg, entries: [] };
            byTemplate[key].entries.push(e);
        });

        var groups = Object.keys(byTemplate).map(function (k) { return byTemplate[k]; });
        groups.sort(function (a, b) { return b.entries.length - a.entries.length; });

        // Walk components + resolve settings name for each group (once each)
        groups.forEach(function (g) {
            g.compInfo = _readComponents(g.entries[0].entity);
            g.name     = _readSettingsName(g.initArg);

            // Aggregate the FULL stack frame at depth 2 (the spawn-site
            // caller, two frames above the oCEntity::ctor hook — frame 0
            // is inside the allocator, frame 1 is inside the trampoline,
            // frame 2 is the actual spawn-site code).
            function aggregate(getter) {
                var hist = {};
                g.entries.forEach(function (e) {
                    var v = getter(e);
                    if (!v) return;
                    var key = v.toString();
                    hist[key] = (hist[key] || 0) + 1;
                });
                var keys = Object.keys(hist);
                keys.sort(function (a, b) { return hist[b] - hist[a]; });
                return keys.slice(0, 3).map(function (k) {
                    var rva = -1;
                    try {
                        var p = ptr(k);
                        if (p.compare(imageBase) >= 0 && p.compare(imageEnd) < 0) {
                            rva = p.sub(imageBase).toInt32();
                        }
                    } catch (er) {}
                    return { addr: k, rva: rva, count: hist[k] };
                });
            }

            g.callers     = aggregate(function (e) { return e.caller; });
            g.spawnSites2 = aggregate(function (e) { return (e.stack && e.stack[2]) || null; });
            g.spawnSites3 = aggregate(function (e) { return (e.stack && e.stack[3]) || null; });
        });

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
            var label = g.name ? g.name + " [" + g.initArg + "]" : "template " + g.initArg;
            console.log("\n[SpawnCapture.analyze] === " + label +
                        " (" + g.entries.length + " entities) ===");
            g.entries.slice(0, 3).forEach(function (e, i) {
                var pos;
                try { pos = v3str(vec3(e.entity.add(ENTITY_POS_OFF))); } catch (er) { pos = "?"; }
                console.log("  [" + i + "] " + e.entity + " pos=" + pos);
            });
            if (g.entries.length > 3) console.log("  ... +" + (g.entries.length - 3) + " more");

            if (!g.compInfo) {
                console.log("  components: (none / map empty)");
            } else {
                console.log("  components (" + g.compInfo.count + "):");
                g.compInfo.comps.forEach(function (cm) {
                    console.log("    - " + cm.name + "  (key 0x" + cm.key.toString(16) + ")");
                });
            }

            function printFrames(label, frames) {
                if (!frames || !frames.length) return;
                console.log("  " + label + ":");
                frames.forEach(function (c) {
                    var rvaStr = (c.rva >= 0) ? ("RVA 0x" + c.rva.toString(16)) : "(out of module)";
                    console.log("    " + c.addr + " " + rvaStr + "  x" + c.count);
                });
            }
            printFrames("frame[0] return-into-allocator", g.callers);
            printFrames("frame[2] spawn-site",            g.spawnSites2);
            printFrames("frame[3] spawn-site-caller",     g.spawnSites3);
        });
    };

    /*
     * ----------------------------------------------------------------
     * SpawnCapture.findCommonParents(opts?: { templateSubstring?: string, scanBytes?: number }): void
     *
     * For each captured entity matching the template name filter,
     * scan its first scanBytes bytes a qword at a time looking for
     * non-module pointers whose dereference is the oCEntity vtable
     * (RVA 0xf4cc40). Aggregate: count how often each unique parent
     * pointer appears across the matching entity set. Sorted desc.
     *
     * Use case: traverse from runtime-spawned children (eggs,
     * projectiles, etc.) to their pre-existing parent enemy. If the
     * parent is the same across all children, it dominates the
     * histogram (e.g., 7/7 eggs reference the mom spider).
     *
     * opts.templateSubstring: case-insensitive substring filter
     *   against resolved settings names. Default: no filter (all
     *   captures).
     * opts.scanBytes: bytes per entity to scan (default 0x200,
     *   covers most known component layouts).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   For each capture matching the filter, walks bytes off=0..N
     *   step 8: tries readPointer at entity+off; if pointer-shaped
     *   AND outside the module range AND its deref's vtable RVA is
     *   OCENTITY_VT_RVA, records it. Aggregates counts across all
     *   matching captures. Module-range pointers are skipped to
     *   exclude vtable slots.
     */
    SpawnCapture.findCommonParents = function (opts) {
        var caps = SpawnCapture._captures;
        if (!caps.length) { console.log("[SpawnCapture.findCommonParents] no captures"); return; }

        var filter    = (opts && opts.templateSubstring) ? String(opts.templateSubstring).toLowerCase() : null;
        var scanBytes = (opts && typeof opts.scanBytes === 'number') ? opts.scanBytes : 0x200;

        var matching = caps;
        if (filter) {
            matching = caps.filter(function (e) {
                var n = _readSettingsName(e.initArg);
                return n && n.toLowerCase().indexOf(filter) >= 0;
            });
        }
        if (!matching.length) {
            console.log("[SpawnCapture.findCommonParents] no entities match filter \"" + filter + "\"");
            return;
        }

        var hist = {};   // parentPtrStr -> { count, offsets:Set }
        matching.forEach(function (cap) {
            var seen = {};   // dedupe within one entity
            for (var off = 0; off < scanBytes; off += 8) {
                var v;
                try { v = cap.entity.add(off).readPointer(); } catch (e) { continue; }
                if (v.compare(imageBase) >= 0 && v.compare(imageEnd) < 0) continue;
                if (vtRva(v) !== OCENTITY_VT_RVA) continue;
                var key = v.toString();
                if (seen[key]) continue;
                seen[key] = true;
                if (!hist[key]) hist[key] = { count: 0, offsets: {} };
                hist[key].count += 1;
                hist[key].offsets[off] = (hist[key].offsets[off] || 0) + 1;
            }
        });

        var keys = Object.keys(hist);
        keys.sort(function (a, b) { return hist[b].count - hist[a].count; });

        var label = filter ? "matching \"" + filter + "\"" : "(all captures)";
        console.log("[SpawnCapture.findCommonParents] " + matching.length + " entities " + label +
                    "; scan " + scanBytes + " bytes each:");
        if (!keys.length) {
            console.log("  no oCEntity backrefs found in any entity");
            return;
        }
        keys.slice(0, 10).forEach(function (k) {
            var rec = hist[k];
            var offs = Object.keys(rec.offsets).map(function (o) { return "+0x" + parseInt(o, 10).toString(16); }).join(",");
            console.log("  " + k + "  " + rec.count + "/" + matching.length + " entities  (offsets: " + offs + ")");
        });
    };

    // Live captures array exposed for programmatic use.
    SpawnCapture.events = SpawnCapture._captures;

    RW.registerMod("spawn_capture", version);
    console.log("[SpawnCapture] " + version + " loaded. start() / stop() / dump() / analyze() / findCommonParents()");
})();

// Top-level alias
var SpawnCapture = RW.SpawnCapture;
