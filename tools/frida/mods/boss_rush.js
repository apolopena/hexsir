// boss_rush.js v0.6 — fixes the entry-string reader.
// Settings entry strings are { char* ptr; u32 len; u32 cap }, not {begin,end}.
// Path is at +0x1d0 (not +0x1c0; +0x1c0 is the type tag like "EntitySettings").
//
// New surface (read-only / non-destructive until you call loadPrefabByPath):
//   findEncyclopedia(), dumpEncyclopedia(limit), findEntitySettings(name) — unchanged from v0.4.
//   captureNextResolution()        — arms a one-shot Interceptor on
//                                    oIEntity_resolveBoundPrefab_byIndex; the
//                                    next call captures (parent, slot, entry).
//   inspectLastResolution()        — prints the captured entry's +0x1c0 path
//                                    + secondary +0x1d0 + flags + bound handle.
//   loadPrefabByPath(pathStr)      — calls the prefab-loader's vtable[3] with
//                                    the given path. Returns a resource handle
//                                    or null. NOT YET DESTRUCTIVE — just loads
//                                    and refcounts; doesn't bind to anything.
//
// Test plan (no game-state mutation):
//   1) loadMod("boss_rush")
//   2) captureNextResolution()
//   3) forceBossSpawn()                   // triggers ~immediate resolveBoundPrefab call
//   4) inspectLastResolution()            // see what path the engine uses
//   5) loadPrefabByPath("<that path>")    // sanity — should match the captured handle
//   6) loadPrefabByPath("<chapter-2 path variant>")  // the gating test

(function () {
    var version = "0.8.0-spawner-trigger";

    // Read the engine's custom 16-byte string at `entry + offset`:
    //   +0x00: char* ptr
    //   +0x08: u32 length
    //   +0x0c: u32 capacity
    function readEntryString(entry, offset) {
        try {
            var p = entry.add(offset).readPointer();
            var len = entry.add(offset + 8).readU32();
            if (p.isNull() || len === 0 || len > 512) return null;
            return p.readUtf8String(len);
        } catch (e) { return null; }
    }
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[boss_rush] FATAL: Ravenswatch.exe not loaded"); return; }
    var imageBase = mod.base;

    if (!RW.bossRush) RW.bossRush = {};
    var br = RW.bossRush;
    br.imageBase = imageBase;

    br.addr = {
        encTypeTesterVftable:        imageBase.add(0xf536d0),
        sceneMgrFindByType:          imageBase.add(0x653f80),
        gTypeIdEnc:                  imageBase.add(0x1447c18),
        gGlobalTypeRegistryRoot:     imageBase.add(0x1446f38),
        gDefaultLoaderOptions:       imageBase.add(0x12c7590),
        resolveBoundPrefabByIndex:   imageBase.add(0x314e20),
        // Spawner-trigger surface (v0.8)
        scSpawnImpl:                 imageBase.add(0x6ef7c0),
        addSpawnedEntity:            imageBase.add(0x6db390),
        TYPE_ID_PREFAB_LOADER:       0x53b64d,
    };

    // ---- existing encyclopedia primitive (unchanged from v0.4) ----
    var typeTester = Memory.alloc(16);
    typeTester.writePointer(br.addr.encTypeTesterVftable);
    typeTester.add(8).writePointer(br.addr.gTypeIdEnc.readPointer());
    br.typeTester = typeTester;

    var sceneMgrFindByType = new NativeFunction(br.addr.sceneMgrFindByType,
        'pointer', ['pointer', 'pointer']);

    if (br.sceneMgrCapture) { try { br.sceneMgrCapture.detach(); } catch (e) {} }
    br.sceneMgrCapture = Interceptor.attach(br.addr.sceneMgrFindByType, {
        onEnter: function (args) {
            if (!br.sceneManager) {
                br.sceneManager = ptr(args[0]);
                console.log("[boss_rush] captured scene_manager = " + br.sceneManager);
            }
        }
    });

    br.findEncyclopedia = function () {
        if (!br.sceneManager) { console.log("[boss_rush] scene_manager not captured yet"); return null; }
        var enc = sceneMgrFindByType(br.sceneManager, typeTester);
        return enc.isNull() ? null : enc;
    };

    br.dumpEncyclopedia = function (limit) {
        var enc = br.findEncyclopedia();
        if (!enc) { console.log("[boss_rush] no encyclopedia"); return []; }
        var ctrl     = enc.add(0x28).readPointer();
        var entries  = enc.add(0x30).readPointer();
        var count    = enc.add(0x38).readU64().toNumber();
        var capMask  = enc.add(0x40).readU64().toNumber();
        var capacity = capMask + 1;
        console.log("[boss_rush] encyclopedia: count=" + count + " capacity=" + capacity);

        var out = [];
        for (var i = 0; i < capacity; i++) {
            var c = ctrl.add(i).readU8();
            if (c & 0x80) continue;
            var value = entries.add(i * 0x18).add(0x10).readPointer();
            if (value.isNull()) continue;
            var name;
            try {
                var strPtr = value.add(0x08).readPointer();
                var len    = value.add(0x10).readU32();
                if (len <= 0 || len > 512) continue;
                name = strPtr.readUtf8String(len);
            } catch (e) { continue; }
            out.push({ name: name, value: value });
            if (limit && out.length >= limit) break;
        }
        return out;
    };

    br.findEntitySettings = function (name) {
        var all = br.dumpEncyclopedia();
        for (var i = 0; i < all.length; i++) {
            if (all[i].name === name) return all[i].value;
        }
        return null;
    };

    // ---- path-based loader (NEW) ----
    // Walks g_global_type_registry_root, finds class with type-id 0x53b64d,
    // returns a NativeFunction wrapper for its vtable[3].
    function resolvePrefabLoader() {
        // The symbol holds a pointer to the registry struct; dereference once first.
        var reg = br.addr.gGlobalTypeRegistryRoot.readPointer();
        var entries = reg.add(0x30).readPointer();
        var count   = reg.add(0x38).readU32();
        for (var i = 0; i < count; i++) {
            var classPtr = entries.add(i * 8).readPointer();
            if (classPtr.isNull()) continue;
            var typeId = classPtr.add(8).readU32();
            if (typeId === br.addr.TYPE_ID_PREFAB_LOADER) {
                var loader = classPtr.add(0x10).readPointer();
                console.log("[boss_rush] prefab loader instance = " + loader);
                return loader;
            }
        }
        console.log("[boss_rush] prefab loader (type-id 0x53b64d) NOT FOUND in registry");
        return null;
    }

    br.loadPrefabByPath = function (pathStr) {
        var loader = resolvePrefabLoader();
        if (!loader) return null;
        var vtable = loader.readPointer();
        // Third arg: try as uint64 value (the qword AT 0x1412c7590 = 1 per dump),
        // not as the address. Decompile syntax `_DAT_1412c7590` (no &) implies value.
        var loadFn = new NativeFunction(vtable.add(0x18).readPointer(),
            'void', ['pointer', 'pointer', 'uint64', 'pointer', 'int']);

        var pathBuf = Memory.allocUtf8String(pathStr);
        var pathStruct = Memory.alloc(16);
        pathStruct.writePointer(pathBuf);            // +0x00: char* ptr
        pathStruct.add(8).writeU32(pathStr.length);  // +0x08: u32 length
        pathStruct.add(0xc).writeU32(pathStr.length);// +0x0c: u32 capacity

        var outHandle = Memory.alloc(16);            // 16 bytes; loader may write 2 qwords
        outHandle.writePointer(NULL);
        outHandle.add(8).writePointer(NULL);

        var configValue = br.addr.gDefaultLoaderOptions.readU64();

        try {
            loadFn(loader, pathStruct, configValue, outHandle, 0);
        } catch (e) {
            console.log("[boss_rush] loader call threw: " + e.message);
            return null;
        }
        var result = outHandle.readPointer();
        console.log("[boss_rush] loadPrefabByPath('" + pathStr + "') = " + result);
        return result;
    };

    // ---- resolveBoundPrefab capture, up to N calls (NEW) ----
    br.resolutions = [];
    br.captureResolutions = function (max) {
        max = max || 16;
        if (br.resolveCapture) { try { br.resolveCapture.detach(); } catch (e) {} }
        br.resolutions = [];
        console.log("[boss_rush] arming capture on resolveBoundPrefab (up to " + max + ", then auto-detach). Trigger with forceBossSpawn().");
        br.resolveCapture = Interceptor.attach(br.addr.resolveBoundPrefabByIndex, {
            onEnter: function (args) {
                if (br.resolutions.length >= max) {
                    try { br.resolveCapture.detach(); } catch (e) {}
                    br.resolveCapture = null;
                    return;
                }
                var parent = ptr(args[0]);
                var slotArg = args[1].toInt32() & 0xffff;
                var entryCount = 0;
                try { entryCount = parent.add(0x119 * 8).readU32(); } catch (e) {}
                var slot = (slotArg >= entryCount) ? 0 : slotArg;
                var entry = NULL;
                try {
                    var entriesArrayPtr = parent.add(0x118 * 8).readPointer();
                    entry = entriesArrayPtr.add(slot * 8).readPointer();
                } catch (e) {}
                br.resolutions.push({
                    idx: br.resolutions.length,
                    parent: parent,
                    slotArg: slotArg,
                    slotEffective: slot,
                    entry: entry,
                    when: Date.now(),
                });
            }
        });
    };

    br.listResolutions = function () {
        if (!br.resolutions.length) { console.log("[boss_rush] no resolutions captured yet"); return; }
        console.log("[boss_rush] " + br.resolutions.length + " resolution(s) captured:");
        for (var i = 0; i < br.resolutions.length; i++) {
            var r = br.resolutions[i];
            var typeTag = r.entry.isNull() ? "(?)" : (readEntryString(r.entry, 0x1c0) || "(?)");
            var path    = r.entry.isNull() ? "(?)" : (readEntryString(r.entry, 0x1d0) || "(?)");
            console.log("  [" + i + "] parent=" + r.parent + " slot=" + r.slotEffective +
                        " type='" + typeTag + "' path='" + path + "'");
        }
    };

    br.inspectResolution = function (idx) {
        idx = idx || 0;
        var r = br.resolutions[idx];
        if (!r) { console.log("[boss_rush] no resolution at index " + idx); return null; }
        console.log("[boss_rush] resolution[" + idx + "]");
        console.log("  parent           = " + r.parent);
        console.log("  slot (arg/eff)   = " + r.slotArg + " / " + r.slotEffective);
        console.log("  entry            = " + r.entry);
        try {
            console.log("  +0x1c0 type   = '" + (readEntryString(r.entry, 0x1c0) || "(?)") + "'");
            console.log("  +0x1d0 path   = '" + (readEntryString(r.entry, 0x1d0) || "(?)") + "'");
            console.log("  +0x1e0 loader = " + r.entry.add(0x1e0).readPointer());
            console.log("  +0x1e8 resolv = " + r.entry.add(0x1e8).readU8());
            console.log("  +0x1f0 handle = " + r.entry.add(0x1f0).readPointer());
        } catch (e) {
            console.log("  ERROR reading entry fields: " + e.message);
        }
        return r;
    };

    // ---- Spawner trigger surface (v0.8) ----
    if (!br.spawners) br.spawners = {};   // spawnerAddr (string) -> { addr, hits, lastEntity }

    if (br.spawnerHook) { try { br.spawnerHook.detach(); } catch (e) {} }
    br.spawnerHook = Interceptor.attach(br.addr.addSpawnedEntity, {
        onEnter: function (args) {
            var spawner = ptr(args[0]);
            var entity  = ptr(args[1]);
            var key = spawner.toString();
            if (!br.spawners[key]) {
                br.spawners[key] = { addr: spawner, hits: 0, lastEntity: NULL };
            }
            br.spawners[key].hits++;
            br.spawners[key].lastEntity = entity;
        }
    });

    var scSpawnFn = new NativeFunction(br.addr.scSpawnImpl, 'void', ['pointer']);

    br.listSpawners = function () {
        var keys = Object.keys(br.spawners);
        if (!keys.length) { console.log("[boss_rush] no spawners captured yet — walk into an enemy camp"); return []; }
        var out = [];
        keys.forEach(function (k, i) {
            var s = br.spawners[k];
            console.log("  [" + i + "] " + s.addr + " hits=" + s.hits + " lastEntity=" + s.lastEntity);
            out.push(s);
        });
        return out;
    };

    br.triggerSpawn = function (idx) {
        var keys = Object.keys(br.spawners);
        if (idx === undefined || idx < 0 || idx >= keys.length) {
            console.log("[boss_rush] usage: triggerSpawn(idx) — see listSpawners() for indices");
            return;
        }
        var s = br.spawners[keys[idx]];
        console.log("[boss_rush] triggerSpawn(" + idx + ") -> Sc_Spawn_impl(" + s.addr + ")");
        try {
            scSpawnFn(s.addr);
            console.log("[boss_rush] returned without crash");
        } catch (e) {
            console.log("[boss_rush] threw: " + e.message);
        }
    };

    br.spawnerInfo = function (idx) {
        var keys = Object.keys(br.spawners);
        if (idx === undefined || idx < 0 || idx >= keys.length) return null;
        var s = br.spawners[keys[idx]];
        try {
            console.log("spawner " + s.addr + ":");
            console.log("  +0x18  = " + s.addr.add(0x18).readPointer());
            console.log("  +0x160 = " + s.addr.add(0x160).readPointer() + " (must be 0 for Sc_Spawn_impl)");
            console.log("  +0x168 = 0x" + s.addr.add(0x168).readU8().toString(16));
            console.log("  +0x169 = 0x" + s.addr.add(0x169).readU8().toString(16));
        } catch (e) { console.log("err: " + e.message); }
        return s;
    };

    globalThis.listSpawners  = br.listSpawners;
    globalThis.triggerSpawn  = br.triggerSpawn;
    globalThis.spawnerInfo   = br.spawnerInfo;

    globalThis.findEncyclopedia    = br.findEncyclopedia;
    globalThis.dumpEncyclopedia    = br.dumpEncyclopedia;
    globalThis.findEntitySettings  = br.findEntitySettings;
    globalThis.captureResolutions  = br.captureResolutions;
    globalThis.listResolutions     = br.listResolutions;
    globalThis.inspectResolution   = br.inspectResolution;
    globalThis.loadPrefabByPath    = br.loadPrefabByPath;

    RW.registerMod("boss_rush", version);
    console.log("[boss_rush] " + version + " loaded");
    console.log("[boss_rush]   captureResolutions(16)        → arm hook, up to 16 calls");
    console.log("[boss_rush]   forceBossSpawn()              → trigger natural resolutions");
    console.log("[boss_rush]   listResolutions()             → list all captured (with paths)");
    console.log("[boss_rush]   inspectResolution(idx)        → full field dump for one entry");
    console.log("[boss_rush]   loadPrefabByPath('<path>')    → call path-based loader");
    console.log("[boss_rush]   listSpawners()                → spawners captured by addSpawnedEntity hook");
    console.log("[boss_rush]   spawnerInfo(idx)              → dump key fields of a captured spawner");
    console.log("[boss_rush]   triggerSpawn(idx)             → call Sc_Spawn_impl on captured spawner");
})();
