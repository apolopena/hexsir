// spawner_probe.js — capture spawner instances at chapter load, identify
// them by parent-entity name + sub-index, and fire them on demand.
//
// Working flow (per rw/findings/entity-spawner-mechanism.md):
//   1. Hook FUN_1402d0ee0 (the oCEntityCpntEntitySpawner ctor) BEFORE the
//      chapter loads. Every spawner created during chapter setup is captured
//      to RW.SpawnerProbe._spawners with its +0x08 parent and +0x10 settings.
//   2. After chapter load, filter the captured set by parent-entity name
//      (parent.+0x28 settings name — stable, asset-baked) plus sub-index in
//      the filtered list. That's the cross-session-stable identifier.
//   3. Fire by calling FUN_1406f62b0(spawner) — the broadcast worker that
//      the engine uses internally as part of natural activation. With
//      noWarp:true, no parent warp is performed; the spawn fires at the
//      spawner's natural bound transform. Without noWarp the parent is
//      first warped to the player's position, so the spawn appears at the
//      player.
//
// Most spawners are gated one-shot per chapter (cap state somewhere we
// haven't isolated). Some — e.g. the hourglass reward once the hourglass
// is in active state — are re-fireable indefinitely.
//
// Usage:
//   loadMod("spawner_probe")
//   SpawnerProbe.expr_armSpawnerCtor()   // arm BEFORE reloading chapter
//   <reload chapter>
//   SpawnerProbe.expr_listSpawners({ unfiredOnly: true, nameMatch: "..." })
//   SpawnerProbe.expr_summonAtPlayer({ nameMatch: "...", index: 0, noWarp: true })
//
// Depends on:
//   - RW.Entity (rw_lab.js)              for name->entity lookup
//   - RW.Player (rw_lab.js)              required only when warping (noWarp:false)
//   - RW.Transporter (Transporter.js)    required only when warping

(function () {
    var version = "0.12.0";
    if (typeof RW !== "object") {
        console.log("[SpawnerProbe] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    var rwMod = Process.findModuleByName("Ravenswatch.exe");
    if (!rwMod) { console.log("[SpawnerProbe] FATAL: no Ravenswatch.exe"); return; }
    var IMG     = rwMod.base;
    var IMG_END = IMG.add(rwMod.size);

    var SPAWNER_VT_RVA          = 0xf00650;       // oCEntityCpntEntitySpawner primary vtable
    var HOLDER_VT_RVA           = 0xf4e2e8;       // oe::RegisteredEntitiesHolderEntityCpnt
    var HOLDER_FIRE_ACTIVE_RVA  = 0x6f62b0;       // FUN_1406f62b0 — broadcast worker (active-side) used as the spawn primitive
    var WAVE_ORCHESTRATOR_RVA   = 0x713520;       // FUN_140713520 — vtable[28] wave-spawn orchestrator (capture-only hook target)
    var FIRE_DISPATCHER_RVA     = 0x74ef20;       // FUN_14074ef20 — natural fire dispatcher (capture-only hook target)
    var SPAWNER_CTOR_RVA        = 0x2d0ee0;       // FUN_1402d0ee0 — oCEntityCpntEntitySpawner ctor
    var COMP_ARRAY_OFF          = 0x1c0;          // oCEntity sequential component list head
    var COMP_COUNT_OFF          = 0x1c8;          // count (u32, 8-byte slots)
    var COMP_HASHMAP_CTRL_OFF   = 0x5e8;          // Swiss-Tables ctrl bytes ptr
    var COMP_HASHMAP_VALS_OFF   = 0x5f0;          // entries ptr (16-byte slots)
    var COMP_HASHMAP_COUNT_OFF  = 0x5f8;          // u64 count
    var COMP_HASHMAP_MASK_OFF   = 0x600;          // u64 capacity-1
    var SPAWNER_SETTINGS_OFF    = 0x18;           // settings binding ptr
    var SPAWNER_CACHED_OUT_OFF  = 0x160;          // cached-output guard
    var ENTITY_POS_OFF          = 0x324;
    var FLAG_PTR_THRESHOLD      = ptr("0x10000"); // anything below is a flag, not a heap ptr
    var ENTITY_SPAWNER_PREFIX   = "[Entity spawner] ";

    if (!RW.SpawnerProbe) RW.SpawnerProbe = {};
    var SpawnerProbe = RW.SpawnerProbe;

    SpawnerProbe._lastInspect = SpawnerProbe._lastInspect || null;
    SpawnerProbe._lastFire    = SpawnerProbe._lastFire    || null;
    SpawnerProbe._lastSurvey  = SpawnerProbe._lastSurvey  || null;

    // Curated list of known-interesting spawner-anchor names. Names are stable
    // across launches (asset-cooker baked); heap pointers are not. Grow this
    // as promising anchors are surfaced via survey(). Substrings are matched
    // case-insensitively by the underlying RW.Entity.find.
    SpawnerProbe.candidates = SpawnerProbe.candidates || [
        "Cauldron",
        "EnemySpawner_01",
        "Boss Spawner",
        "Teleporter",
        "NoModel+2Cpnt",
        "Fireflies_2",
    ];

    var SPAWNER_VT = IMG.add(SPAWNER_VT_RVA);
    var HOLDER_VT  = IMG.add(HOLDER_VT_RVA);
    var holderFireActiveFn = new NativeFunction(
        IMG.add(HOLDER_FIRE_ACTIVE_RVA),
        'void', ['pointer']
    );

    // Wave-capture state — survives mod re-eval.
    SpawnerProbe._waveHook    = SpawnerProbe._waveHook    || null;
    SpawnerProbe._waveFires   = SpawnerProbe._waveFires   || [];
    SpawnerProbe._lastWave    = SpawnerProbe._lastWave    || null;
    SpawnerProbe._dispHook    = SpawnerProbe._dispHook    || null;
    SpawnerProbe._dispFires   = SpawnerProbe._dispFires   || [];
    SpawnerProbe._lastDisp    = SpawnerProbe._lastDisp    || null;
    SpawnerProbe._ctorHook    = SpawnerProbe._ctorHook    || null;
    SpawnerProbe._spawners    = SpawnerProbe._spawners    || [];

    function inImage(p) {
        try { return p.compare(IMG) >= 0 && p.compare(IMG_END) < 0; }
        catch (e) { return false; }
    }

    function vtRva(obj) {
        try {
            var vt = obj.readPointer();
            if (inImage(vt)) return vt.sub(IMG).toInt32();
        } catch (e) {}
        return -1;
    }

    function rttiName(obj) {
        try {
            var vt   = obj.readPointer();
            var col  = vt.sub(8).readPointer();
            var tdRva   = col.add(0x0c).readU32();
            var selfRva = col.add(0x14).readU32();
            var imgBase = col.sub(selfRva);
            return imgBase.add(tdRva).add(0x10).readCString();
        } catch (e) { return "?"; }
    }

    function readSettingsName(settings) {
        try {
            if (settings.isNull()) return null;
            var strPtr = settings.add(0x08).readPointer();
            var len    = settings.add(0x10).readU32();
            if (len <= 0 || len > 512) return null;
            return strPtr.readUtf8String(len);
        } catch (e) { return null; }
    }

    function readVec3(p) {
        try {
            return {
                x: p.readFloat(),
                y: p.add(4).readFloat(),
                z: p.add(8).readFloat(),
            };
        } catch (e) { return null; }
    }

    function v3str(v) {
        if (!v) return "?";
        return "(" + v.x.toFixed(2) + "," + v.y.toFixed(2) + "," + v.z.toFixed(2) + ")";
    }

    // Walk both component access paths and dedupe. Each result is
    // { ptr, source, rva, rtti } where source is "seq" | "hash".
    function walkComponents(entity) {
        var seen = {};
        var out  = [];
        function push(comp, source) {
            if (!comp || comp.isNull()) return;
            var key = comp.toString();
            if (seen[key]) return;
            seen[key] = true;
            out.push({ ptr: comp, source: source, rva: vtRva(comp), rtti: rttiName(comp) });
        }
        // Sequential array at +0x1c0/+0x1c8
        try {
            var arr   = entity.add(COMP_ARRAY_OFF).readPointer();
            var count = entity.add(COMP_COUNT_OFF).readU32();
            if (!arr.isNull() && count > 0 && count < 256) {
                for (var i = 0; i < count; i++) {
                    var comp;
                    try { comp = arr.add(i * 8).readPointer(); } catch (e) { continue; }
                    push(comp, "seq");
                }
            }
        } catch (e) {}
        // Swiss-Tables hashmap at +0x5e8/+0x5f0/+0x5f8/+0x600
        try {
            var ctrl = entity.add(COMP_HASHMAP_CTRL_OFF).readPointer();
            var vals = entity.add(COMP_HASHMAP_VALS_OFF).readPointer();
            var mapCount = entity.add(COMP_HASHMAP_COUNT_OFF).readU64().toNumber();
            var mask     = entity.add(COMP_HASHMAP_MASK_OFF).readU64().toNumber();
            if (!ctrl.isNull() && !vals.isNull() && mapCount > 0 && mask > 0 && mask < 1024) {
                var capacity = mask + 1;
                for (var j = 0; j < capacity; j++) {
                    var c;
                    try { c = ctrl.add(j).readU8(); } catch (er) { break; }
                    if (c >= 0x80) continue;
                    try {
                        var compPtr = vals.add(j * 16).add(8).readPointer();
                        push(compPtr, "hash");
                    } catch (er) {}
                }
            }
        } catch (e) {}
        return out;
    }

    // Pick the spawner-class components out of a walked component list.
    function filterSpawners(comps) {
        return comps.filter(function (c) { return c.rva === SPAWNER_VT_RVA; });
    }

    // Sanity-gate the spawner before firing. Returns null on pass, a
    // string reason on fail. The prior dig session crashed when +0x18
    // was 0x1 (a flag, not a pointer); guard against that and similar.
    function reasonNotFireable(spawner) {
        var settings;
        try { settings = spawner.add(SPAWNER_SETTINGS_OFF).readPointer(); }
        catch (e) { return "+0x18 unreadable"; }
        if (settings.isNull()) return "+0x18 is null";
        if (settings.compare(FLAG_PTR_THRESHOLD) < 0) {
            return "+0x18 looks like a flag, not a pointer (" + settings + ")";
        }
        var settingsVt;
        try { settingsVt = settings.readPointer(); }
        catch (e) { return "+0x18 deref unreadable"; }
        if (!inImage(settingsVt)) {
            return "+0x18 settings vtable not in image (" + settingsVt + ")";
        }
        return null;
    }

    function describeSpawner(spawner) {
        var settings = null, settingsVt = null, cached = null, name = null;
        try { settings = spawner.add(SPAWNER_SETTINGS_OFF).readPointer(); } catch (e) {}
        try { cached   = spawner.add(SPAWNER_CACHED_OUT_OFF).readPointer(); } catch (e) {}
        if (settings && !settings.isNull()) {
            try { settingsVt = settings.readPointer(); } catch (e) {}
            name = readSettingsName(settings);
        }
        return {
            spawner:    spawner,
            settings:   settings,
            settingsVt: settingsVt,
            template:   name,
            cached:     cached,
        };
    }

    function findEntityByName(name) {
        if (!RW.Entity || typeof RW.Entity.find !== 'function') {
            console.log("[SpawnerProbe] FATAL: RW.Entity missing (rw_lab.js not loaded?)");
            return null;
        }
        var hit = RW.Entity.find(name);
        if (hit === undefined) {
            console.log("[SpawnerProbe] scene_manager not captured — play one frame, then retry");
            return null;
        }
        if (!hit) {
            console.log("[SpawnerProbe] no entity matches \"" + name + "\" in the streamed cache");
            return null;
        }
        if (!hit.entity || hit.entity.isNull()) {
            console.log("[SpawnerProbe] \"" + hit.name + "\" has no live oCEntity back-pointer");
            return null;
        }
        return hit;
    }

    function logSpawnerLine(idx, info) {
        var tplStr = info.template ? "\"" + info.template + "\"" : "<unnamed>";
        console.log("[SpawnerProbe]   spawner[" + idx + "] " + info.spawner +
                    "  +0x18=" + info.settings + " (" + tplStr + ")" +
                    "  +0x160=" + info.cached);
    }

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.inspect(name: string): { entity, spawners, ... } | null
     *
     * Diagnostic only — no spawn is fired. Looks up the entity matching
     * `name` (case-insensitive substring) via RW.Entity.find, walks its
     * sequential component list at +0x1c0/+0x1c8, and reports every
     * oCEntityCpntEntitySpawner component on it (matched by vtable
     * RVA 0xf00650).
     *
     * For each spawner found, prints:
     *   - spawner address
     *   - +0x18 settings binding (and the template's display name)
     *   - +0x160 cached-output guard (non-null means a previous spawn
     *     is still alive; fire() would no-op without clearing it)
     *
     * Usage:
     *   SpawnerProbe.inspect("hourglass")
     *   SpawnerProbe.inspect("sandman")
     *   SpawnerProbe.inspect("teleporter")
     *
     * Result:
     *   Returns { entity, name, loc, settings, spawners: [{ spawner,
     *   settings, settingsVt, template, cached }] } on a match
     *   (spawners may be empty). Returns null if no entity matches or
     *   the live entity is missing. Caches the result on
     *   RW.SpawnerProbe._lastInspect for follow-up REPL inspection.
     *
     * Caveats:
     *   - RW.Entity.find only sees the streamed-in encyclopedia cache
     *     (typically 15-30 near the player at boot, up to ~2000 after
     *     exploration). Walk past the target once if the lookup misses.
     *   - The encyclopedia gives ONE entity back-pointer per settings
     *     class. If multiple instances share a template (e.g. several
     *     identical fireflies), this only reaches one of them.
     *   - Empty `spawners` is informative — the entity exists but
     *     does not bear the spawner component, so Path B does not
     *     apply to it; try a different candidate.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Per rw/findings/entity-spawner-mechanism.md, every entity-
     *   spawner component shares the primary vtable at IMG+0xf00650
     *   (30 entries). The component sequential list lives at
     *   oCEntity+0x1c0 (head ptr) / +0x1c8 (count u32, 8-byte slots).
     *   The settings name pattern is the standard RW asset-cache
     *   layout: settings+0x08 = char*, settings+0x10 = u32 length,
     *   confirmed in transporter-placement-primitive.md.
     */
    SpawnerProbe.inspect = function (name) {
        var hit = findEntityByName(name);
        if (!hit) return null;
        console.log("[SpawnerProbe] match: \"" + hit.name + "\"  entity=" + hit.entity +
                    " loc=" + v3str(hit.loc));
        var comps    = walkComponents(hit.entity);
        var spawnRaw = filterSpawners(comps);
        var spawners = spawnRaw.map(function (c) { return describeSpawner(c.ptr); });
        console.log("[SpawnerProbe]   " + comps.length + " component(s) total:");
        comps.forEach(function (c, i) {
            var rvaStr = (c.rva >= 0) ? ("RVA 0x" + c.rva.toString(16)) : "(out of module)";
            var mark   = (c.rva === SPAWNER_VT_RVA) ? " ★ spawner" : "";
            console.log("[SpawnerProbe]     [" + i + "] " + c.ptr +
                        " (" + c.source + ") vt=" + rvaStr + " rtti=" + c.rtti + mark);
        });
        if (!spawners.length) {
            console.log("[SpawnerProbe]   no spawner-class components match — Path B does not apply here");
        } else {
            console.log("[SpawnerProbe]   " + spawners.length + " spawner component(s):");
            spawners.forEach(function (info, i) { logSpawnerLine(i, info); });
        }
        var result = {
            entity:     hit.entity,
            name:       hit.name,
            loc:        hit.loc,
            settings:   hit.value,
            components: comps,
            spawners:   spawners,
        };
        SpawnerProbe._lastInspect = result;
        return result;
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.survey(opts?: { prefix?: string, substring?: string }): array
     *
     * Walks the streamed encyclopedia cache, filters entries by name,
     * and reports every spawner-bearing entity it finds. Default
     * filter is the prefix "[Entity spawner] " — every encyclopedia
     * entry under that format string is by construction an instance
     * of the spawner anchor pattern (format string at IMG+0xf4f4b0).
     *
     * opts.prefix:    case-insensitive name-starts-with filter.
     *                 Default "[Entity spawner] ".
     * opts.substring: case-insensitive name-contains filter; takes
     *                 precedence over prefix when both are set.
     *
     * Usage:
     *   SpawnerProbe.survey()                    // every spawner anchor
     *   SpawnerProbe.survey({ substring: "fire" })   // only "Firefly_*"
     *   SpawnerProbe.survey({ prefix: "Map_" })      // any Map_* entry
     *
     * Result:
     *   For each match: prints one line with name, entity ptr, loc,
     *   spawner-component count, and (if any) the first spawner's
     *   +0x18 template name. Returns the array of per-match records
     *   sorted by spawner-bearing-first. Caches on
     *   RW.SpawnerProbe._lastSurvey.
     *
     * Caveats:
     *   - Pulls from the same streamed cache as inspect(); only
     *     entries currently loaded near the player show up.
     *   - The internal call also triggers RW.Entity.list()'s
     *     informational print of every cached entry. Treat the dump
     *     as a free side benefit, not noise to suppress.
     *   - One settings -> one entity back-pointer. If a settings
     *     class has multiple instances, only one is reachable here.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Calls RW.Entity.list() to get the full encyclopedia walk,
     *   filters by name, then for each surviving entry runs the same
     *   walkComponents + filterSpawners pipeline as inspect(). One-
     *   line summary uses describeSpawner() on the first match.
     */
    SpawnerProbe.survey = function (opts) {
        if (!RW.Entity || typeof RW.Entity.list !== 'function') {
            console.log("[SpawnerProbe] FATAL: RW.Entity missing (rw_lab.js not loaded?)");
            return null;
        }
        var prefix    = opts && opts.prefix    ? String(opts.prefix).toLowerCase()    : ENTITY_SPAWNER_PREFIX.toLowerCase();
        var substring = opts && opts.substring ? String(opts.substring).toLowerCase() : null;

        var raw = RW.Entity.list();
        if (!raw) return null;

        var matches = raw.filter(function (e) {
            var n = e.name ? e.name.toLowerCase() : "";
            if (substring) return n.indexOf(substring) >= 0;
            return n.indexOf(prefix) === 0;
        });

        var results = matches.map(function (e) {
            var comps    = walkComponents(e.entity);
            var spawnRaw = filterSpawners(comps);
            var info     = spawnRaw.length ? describeSpawner(spawnRaw[0].ptr) : null;
            return {
                name:           e.name,
                entity:         e.entity,
                loc:            e.loc,
                settings:       e.value,
                componentCount: comps.length,
                spawnerCount:   spawnRaw.length,
                firstSpawner:   info,
            };
        });

        // Spawner-bearing first, then by component count desc.
        results.sort(function (a, b) {
            if (a.spawnerCount !== b.spawnerCount) return b.spawnerCount - a.spawnerCount;
            return b.componentCount - a.componentCount;
        });

        var label = substring ? "substring \"" + substring + "\"" : "prefix \"" + prefix + "\"";
        console.log("[SpawnerProbe.survey] " + results.length + " entr(y/ies) match " + label);
        results.forEach(function (r) {
            var tpl = (r.firstSpawner && r.firstSpawner.template)
                ? "\"" + r.firstSpawner.template + "\""
                : (r.spawnerCount > 0 ? "<unnamed>" : "(no spawner)");
            console.log("[SpawnerProbe.survey]   " + r.entity + " loc=" + v3str(r.loc) +
                        "  comps=" + r.componentCount + " spawners=" + r.spawnerCount +
                        " bound=" + tpl + "  name=\"" + r.name + "\"");
        });

        var fireable = results.filter(function (r) { return r.spawnerCount > 0; });
        console.log("[SpawnerProbe.survey] ----------------------------------------");
        if (!fireable.length) {
            console.log("[SpawnerProbe.survey] FIREABLE: 0 / " + results.length +
                        " — no oCEntityCpntEntitySpawner (vtable 0xf00650) found on any match.");
            console.log("[SpawnerProbe.survey] Likely cause: these anchors use sibling/derived");
            console.log("[SpawnerProbe.survey] spawner classes (camp selectors, boss spawners,");
            console.log("[SpawnerProbe.survey] cauldron anchors, etc.). Run inspect(name) on one");
            console.log("[SpawnerProbe.survey] of them to see the actual component RTTI.");
        } else {
            console.log("[SpawnerProbe.survey] FIREABLE: " + fireable.length + " / " + results.length +
                        " bear oCEntityCpntEntitySpawner:");
            fireable.forEach(function (r) {
                var tpl = (r.firstSpawner && r.firstSpawner.template)
                    ? r.firstSpawner.template : "<unnamed>";
                console.log("[SpawnerProbe.survey]   \"" + r.name + "\"  -> " + tpl);
            });
        }
        SpawnerProbe._lastSurvey = results;
        return results;
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_captureWaveTrigger(): void
     *
     * UNVERIFIED PRIMITIVE — research only. Arms an Interceptor on
     * FUN_140713520 (RVA 0x713520) — the wave-spawn orchestrator that
     * fires once per enemy in a wave. On every call, captures:
     *   - param_1 (RCX) = the wave-context object pointer
     *   - return address = the caller of the orchestrator (the
     *     wave-trigger code path we couldn't find via static xrefs
     *     because the dispatch is via vtable[28])
     *   - timestamp
     *
     * Re-arming detaches any prior hook. Captures append to
     * RW.SpawnerProbe._waveFires (each entry { ts, context, retAddr,
     * retRva }) and the most recent is mirrored to ._lastWave.
     *
     * Usage:
     *   SpawnerProbe.expr_captureWaveTrigger()   // arm hook
     *   <walk to cauldron, activate naturally>
     *   SpawnerProbe.expr_stopWaveCapture()      // detach + dump
     *
     * Result: each fire logs one line "[expr_captureWaveTrigger]
     * fire #N context=<ptr> retRva=<rva>". The hook stays armed
     * until expr_stopWaveCapture() is called.
     *
     * Caveats:
     *   - Frida Interceptor on a hot vtable-dispatched method is
     *     fine cost-wise (waves fire infrequently), but the hook
     *     should be detached after capture to avoid lingering side
     *     effects on subsequent waves.
     *   - The captured context pointer is heap-allocated and may be
     *     freed at chapter unload. Do not rely on it persisting
     *     across chapter transitions.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   FUN_140713520 is at vtable[28] (offset +0xe0) of multiple
     *   spawner-flavored classes including oCEntityCpntEntitySpawner
     *   (vtable 0x140f00650). Static xrefs are all data refs (vtable
     *   slots) — no direct calls — so dynamic capture is the only
     *   way to surface the actual trigger code path. The return
     *   address from the hook gives us frame[1] of the call stack,
     *   which is what we need.
     */
    SpawnerProbe.expr_captureWaveTrigger = function () {
        var prefix = "[SpawnerProbe.expr_captureWaveTrigger]";
        if (SpawnerProbe._waveHook) {
            try { SpawnerProbe._waveHook.detach(); } catch (e) {}
            SpawnerProbe._waveHook = null;
        }
        SpawnerProbe._waveFires = [];
        SpawnerProbe._lastWave  = null;
        SpawnerProbe._waveHook = Interceptor.attach(IMG.add(WAVE_ORCHESTRATOR_RVA), {
            onEnter: function (args) {
                try {
                    var ctx     = ptr(args[0]);
                    var retAddr = this.returnAddress;
                    var retRva  = inImage(retAddr) ? retAddr.sub(IMG).toInt32() : -1;
                    var frames = [];
                    try {
                        var stack = Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 4);
                        for (var fi = 0; fi < stack.length; fi++) {
                            var fa  = stack[fi];
                            var fr  = inImage(fa) ? fa.sub(IMG).toInt32() : -1;
                            frames.push({ addr: fa, rva: fr });
                        }
                    } catch (er) { frames = null; }
                    var rec = {
                        ts:      Date.now(),
                        context: ctx,
                        retAddr: retAddr,
                        retRva:  retRva,
                        frames:  frames,
                    };
                    SpawnerProbe._waveFires.push(rec);
                    SpawnerProbe._lastWave = rec;
                    var frameStr = "";
                    if (frames) {
                        for (var fj = 0; fj < frames.length; fj++) {
                            var fr2 = frames[fj].rva;
                            frameStr += " f" + fj + "=" +
                                (fr2 >= 0 ? "0x" + fr2.toString(16) : "OOM");
                        }
                    }
                    console.log(prefix + " fire #" + SpawnerProbe._waveFires.length +
                                " context=" + ctx +
                                " retRva=" + (retRva >= 0 ? "0x" + retRva.toString(16) : "(out of module)") +
                                frameStr);
                } catch (e) {
                    console.log(prefix + " onEnter EXC: " + e.message);
                }
            },
        });
        console.log(prefix + " armed at FUN_140713520 (RVA 0x" + WAVE_ORCHESTRATOR_RVA.toString(16) + ")");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_stopWaveCapture(): void
     *
     * Detach the wave-capture hook armed by expr_captureWaveTrigger.
     * Prints a summary of captured fires (count, distinct contexts,
     * distinct caller RVAs).
     *
     * No-op if not armed. Captured records remain in
     * RW.SpawnerProbe._waveFires for follow-up REPL inspection.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_stopWaveCapture = function () {
        var prefix = "[SpawnerProbe.expr_stopWaveCapture]";
        if (!SpawnerProbe._waveHook) {
            console.log(prefix + " not armed");
            return;
        }
        try { SpawnerProbe._waveHook.detach(); } catch (e) {}
        SpawnerProbe._waveHook = null;
        var fires = SpawnerProbe._waveFires;
        var seenCtx = {};
        var seenF = [{}, {}, {}, {}];
        fires.forEach(function (r) {
            seenCtx[r.context.toString()] = (seenCtx[r.context.toString()] || 0) + 1;
            if (r.frames) {
                for (var i = 0; i < Math.min(r.frames.length, 4); i++) {
                    var rva = r.frames[i].rva;
                    var k = rva >= 0 ? "0x" + rva.toString(16) : "OOM";
                    seenF[i][k] = (seenF[i][k] || 0) + 1;
                }
            }
        });
        console.log(prefix + " detached. " + fires.length + " fire(s) captured.");
        console.log(prefix + " distinct contexts: " + Object.keys(seenCtx).length);
        Object.keys(seenCtx).forEach(function (k) {
            console.log(prefix + "   " + k + "  x" + seenCtx[k]);
        });
        for (var i = 0; i < 4; i++) {
            var keys = Object.keys(seenF[i]);
            if (!keys.length) continue;
            console.log(prefix + " frame[" + i + "] distinct callers: " + keys.length);
            keys.sort(function (a, b) { return seenF[i][b] - seenF[i][a]; });
            keys.slice(0, 8).forEach(function (k) {
                console.log(prefix + "   " + k + "  x" + seenF[i][k]);
            });
        }
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_replayLastWave(): void
     *
     * UNVERIFIED PRIMITIVE — research only. Calls FUN_140713520
     * (the wave orchestrator) directly with the most recently-
     * captured wave-context pointer (from expr_captureWaveTrigger).
     *
     * Usage:
     *   SpawnerProbe.expr_captureWaveTrigger()
     *   <walk to cauldron, activate naturally — populates _lastWave>
     *   SpawnerProbe.expr_stopWaveCapture()
     *   SpawnerProbe.expr_replayLastWave()    // fire another wave
     *
     * Caveats:
     *   - First-ever attempt. May crash, produce a duplicated wave,
     *     produce nothing, or destabilize the wave manager. Save the
     *     run before invoking.
     *   - The wave context may be in a "consumed" state after the
     *     natural activation. Re-firing might no-op or produce
     *     unexpected behavior.
     *   - The context's referenced sub-objects (param_1->+0x10
     *     settings, +0xc8 spawn-target, +0x150 transform source, etc.)
     *     may have been freed or reused since capture.
     * ----------------------------------------------------------------
     */
    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_inspectLastWave(): void
     *
     * Dumps the field state of the most-recently-captured wave context
     * (RW.SpawnerProbe._lastWave.context). Reads every offset that
     * FUN_140713520 (the orchestrator) accesses, plus the broadcast-
     * worker fields. -1 sentinels (0xffffffffffffffff) are highlighted
     * so we can tell which field is in a "torn-down" state and is
     * causing replay to crash.
     *
     * Usage (typical diagnostic flow after a replay crash):
     *   SpawnerProbe.expr_captureWaveTrigger()
     *   <natural cauldron activation>
     *   SpawnerProbe.expr_stopWaveCapture()
     *   SpawnerProbe.expr_inspectLastWave()    // ← see what's at -1
     *   SpawnerProbe.expr_replayLastWave()     // (optional, may crash)
     *
     * Result: prints one line per field with offset, label, and value.
     * Lines whose pointer is -1 or NULL are suffixed with " ★ -1
     * SENTINEL" or " (null)" so the eye can scan.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Maps the field offsets observed in the orchestrator decompile:
     *     +0x00 vtable, +0x08 owner-ptr, +0x10 settings,
     *     +0x64 flag-byte, +0xc8 spawn-target,
     *     +0x110/+0x150/+0x158/+0x180 transform sources,
     *     +0x1a8 settings-context,
     *     +0x1bc transform-mode (0 vs 1),
     *     +0x1c0/+0x1c8/+0x1cc spawn-list head/count/cap (★ where the
     *     replay crash hits if +0x1c0 is -1),
     *     +0x1d8/+0x1f8 event dispatcher lists,
     *     +0x210/+0x218 + +0x220/+0x228 sub-spawn lists,
     *     +0x230 fire-flag set by FUN_14070ae70.
     */
    SpawnerProbe.expr_inspectLastWave = function () {
        var prefix = "[SpawnerProbe.expr_inspectLastWave]";
        if (!SpawnerProbe._lastWave) {
            console.log(prefix + " no captured wave — call expr_captureWaveTrigger first");
            return null;
        }
        var c = SpawnerProbe._lastWave.context;
        console.log(prefix + " context=" + c +
                    " retRva=0x" + SpawnerProbe._lastWave.retRva.toString(16));

        var FIELDS = [
            [0x000, 'ptr', 'vtable'],
            [0x008, 'ptr', '+0x08 owner/parent'],
            [0x010, 'ptr', '+0x10 settings'],
            [0x064, 'u8',  '+0x64 flag-byte'],
            [0x0c8, 'ptr', '+0xc8 spawn-target ctx'],
            [0x110, 'ptr', '+0x110 transform-A'],
            [0x150, 'ptr', '+0x150 transform-B'],
            [0x158, 'ptr', '+0x158 transform-B-alt'],
            [0x160, 'ptr', '+0x160 (oCSpawner cached output, if applicable)'],
            [0x168, 'u8',  '+0x168 (oCSpawner active flag, if applicable)'],
            [0x180, 'ptr', '+0x180 callback record'],
            [0x1a8, 'ptr', '+0x1a8 settings sub-ctx'],
            [0x1b0, 'ptr', '+0x1b0 (finalize branch source A) ★'],
            [0x1b8, 'ptr', '+0x1b8 (finalize branch source B) ★'],
            [0x1bc, 'u32', '+0x1bc transform-mode'],
            [0x1c0, 'ptr', '+0x1c0 spawn-list head ★'],
            [0x1c8, 'u32', '+0x1c8 spawn-list count'],
            [0x1cc, 'u32', '+0x1cc spawn-list cap'],
            [0x1d8, 'ptr', '+0x1d8 event-list-A'],
            [0x1f8, 'ptr', '+0x1f8 event-list-B'],
            [0x210, 'ptr', '+0x210 sub-spawn list'],
            [0x218, 'u32', '+0x218 sub-spawn count'],
            [0x220, 'ptr', '+0x220 listener list 2'],
            [0x228, 'u32', '+0x228 listener count 2'],
            [0x230, 'u8',  '+0x230 fire-flag'],
        ];

        for (var i = 0; i < FIELDS.length; i++) {
            var off = FIELDS[i][0], ty = FIELDS[i][1], label = FIELDS[i][2];
            var disp;
            try {
                if (ty === 'ptr') {
                    var p = c.add(off).readPointer();
                    if (p.toString() === '0xffffffffffffffff') disp = p + "  ★ -1 SENTINEL";
                    else if (p.isNull())                       disp = p + "  (null)";
                    else                                        disp = p.toString();
                } else if (ty === 'u32') {
                    disp = "0x" + c.add(off).readU32().toString(16);
                } else if (ty === 'u8') {
                    disp = "0x" + c.add(off).readU8().toString(16);
                }
            } catch (e) { disp = "<read error: " + e.message + ">"; }
            console.log(prefix + "   " + label + " = " + disp);
        }

        // The +0x60..0x90 region holds the sub-object that FUN_140713c30
        // returns when settings+0x1bc is 1 or 2 (our case). The crash
        // most likely comes from FUN_140714350 dereffing *(this+0x68)
        // as a vtable. Dump the whole area in raw form.
        console.log(prefix + " --- this+0x60..0x90 sub-object header ---");
        for (var sub = 0x60; sub <= 0x88; sub += 8) {
            try {
                var v = c.add(sub).readPointer();
                var s;
                if (v.toString() === '0xffffffffffffffff') s = v + "  ★ -1 SENTINEL";
                else if (v.isNull())                       s = v + "  (null)";
                else                                        s = v.toString();
                console.log(prefix + "   +0x" + sub.toString(16) + " = " + s);
            } catch (e) {
                console.log(prefix + "   +0x" + sub.toString(16) + " READ ERROR");
            }
        }
        // Specifically the vtable at *(this+0x68) — what FUN_1406db260 derefs.
        try {
            var sub68 = c.add(0x68).readPointer();
            if (sub68.toString() !== '0xffffffffffffffff' && !sub68.isNull()) {
                try {
                    var sub68Vt = sub68.readPointer();
                    var s;
                    if (sub68Vt.toString() === '0xffffffffffffffff') s = sub68Vt + "  ★ -1 SENTINEL";
                    else if (sub68Vt.isNull())                       s = sub68Vt + "  (null)";
                    else                                              s = sub68Vt.toString();
                    console.log(prefix + "   *(this+0x68)  = " + sub68);
                    console.log(prefix + "   **(this+0x68) = " + s + "  ← FUN_1406db260 derefs this");
                } catch (e) {
                    console.log(prefix + "   **(this+0x68) READ FAILED: " + e.message);
                }
            } else {
                console.log(prefix + "   *(this+0x68) was bad — skipping deeper deref");
            }
        } catch (e) {}

        // Indirect chain dereferences — the orchestrator follows several
        // paths from this+0x10 (settings) and from this+0x1b0/+0x1b8.
        // Read each one and flag -1 sentinels. This is what tells us
        // which deref crashes the replay.
        console.log(prefix + " --- indirect chain walks ---");
        function safeReadPtr(addr, label) {
            try {
                var v = addr.readPointer();
                var disp;
                if (v.toString() === '0xffffffffffffffff') disp = v + "  ★ -1 SENTINEL";
                else if (v.isNull())                       disp = v + "  (null)";
                else                                        disp = v.toString();
                console.log(prefix + "   " + label + " = " + disp);
                return v;
            } catch (e) {
                console.log(prefix + "   " + label + " READ FAILED: " + e.message);
                return null;
            }
        }
        function safeReadU8(addr, label) {
            try {
                var v = addr.readU8();
                console.log(prefix + "   " + label + " = 0x" + v.toString(16));
                return v;
            } catch (e) {
                console.log(prefix + "   " + label + " READ FAILED: " + e.message);
                return null;
            }
        }
        function safeReadU32(addr, label) {
            try {
                var v = addr.readU32();
                console.log(prefix + "   " + label + " = 0x" + v.toString(16));
                return v;
            } catch (e) {
                console.log(prefix + "   " + label + " READ FAILED: " + e.message);
                return null;
            }
        }

        var settings = null;
        try { settings = c.add(0x10).readPointer(); } catch (e) {}
        if (settings && !settings.isNull()) {
            safeReadU32(settings.add(0x84),   "settings+0x84   gate condition mode");
            safeReadU32(settings.add(0x1bc),  "settings+0x1bc  transform mode");
            safeReadU8(settings.add(0x19f0),  "settings+0x19f0 finalize-branch gate");
            var lvar8root = safeReadPtr(settings.add(0x1a8), "*(settings+0x1a8)  ← orchestrator's lVar8 source");
            if (lvar8root && !lvar8root.isNull() && lvar8root.toString() !== '0xffffffffffffffff') {
                // FUN_1406c9100(lVar15) is called with lVar8 + 0x98.
                var lvar8 = lvar8root.add(0x98);
                console.log(prefix + "   lVar8 = lvar8root + 0x98 = " + lvar8);
                safeReadU32(lvar8.add(0x198), "  *(lVar8+0x198)  spawn-children count");
                // Then the loop derefs *(lVar8+0x190) + i*8 — read base ptr.
                safeReadPtr(lvar8.add(0x190), "  *(lVar8+0x190)  spawn-children base");
            }
        }

        // Finalize-branch reads at this+0x1b0 / this+0x1b8.
        var p1b0 = null, p1b8 = null;
        try { p1b0 = c.add(0x1b0).readPointer(); } catch (e) {}
        try { p1b8 = c.add(0x1b8).readPointer(); } catch (e) {}
        if (p1b8 && !p1b8.isNull() && p1b8.toString() !== '0xffffffffffffffff') {
            safeReadU8(p1b8.add(0x8),         "*(this+0x1b8)+0x8  finalize cVar7-B");
        } else if (p1b0 && !p1b0.isNull() && p1b0.toString() !== '0xffffffffffffffff') {
            safeReadPtr(p1b0.add(0x68),       "*(this+0x1b0)+0x68 finalize cVar7-A");
        }

        // listener-list-2 walk: *(this+0x220) is the array head; each
        // entry is 8 bytes containing a pointer.
        var llist2 = null;
        try { llist2 = c.add(0x220).readPointer(); } catch (e) {}
        if (llist2 && !llist2.isNull() && llist2.toString() !== '0xffffffffffffffff') {
            try {
                var n = c.add(0x228).readU32();
                console.log(prefix + "   listener-list-2: head=" + llist2 + " count=" + n);
                for (var k = 0; k < Math.min(n, 4); k++) {
                    safeReadPtr(llist2.add(k * 8), "  llist2[" + k + "] (entry ptr)");
                }
            } catch (e) {}
        }
    };


    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_captureFireDispatcher(): void
     *
     * Arms an Interceptor on FUN_14074ef20 (RVA 0x74ef20) — the natural
     * wave fire dispatcher. Each call to it represents the engine
     * deciding to fire some range of spawners (wave_manager, start,
     * end). Captures every (manager, start, end) tuple to
     * RW.SpawnerProbe._dispFires. The most recent is mirrored to
     * ._lastDisp.
     *
     * Usage:
     *   SpawnerProbe.expr_captureFireDispatcher()    // arm
     *   <walk to cauldron, activate naturally, wave fires>
     *   SpawnerProbe.expr_stopFireDispatcherCapture() // detach + summary
     *   SpawnerProbe.expr_replayLastDispatcher()      // re-fire same range
     *
     * Result: each fire logs "[expr_captureFireDispatcher] dispatch
     * #N manager=<ptr> start=<i> end=<j>".
     *
     * Caveats:
     *   - The dispatcher only fires spawners with +0x64 bit 3 clear.
     *     Replaying with the same (start, end) range AFTER they all
     *     fired naturally is a no-op — the gates inside the dispatcher
     *     skip consumed spawners.
     *   - However, replaying a wave's manager BEFORE all its waves have
     *     fired (i.e., the cauldron has multi-wave; we replay before
     *     wave-N fires) should produce wave-N enemies on demand.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   FUN_14074ef20 walks wave_manager->+0x68[start..end-1], for each
     *   spawner: checks parent-alive, settings condition (FUN_140-
     *   70adc0), vtable[26] permission, then routes by +0x64 flag bits.
     *   bit3=0 + bit2=0 → calls FUN_1406f62b0 (broadcast worker which
     *   dispatches vtable[28] = orchestrator). bit3=0 + bit2=1 → just
     *   counts. bit3=1 → cap-bounded count. So the dispatcher is the
     *   orchestrated entry point; calling it directly is the natural
     *   fire path.
     */
    SpawnerProbe.expr_captureFireDispatcher = function () {
        var prefix = "[SpawnerProbe.expr_captureFireDispatcher]";
        if (SpawnerProbe._dispHook) {
            try { SpawnerProbe._dispHook.detach(); } catch (e) {}
            SpawnerProbe._dispHook = null;
        }
        SpawnerProbe._dispFires = [];
        SpawnerProbe._lastDisp  = null;
        SpawnerProbe._dispHook = Interceptor.attach(IMG.add(FIRE_DISPATCHER_RVA), {
            onEnter: function (args) {
                try {
                    var mgr   = ptr(args[0]);
                    var start = args[1].toInt32() & 0xff;
                    var end   = args[2].toInt32() & 0xff;
                    var rec = {
                        ts:      Date.now(),
                        manager: mgr,
                        start:   start,
                        end:     end,
                        count:   end - start,
                    };
                    SpawnerProbe._dispFires.push(rec);
                    SpawnerProbe._lastDisp = rec;
                    console.log(prefix + " dispatch #" + SpawnerProbe._dispFires.length +
                                " manager=" + mgr +
                                " start=" + start + " end=" + end +
                                " count=" + (end - start));
                } catch (e) {
                    console.log(prefix + " onEnter EXC: " + e.message);
                }
            },
        });
        console.log(prefix + " armed at FUN_14074ef20 (RVA 0x" + FIRE_DISPATCHER_RVA.toString(16) + ")");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_stopFireDispatcherCapture(): void
     *
     * Detach the dispatcher hook armed by expr_captureFireDispatcher.
     * Prints summary of distinct managers seen and the (start, end)
     * tuples for each. Captured records remain in
     * RW.SpawnerProbe._dispFires.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_stopFireDispatcherCapture = function () {
        var prefix = "[SpawnerProbe.expr_stopFireDispatcherCapture]";
        if (!SpawnerProbe._dispHook) {
            console.log(prefix + " not armed");
            return;
        }
        try { SpawnerProbe._dispHook.detach(); } catch (e) {}
        SpawnerProbe._dispHook = null;
        var fires = SpawnerProbe._dispFires;
        var byMgr = {};
        fires.forEach(function (r) {
            var k = r.manager.toString();
            if (!byMgr[k]) byMgr[k] = [];
            byMgr[k].push(r);
        });
        console.log(prefix + " detached. " + fires.length + " dispatch(es) captured.");
        var keys = Object.keys(byMgr);
        console.log(prefix + " distinct managers: " + keys.length);
        keys.forEach(function (k) {
            var ranges = byMgr[k].map(function (r) {
                return "[" + r.start + "," + r.end + ")";
            });
            console.log(prefix + "   " + k + "  x" + byMgr[k].length + "  ranges=" + ranges.join(","));
        });
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_armSpawnerCtor(): void
     *
     * Arms an Interceptor on FUN_1402d0ee0 (RVA 0x2d0ee0) — the
     * oCEntityCpntEntitySpawner constructor. Each spawner instance
     * created by the engine is captured into RW.SpawnerProbe._spawners
     * regardless of whether it ever fires. **This is the right hook
     * for catching the cauldron's UNFIRED wave spawners** (the wave/
     * orchestrator hooks only see spawners after they've fired and
     * are consumed; the ctor sees them at creation, before the lockout
     * flag is set).
     *
     * Workflow:
     *   loadMod("spawner_probe")
     *   SpawnerProbe.expr_armSpawnerCtor()    // arm BEFORE reload
     *   <reload chapter — chapter-load creates all spawners; hook captures them>
     *   loadMod("cauldron_test")
     *   CauldronTest.start()
     *   SpawnerProbe.expr_summonAtPlayer(opts?)   // ★ ONE call
     *
     * Caveats:
     *   - Must be armed BEFORE chapter load. Arming after the chapter
     *     has loaded misses every spawner that was created during load.
     *     Only matters if a future chapter feature creates spawners
     *     post-load (none observed yet, but stay aware).
     *   - Hook overhead is per-creation, not per-frame. Cheap.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_armSpawnerCtor = function () {
        var prefix = "[SpawnerProbe.expr_armSpawnerCtor]";
        if (SpawnerProbe._ctorHook) {
            try { SpawnerProbe._ctorHook.detach(); } catch (e) {}
            SpawnerProbe._ctorHook = null;
        }
        SpawnerProbe._spawners = [];
        SpawnerProbe._ctorHook = Interceptor.attach(IMG.add(SPAWNER_CTOR_RVA), {
            onEnter: function (args) {
                try {
                    SpawnerProbe._spawners.push({ ts: Date.now(), ptr: ptr(args[0]) });
                } catch (e) {}
            },
        });
        console.log(prefix + " armed at FUN_1402d0ee0 (RVA 0x" + SPAWNER_CTOR_RVA.toString(16) +
                    "). Reload chapter to populate.");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_stopSpawnerCtor(): void
     *
     * Detach the spawner-ctor hook. Captured records remain in
     * RW.SpawnerProbe._spawners.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_stopSpawnerCtor = function () {
        if (!SpawnerProbe._ctorHook) {
            console.log("[SpawnerProbe.expr_stopSpawnerCtor] not armed");
            return;
        }
        try { SpawnerProbe._ctorHook.detach(); } catch (e) {}
        SpawnerProbe._ctorHook = null;
        console.log("[SpawnerProbe.expr_stopSpawnerCtor] detached. " +
                    SpawnerProbe._spawners.length + " spawner(s) captured.");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_listSpawners(opts?): array
     *
     * List captured spawner instances with their settings name + flag
     * state, optionally filtered.
     *
     * opts.unfiredOnly: if true, show only spawners with bit 3 of
     *   +0x64 clear (i.e. not yet fired this chapter).
     * opts.nameMatch:   case-insensitive substring against settings
     *   display name. Useful for "cauldron" / "camp" / etc.
     *
     * Returns the filtered array of records, each: { ptr, settings,
     * settingsName, parent, flags, unfired }.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_listSpawners = function (opts) {
        var prefix = "[SpawnerProbe.expr_listSpawners]";
        var unfiredOnly = !!(opts && opts.unfiredOnly);
        var nameMatch   = (opts && opts.nameMatch) ? String(opts.nameMatch).toLowerCase() : null;
        var posNear     = (opts && opts.posNear) ? opts.posNear : null;
        var maxPrint    = (opts && typeof opts.max === 'number') ? opts.max : 50;

        var rows = [];
        SpawnerProbe._spawners.forEach(function (rec) {
            var sp = rec.ptr;
            var settings = null, name = null, parent = null, flags = 0;
            var parentLoc = null, parentName = null;
            try { settings = sp.add(0x10).readPointer(); } catch (e) {}
            try { parent   = sp.add(0x08).readPointer(); } catch (e) {}
            try { flags    = sp.add(0x64).readU8(); } catch (e) {}
            if (settings && !settings.isNull() && settings.toString() !== '0xffffffffffffffff') {
                name = readSettingsName(settings);
            }
            if (parent && !parent.isNull() && parent.toString() !== '0xffffffffffffffff') {
                try {
                    var p3 = parent.add(0x324);
                    parentLoc = { x: p3.readFloat(), y: p3.add(4).readFloat(), z: p3.add(8).readFloat() };
                } catch (e) {}
                // Parent entity's oCEntitySettings* lives at +0x28; its display
                // name uses the standard asset-cache layout (+0x08 char*,
                // +0x10 u32 length). This is stable across launches — settings
                // assets are baked, only their heap address randomizes.
                try {
                    var pSettings = parent.add(0x28).readPointer();
                    if (pSettings && !pSettings.isNull() &&
                        pSettings.toString() !== '0xffffffffffffffff') {
                        parentName = readSettingsName(pSettings);
                    }
                } catch (e) {}
            }
            var unfired = (flags & 8) === 0;
            rows.push({
                ptr: sp, settings: settings, settingsName: name,
                parent: parent, parentLoc: parentLoc, parentName: parentName,
                flags: flags, unfired: unfired,
            });
        });

        var visible = rows;
        if (unfiredOnly) visible = visible.filter(function (r) { return r.unfired; });
        if (nameMatch)   visible = visible.filter(function (r) {
            // Match against either the spawner's settings name (rarely populated
            // for components) or the parent entity's settings name (stable, the
            // useful one for cross-session ID).
            var hay = ((r.settingsName || "") + " " + (r.parentName || "")).toLowerCase();
            return hay.indexOf(nameMatch) >= 0;
        });
        if (posNear) {
            visible = visible.filter(function (r) {
                if (!r.parentLoc) return false;
                var dx = r.parentLoc.x - posNear.x;
                var dy = r.parentLoc.y - posNear.y;
                var dz = r.parentLoc.z - posNear.z;
                return (dx*dx + dy*dy + dz*dz) <= (posNear.radius * posNear.radius);
            });
            // Sort by distance ascending so closest are listed first.
            visible.sort(function (a, b) {
                var da = Math.pow(a.parentLoc.x - posNear.x, 2) +
                         Math.pow(a.parentLoc.y - posNear.y, 2) +
                         Math.pow(a.parentLoc.z - posNear.z, 2);
                var db = Math.pow(b.parentLoc.x - posNear.x, 2) +
                         Math.pow(b.parentLoc.y - posNear.y, 2) +
                         Math.pow(b.parentLoc.z - posNear.z, 2);
                return da - db;
            });
        }

        var label = "";
        if (unfiredOnly) label += " unfired-only";
        if (nameMatch)   label += " name~\"" + nameMatch + "\"";
        if (posNear)     label += " near=(" + posNear.x.toFixed(1) + "," + posNear.y.toFixed(1) + "," +
                                  posNear.z.toFixed(1) + ") r=" + posNear.radius;
        console.log(prefix + " " + visible.length + " / " + rows.length +
                    " spawner(s)" + label + ":");
        visible.slice(0, maxPrint).forEach(function (r, i) {
            var nm  = r.settingsName ? "\"" + r.settingsName + "\"" : "<no name>";
            var pnm = r.parentName   ? " parentName=\"" + r.parentName + "\"" : "";
            var st = r.unfired ? "UNFIRED" : "consumed";
            var loc = r.parentLoc
                ? " parent@(" + r.parentLoc.x.toFixed(1) + "," + r.parentLoc.y.toFixed(1) + "," +
                  r.parentLoc.z.toFixed(1) + ")"
                : " parent@?";
            console.log(prefix + "   [" + i + "] " + r.ptr +
                        "  flags=0x" + r.flags.toString(16) +
                        "  " + st + loc + "  " + nm + pnm);
        });
        if (visible.length > maxPrint) {
            console.log(prefix + "   ... +" + (visible.length - maxPrint) + " more (use opts.max to raise)");
        }
        return visible;
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_summonAtPlayer(opts?): record | null
     *
     * UNVERIFIED PRIMITIVE — research only. The "summon-at-me" play:
     * picks an unfired spawner, warps its parent entity to the player's
     * current position, then fires the spawner via FUN_1406f62b0. The
     * orchestrator reads the spawn location from the spawner's bound
     * transform — typically tied to the parent's position — so warping
     * the parent moves the spawn site to the player.
     *
     * opts.nameMatch:  pick the first unfired spawner whose settings
     *   name matches this substring (case-insensitive). Default: any
     *   unfired spawner.
     * opts.index:      use this index from the filtered list (default 0).
     * opts.dryRun:     if true, prints what would be done but doesn't
     *   actually warp or fire. Useful sanity check.
     *
     * Prerequisites:
     *   - expr_armSpawnerCtor() armed BEFORE the chapter loaded.
     *   - RW.Player captured (RW.Player.refresh() — happens in
     *     CauldronTest.start automatically).
     *   - RW.Transporter loaded (auto-loaded by CauldronTest.start).
     *
     * Result: returns the spawner record on success, null on failure
     * (no captures, no match, prereqs missing, native call threw).
     *
     * Caveats:
     *   - Same general crash risk as any expr_*. The +0x108 I/O queue
     *     state may not be ready on a freshly-ctor'd spawner; if so,
     *     fire crashes. Save the run before invoking.
     *   - Warping the parent moves the WHOLE entity, not just the
     *     spawn site. Reset Transporter afterwards if needed.
     *   - Spawn target's bound transform mode (settings+0x1bc) may
     *     route to a different transform source — warping the parent
     *     might not move the spawn if mode != "use parent position".
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_summonAtPlayer = function (opts) {
        var prefix = "[SpawnerProbe.expr_summonAtPlayer]";
        var nameMatch     = (opts && opts.nameMatch) ? String(opts.nameMatch).toLowerCase() : null;
        var idx           = (opts && typeof opts.index === 'number') ? opts.index : 0;
        var dryRun        = !!(opts && opts.dryRun);
        var posNear       = (opts && opts.posNear) ? opts.posNear : null;
        var nearEntity    = (opts && opts.nearEntity) ? String(opts.nearEntity) : null;
        var nearRadius    = (opts && typeof opts.nearRadius === 'number') ? opts.nearRadius : 10;
        var noWarp        = !!(opts && opts.noWarp);

        if (!SpawnerProbe._spawners.length) {
            console.log(prefix + " no captures — call expr_armSpawnerCtor before reloading the chapter");
            return null;
        }

        // Resolve nearEntity shortcut → posNear from the named entity's location.
        if (nearEntity && !posNear) {
            if (!RW.Entity || typeof RW.Entity.find !== 'function') {
                console.log(prefix + " RW.Entity missing — cannot resolve \"" + nearEntity + "\"");
                return null;
            }
            var anchor = RW.Entity.find(nearEntity);
            if (anchor === undefined) {
                console.log(prefix + " scene_manager not captured yet — play one frame, retry");
                return null;
            }
            if (!anchor) {
                console.log(prefix + " no entity matches \"" + nearEntity + "\"");
                return null;
            }
            posNear = { x: anchor.loc.x, y: anchor.loc.y, z: anchor.loc.z, radius: nearRadius };
            console.log(prefix + " nearEntity \"" + anchor.name + "\": " + anchor.entity +
                        " loc=(" + anchor.loc.x.toFixed(1) + "," + anchor.loc.y.toFixed(1) + "," +
                        anchor.loc.z.toFixed(1) + ") radius=" + nearRadius);
        }

        var candidates = SpawnerProbe.expr_listSpawners({
            unfiredOnly: true,
            nameMatch:   nameMatch,
            posNear:     posNear,
            max:         50,
        });
        if (!candidates.length) {
            console.log(prefix + " no unfired spawners match the filter");
            return null;
        }
        if (idx < 0 || idx >= candidates.length) {
            console.log(prefix + " index " + idx + " out of range (have " + candidates.length + ")");
            return null;
        }
        var rec = candidates[idx];
        console.log(prefix + " selected: " + rec.ptr +
                    " (" + (rec.settingsName || "<no name>") + ")");

        var p = null;
        if (!noWarp) {
            if (!RW.Player || !RW.Player.loc) {
                console.log(prefix + " RW.Player not captured — call RW.Player.refresh() and play one frame first" +
                            " (or pass noWarp: true to fire without warping)");
                return null;
            }
            p = RW.Player.loc;
        }

        if (!noWarp && (!RW.Transporter || typeof RW.Transporter.warpEntity !== 'function')) {
            console.log(prefix + " RW.Transporter not loaded — call loadPower(\"Transporter\") first " +
                        "(or pass noWarp: true to skip warp)");
            return null;
        }

        // Warp the spawner's parent to the player position. Use vtable[10]
        // setPosition directly on the parent entity since we have its ptr.
        if (!noWarp && (!rec.parent || rec.parent.isNull())) {
            console.log(prefix + " spawner has no parent (+0x08) — cannot warp");
            return null;
        }

        if (dryRun) {
            var dryAction = noWarp
                ? " WITHOUT warp (noWarp=true)"
                : " then warp parent " + rec.parent + " to (" +
                  p.x.toFixed(1) + "," + p.y.toFixed(1) + "," + p.z.toFixed(1) + ")";
            console.log(prefix + " DRY RUN: would call FUN_1406f62b0(" + rec.ptr + ")" + dryAction);
            return rec;
        }

        // Optional: warp parent to player position. Skipped when noWarp=true
        // (e.g., to fire the hourglass reward without moving the hourglass).
        if (!noWarp) {
            try {
                var vt = rec.parent.readPointer();
                var setPosFn = new NativeFunction(vt.add(0x50).readPointer(), 'pointer', ['pointer', 'pointer']);
                var buf = Memory.alloc(12);
                buf.writeFloat(p.x); buf.add(4).writeFloat(p.y); buf.add(8).writeFloat(p.z);
                setPosFn(rec.parent, buf);
                console.log(prefix + " warped parent " + rec.parent +
                            " to (" + p.x.toFixed(1) + "," + p.y.toFixed(1) + "," + p.z.toFixed(1) + ")");
            } catch (e) {
                console.log(prefix + " warp failed: " + e.message);
                return null;
            }
        } else {
            console.log(prefix + " noWarp: parent stays at " + rec.parent);
        }

        try {
            holderFireActiveFn(rec.ptr);
            console.log(prefix + " fired FUN_1406f62b0(" + rec.ptr + ")" +
                        (noWarp ? " — spawn at parent's natural position" : " — watch for spawn at player"));
        } catch (e) {
            console.log(prefix + " fire threw: " + e.message);
            return null;
        }

        return rec;
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_listWaveManagers(opts?): array
     *
     * Groups every captured spawner (from expr_armSpawnerCtor) by its
     * +0x08 parent. Each unique parent is a candidate wave_manager —
     * an entity that owns a stable array of spawners at its +0x68
     * (the same array FUN_14074ef20's natural fire dispatcher walks).
     *
     * The grouped order = the asset-defined order, NOT the ctor
     * capture order. This is what makes "wave_manager parentName +
     * spawner sub-index" a stable ID across chapter reloads — the
     * asset bakes in which spawner is at which position in the
     * manager's array.
     *
     * opts.nameMatch: filter by parentName substring (case-insensitive).
     *
     * Result: prints one line per wave_manager candidate with its name,
     * position, and spawner count. Returns an array of records:
     *   { parent, parentName, parentLoc, spawners: [{ ptr, flags, ... }] }
     *
     * Usage:
     *   SpawnerProbe.expr_listWaveManagers({ nameMatch: "cauldron" })
     *   SpawnerProbe.expr_listWaveManagers({ nameMatch: "snake" })
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_listWaveManagers = function (opts) {
        var prefix = "[SpawnerProbe.expr_listWaveManagers]";
        var nameMatch    = (opts && opts.nameMatch) ? String(opts.nameMatch).toLowerCase() : null;
        var posNear      = (opts && opts.posNear) ? opts.posNear : null;
        var nearEntity   = (opts && opts.nearEntity) ? String(opts.nearEntity) : null;
        var nearRadius   = (opts && typeof opts.nearRadius === 'number') ? opts.nearRadius : 25;
        var minSpawners  = (opts && typeof opts.minSpawners === 'number') ? opts.minSpawners : 0;
        var maxSpawners  = (opts && typeof opts.maxSpawners === 'number') ? opts.maxSpawners : Infinity;
        var unfiredOnly  = !!(opts && opts.unfiredOnly);
        var maxPrint     = (opts && typeof opts.max === 'number') ? opts.max : 50;

        // Resolve nearEntity shortcut.
        if (nearEntity && !posNear && RW.Entity && RW.Entity.find) {
            var anchor = RW.Entity.find(nearEntity);
            if (anchor) {
                posNear = { x: anchor.loc.x, y: anchor.loc.y, z: anchor.loc.z, radius: nearRadius };
                console.log(prefix + " nearEntity \"" + anchor.name + "\": (" +
                            anchor.loc.x.toFixed(1) + "," + anchor.loc.y.toFixed(1) + "," +
                            anchor.loc.z.toFixed(1) + ") radius=" + nearRadius);
            }
        }

        // Group by parent.
        var byParent = {};
        SpawnerProbe._spawners.forEach(function (rec) {
            var sp = rec.ptr;
            var parent = null;
            try { parent = sp.add(0x08).readPointer(); } catch (e) { return; }
            if (!parent || parent.isNull() ||
                parent.toString() === '0xffffffffffffffff') return;
            var k = parent.toString();
            if (!byParent[k]) {
                var pName = null, pLoc = null;
                try {
                    var pSettings = parent.add(0x28).readPointer();
                    if (pSettings && !pSettings.isNull() &&
                        pSettings.toString() !== '0xffffffffffffffff') {
                        pName = readSettingsName(pSettings);
                    }
                } catch (e) {}
                try {
                    var pp = parent.add(0x324);
                    pLoc = { x: pp.readFloat(), y: pp.add(4).readFloat(), z: pp.add(8).readFloat() };
                } catch (e) {}
                byParent[k] = { parent: parent, parentName: pName, parentLoc: pLoc, spawners: [] };
            }
            var flags = 0;
            try { flags = sp.add(0x64).readU8(); } catch (e) {}
            byParent[k].spawners.push({
                ptr: sp, flags: flags, unfired: (flags & 8) === 0,
            });
        });

        var groups = [];
        Object.keys(byParent).forEach(function (k) { groups.push(byParent[k]); });
        if (nameMatch) {
            groups = groups.filter(function (g) {
                return g.parentName && g.parentName.toLowerCase().indexOf(nameMatch) >= 0;
            });
        }
        if (posNear) {
            groups = groups.filter(function (g) {
                if (!g.parentLoc) return false;
                var dx = g.parentLoc.x - posNear.x;
                var dy = g.parentLoc.y - posNear.y;
                var dz = g.parentLoc.z - posNear.z;
                return (dx*dx + dy*dy + dz*dz) <= (posNear.radius * posNear.radius);
            });
        }
        if (minSpawners > 0 || maxSpawners < Infinity) {
            groups = groups.filter(function (g) {
                return g.spawners.length >= minSpawners && g.spawners.length <= maxSpawners;
            });
        }
        if (unfiredOnly) {
            groups = groups.filter(function (g) {
                return g.spawners.some(function (s) { return s.unfired; });
            });
        }
        // Sort: nearest-to-posNear first if set, else largest groups first.
        if (posNear) {
            groups.sort(function (a, b) {
                var da = Math.pow(a.parentLoc.x - posNear.x, 2) +
                         Math.pow(a.parentLoc.y - posNear.y, 2) +
                         Math.pow(a.parentLoc.z - posNear.z, 2);
                var db = Math.pow(b.parentLoc.x - posNear.x, 2) +
                         Math.pow(b.parentLoc.y - posNear.y, 2) +
                         Math.pow(b.parentLoc.z - posNear.z, 2);
                return da - db;
            });
        } else {
            groups.sort(function (a, b) {
                if (b.spawners.length !== a.spawners.length) return b.spawners.length - a.spawners.length;
                return (a.parentName || "").localeCompare(b.parentName || "");
            });
        }

        var label = "";
        if (nameMatch)        label += " name~\"" + nameMatch + "\"";
        if (posNear)          label += " near=(" + posNear.x.toFixed(1) + "," + posNear.y.toFixed(1) + "," +
                                       posNear.z.toFixed(1) + ") r=" + posNear.radius;
        if (unfiredOnly)      label += " unfiredOnly";
        if (minSpawners > 0)  label += " min=" + minSpawners;
        if (maxSpawners < Infinity) label += " max=" + maxSpawners;
        console.log(prefix + " " + groups.length + " wave_manager candidate(s)" + label);
        groups.slice(0, maxPrint).forEach(function (g, i) {
            var loc = g.parentLoc
                ? "(" + g.parentLoc.x.toFixed(1) + "," + g.parentLoc.y.toFixed(1) + "," +
                  g.parentLoc.z.toFixed(1) + ")"
                : "?";
            var nm = g.parentName ? "\"" + g.parentName + "\"" : "<no name>";
            var unfired = g.spawners.filter(function (s) { return s.unfired; }).length;
            console.log(prefix + "   [" + i + "] " + g.parent + "  " + nm +
                        "  pos=" + loc +
                        "  spawners=" + g.spawners.length + " (" + unfired + " unfired)");
        });
        if (groups.length > maxPrint) {
            console.log(prefix + "   ... +" + (groups.length - maxPrint) + " more (use opts.max to raise)");
        }
        return groups;
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_lockToPlayer(spawnerPtr: NativePointer, opts?): void
     *
     * UNVERIFIED PRIMITIVE — research only. Locks a captured spawner
     * to the player: every `intervalMs` ms, warp the spawner's parent
     * entity to the player's current position, then fire the spawner
     * via FUN_1406f62b0. Persists until expr_unlock() is called.
     *
     * spawnerPtr: NativePointer to the spawner instance (from
     *   expr_listSpawners output, e.g. ptr("0x26f650efec0")).
     *
     * opts.intervalMs: tick interval in ms (default 1000 = 1 sec).
     *
     * Usage:
     *   var bats = ptr("0x...");                // spawner ptr from list
     *   SpawnerProbe.expr_lockToPlayer(bats)    // bats follow you, fire each second
     *   <walk around — animation triggers at your feet on every tick>
     *   SpawnerProbe.expr_unlock()              // stop
     *
     * Caveats:
     *   - Heap-pointer-based: invalid after chapter reload. Re-resolve
     *     via expr_listSpawners({ nameMatch: "<parent name>" }).
     *   - Each fire warps the parent. If multiple things share that
     *     parent (e.g. cauldron itself), they ALL move with you.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_lockToPlayer = function (spawnerPtr, opts) {
        var prefix = "[SpawnerProbe.expr_lockToPlayer]";
        var intervalMs = (opts && typeof opts.intervalMs === 'number') ? opts.intervalMs : 1000;
        var noFire     = !!(opts && opts.noFire);

        if (!spawnerPtr) { console.log(prefix + " spawnerPtr required"); return null; }
        if (!RW.Player || !RW.Player.loc) { console.log(prefix + " RW.Player not captured"); return null; }

        if (SpawnerProbe._lockTimer) {
            try { clearInterval(SpawnerProbe._lockTimer); } catch (e) {}
            SpawnerProbe._lockTimer = null;
        }

        var parent = null;
        try { parent = spawnerPtr.add(0x08).readPointer(); } catch (e) {}
        if (!parent || parent.isNull()) {
            console.log(prefix + " spawner has no parent");
            return null;
        }
        var setPosFn = null;
        try {
            var vt = parent.readPointer();
            setPosFn = new NativeFunction(vt.add(0x50).readPointer(), 'pointer', ['pointer', 'pointer']);
        } catch (e) {
            console.log(prefix + " could not resolve parent setPosition: " + e.message);
            return null;
        }
        var buf = Memory.alloc(12);

        SpawnerProbe._lockTimer = setInterval(function () {
            try {
                var p = RW.Player.loc;
                if (!p) return;
                buf.writeFloat(p.x); buf.add(4).writeFloat(p.y); buf.add(8).writeFloat(p.z);
                setPosFn(parent, buf);
                if (!noFire) holderFireActiveFn(spawnerPtr);
            } catch (e) {
                console.log(prefix + " tick threw: " + e.message + " — stopping");
                try { clearInterval(SpawnerProbe._lockTimer); } catch (er) {}
                SpawnerProbe._lockTimer = null;
            }
        }, intervalMs);
        console.log(prefix + " locked spawner " + spawnerPtr +
                    " to player; " + (noFire ? "WARP-ONLY (no fire)" : "warp+fire") +
                    " every " + intervalMs + "ms. Call expr_unlock() to stop.");
    };

    /*
     * ----------------------------------------------------------------
     * SpawnerProbe.expr_unlock(): void
     *
     * Stop the lock-to-player timer started by expr_lockToPlayer.
     * No-op if not running.
     * ----------------------------------------------------------------
     */
    SpawnerProbe.expr_unlock = function () {
        if (!SpawnerProbe._lockTimer) {
            console.log("[SpawnerProbe.expr_unlock] no active lock");
            return;
        }
        try { clearInterval(SpawnerProbe._lockTimer); } catch (e) {}
        SpawnerProbe._lockTimer = null;
        console.log("[SpawnerProbe.expr_unlock] stopped");
    };

    RW.registerMod("spawner_probe", version);
    console.log("[SpawnerProbe] " + version + " loaded.");
    console.log("[SpawnerProbe]   inspect(name)                        — dump entity components + spawners");
    console.log("[SpawnerProbe]   survey(opts?)                        — walk encyclopedia for spawner anchors");
    console.log("[SpawnerProbe]   expr_armSpawnerCtor()                — hook FUN_1402d0ee0 (BEFORE chapter load!)");
    console.log("[SpawnerProbe]   expr_stopSpawnerCtor()               — detach + summary");
    console.log("[SpawnerProbe]   expr_listSpawners(opts?)             — list captured spawners (filterable)");
    console.log("[SpawnerProbe]   expr_listWaveManagers(opts?)         — group captured spawners by parent");
    console.log("[SpawnerProbe]   expr_summonAtPlayer(opts?)           — ★ pick unfired spawner, warp+fire (or noWarp)");
    console.log("[SpawnerProbe]   expr_lockToPlayer(ptr, opts?)        — periodic warp+fire (use noFire:true for safe follow)");
    console.log("[SpawnerProbe]   expr_unlock()                        — stop expr_lockToPlayer");
    console.log("[SpawnerProbe]   --- diagnostic hooks (rare use) ---");
    console.log("[SpawnerProbe]   expr_captureWaveTrigger() / expr_stopWaveCapture()           — orchestrator hook");
    console.log("[SpawnerProbe]   expr_captureFireDispatcher() / expr_stopFireDispatcherCapture()  — dispatcher hook");
    console.log("[SpawnerProbe]   expr_inspectLastWave()               — dump captured wave-context fields");
    console.log("[SpawnerProbe]   candidates: " + SpawnerProbe.candidates.join(", "));
})();

// Top-level alias for REPL convenience
var SpawnerProbe = RW.SpawnerProbe;
