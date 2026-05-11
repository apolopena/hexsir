// Registry.js — persist the universal entity-ctor stream to disk.
//
// Hooks oCEntity::ctor at RVA 0x6c96f0 (per spawn_capture.js header:
// every oCEntity-derived class's ctor chains through this — pigs, props,
// anchors, items, anything). Buffers (entity_ptr, settings_ptr, t) at
// hook time; reads RTTI / settings name / position lazily at flush time
// when derived ctors and async streaming have completed.
//
// Output: rw/ref/registry/ctor/ctor-<YYYYMMDD-HHMMSS>.jsonl, one JSON
// record per line. First line is a meta record with start time + image
// base. Subsequent lines are ctor records.
//
// Usage:
//   loadUtil("Registry")
//   Registry.start()             // arms hook, opens file
//   <reload chapter>             // captures everything during load
//   Registry.flush()             // write buffered records to disk
//   Registry.stop()              // detach + close
//   Registry.path()              // current dump path
//   Registry.size()              // { buffered, written }
//
// SETUP-BOUND: arm BEFORE the chapter (or game) start whose ctors you
// want captured — the hook attaches now, captures only fire on future
// ctor invocations.
//
// Composition with spawn_capture.js: both hook the same RVA. Loading
// both doubles the per-ctor cost but they don't collide. Pick one for
// any given session unless you specifically want both surfaces.

(function () {
    'use strict';

    var version = "0.1.0";

    var rwMod = Process.findModuleByName('Ravenswatch.exe');
    if (!rwMod) { console.log('[Registry] FATAL: no Ravenswatch.exe'); return; }
    var IMG     = rwMod.base;
    var IMG_END = IMG.add(rwMod.size);

    var ENTITY_CTOR_RVA = 0x6c96f0;
    var ENTITY_POS_OFF  = 0x324;
    var FLUSH_THRESHOLD = 500;        // auto-flush after N buffered records

    // Derive dump dir from FRIDA_DIR (//wsl.localhost/Void/.../tools/frida).
    var REPO_ROOT = (RW.FRIDA_DIR || '').replace(/\/tools\/frida\/?$/, '');
    var DUMP_DIR  = REPO_ROOT + '/rw/ref/registry/ctor';

    if (!RW.Registry) RW.Registry = {};
    var Registry = RW.Registry;

    // Re-load safe state. Preserve across re-eval.
    Registry._hook    = Registry._hook    || null;
    Registry._buf     = Registry._buf     || [];   // [{ t, p, s }, ...]
    Registry._file    = Registry._file    || null; // open File handle, or null
    Registry._path    = Registry._path    || null;
    Registry._t0      = Registry._t0      || 0;    // start ms
    Registry._written = Registry._written || 0;
    Registry._dropped = Registry._dropped || 0;    // ctor calls that hit the buffer cap (none today; reserved)

    // ---- helpers ---------------------------------------------------

    function inImage(p) {
        try { return p.compare(IMG) >= 0 && p.compare(IMG_END) < 0; }
        catch (e) { return false; }
    }

    function readRtti(entity) {
        try {
            var vt   = entity.readPointer();
            if (!inImage(vt)) return null;
            var col  = vt.sub(8).readPointer();
            var tdRva   = col.add(0x0c).readU32();
            var selfRva = col.add(0x14).readU32();
            var imgBase = col.sub(selfRva);
            return imgBase.add(tdRva).add(0x10).readCString();
        } catch (e) { return null; }
    }

    function readSettingsName(settings) {
        try {
            if (!settings || settings.isNull()) return null;
            var strPtr = settings.add(0x08).readPointer();
            var len    = settings.add(0x10).readU32();
            if (len <= 0 || len > 512) return null;
            return strPtr.readUtf8String(len);
        } catch (e) { return null; }
    }

    function readPos(entity) {
        try {
            var p = entity.add(ENTITY_POS_OFF);
            return [p.readFloat(), p.add(4).readFloat(), p.add(8).readFloat()];
        } catch (e) { return null; }
    }

    function tsCompact(d) {
        function pad(n) { return n < 10 ? '0' + n : '' + n; }
        return d.getFullYear() +
               pad(d.getMonth() + 1) +
               pad(d.getDate()) + '-' +
               pad(d.getHours()) +
               pad(d.getMinutes()) +
               pad(d.getSeconds());
    }

    function openFile() {
        var name = 'ctor-' + tsCompact(new Date()) + '.jsonl';
        var path = DUMP_DIR + '/' + name;
        var f;
        try { f = new File(path, 'w'); }
        catch (e) {
            console.log('[Registry] FATAL: cannot open ' + path + ' — ' + e.message);
            console.log('[Registry] make sure dir exists: mkdir -p rw/ref/registry/ctor');
            return null;
        }
        var meta = {
            meta:    true,
            version: version,
            start:   new Date().toISOString(),
            imgBase: IMG.toString(),
            ctorRva: '0x' + ENTITY_CTOR_RVA.toString(16),
        };
        try { f.write(JSON.stringify(meta) + '\n'); f.flush(); }
        catch (e) { console.log('[Registry] meta-write failed: ' + e.message); }
        Registry._file = f;
        Registry._path = path;
        Registry._t0   = Date.now();
        return f;
    }

    function closeFile() {
        if (!Registry._file) return;
        try { Registry._file.flush(); Registry._file.close(); } catch (e) {}
        Registry._file = null;
    }

    // Drain the buffer to disk. Reads lazy fields per record. Stale
    // entries (entity already destroyed) get rtti=name=pos=null and
    // a `stale: true` tag.
    function flushBuf() {
        if (!Registry._file) return 0;
        var n = Registry._buf.length;
        if (n === 0) return 0;
        var buf = Registry._buf;
        Registry._buf = [];
        var lines = [];
        for (var i = 0; i < n; i++) {
            var rec  = buf[i];
            var rtti = readRtti(rec.p);
            var name = readSettingsName(rec.s);
            var pos  = readPos(rec.p);
            var stale = (rtti === null && name === null && pos === null);
            var out = {
                t:        rec.t,
                ptr:      rec.p.toString(),
                settings: rec.s ? rec.s.toString() : null,
                rtti:     rtti,
                name:     name,
                pos:      pos,
            };
            if (stale) out.stale = true;
            lines.push(JSON.stringify(out));
        }
        try {
            Registry._file.write(lines.join('\n') + '\n');
            Registry._file.flush();
            Registry._written += n;
        } catch (e) {
            console.log('[Registry] write failed (' + n + ' records dropped): ' + e.message);
        }
        return n;
    }

    // ---- public API ------------------------------------------------

    /*
     * ----------------------------------------------------------------
     * Registry.start(): void
     *
     * Open a fresh dump file and arm the ctor hook. Idempotent — calling
     * twice closes the prior file and re-arms.
     *
     * Result:
     *   - Creates rw/ref/registry/ctor/ctor-<YYYYMMDD-HHMMSS>.jsonl
     *   - Writes a meta record as line 1
     *   - Logs "[Registry] armed → <path>"
     *
     * Caveat: SETUP-BOUND. The hook captures only ctors fired AFTER it
     * arms. Load this util before reloading the chapter you want
     * captured.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Interceptor.attach on RVA 0x6c96f0 (oCEntity::ctor). onEnter
     *   pushes { t, p: args[0], s: args[1] } into _buf — minimal hot-
     *   path work. Auto-flushes when _buf hits FLUSH_THRESHOLD (500).
     *   Lazy reads (RTTI, settings name, position) happen at flush
     *   time, when derived ctors and async streaming have completed.
     */
    Registry.start = function () {
        Registry.stop();
        if (!openFile()) return;
        Registry._hook = Interceptor.attach(IMG.add(ENTITY_CTOR_RVA), {
            onEnter: function (args) {
                Registry._buf.push({
                    t: Date.now() - Registry._t0,
                    p: ptr(args[0]),
                    s: ptr(args[1]),
                });
                if (Registry._buf.length >= FLUSH_THRESHOLD) flushBuf();
            },
        });
        console.log('[Registry] armed → ' + Registry._path);
    };

    /*
     * ----------------------------------------------------------------
     * Registry.stop(): void
     *
     * Detach the hook, flush buffered records, close the dump file.
     * Idempotent — safe to call when nothing is armed.
     *
     * Result: logs "[Registry] stopped — wrote N records to <path>".
     * ----------------------------------------------------------------
     */
    Registry.stop = function () {
        if (Registry._hook) {
            try { Registry._hook.detach(); } catch (e) {}
            Registry._hook = null;
        }
        var drained = 0;
        if (Registry._file) {
            drained = flushBuf();
            console.log('[Registry] stopped — wrote ' + Registry._written +
                        ' records to ' + Registry._path);
            closeFile();
        }
        return drained;
    };

    /*
     * ----------------------------------------------------------------
     * Registry.flush(): number
     *
     * Drain the in-memory buffer to disk without stopping the hook.
     * Returns the number of records written this call.
     *
     * Use mid-session to checkpoint a long capture. Auto-flush also
     * fires every 500 ctors, so manual flush is mostly for taking a
     * deliberate snapshot at a known game state.
     * ----------------------------------------------------------------
     */
    Registry.flush = function () {
        var n = flushBuf();
        console.log('[Registry] flushed ' + n + ' records (' +
                    Registry._written + ' total) → ' + Registry._path);
        return n;
    };

    /*
     * ----------------------------------------------------------------
     * Registry.path(): string | null
     *
     * Current dump file path, or null if no capture is open.
     * ----------------------------------------------------------------
     */
    Registry.path = function () { return Registry._path; };

    /*
     * ----------------------------------------------------------------
     * Registry.size(): { armed, buffered, written, path }
     *
     * Snapshot of capture state — whether hook is armed, how many
     * records are buffered in memory, how many have been written to
     * disk, and the dump path.
     * ----------------------------------------------------------------
     */
    Registry.size = function () {
        return {
            armed:    Registry._hook !== null,
            buffered: Registry._buf.length,
            written:  Registry._written,
            path:     Registry._path,
        };
    };

    RW.registerMod("util:Registry", version);
    console.log("[Registry] " + version + " loaded — call Registry.start() before chapter reload");
    console.log("[Registry]   start()    — open dump file and arm oCEntity::ctor hook");
    console.log("[Registry]   stop()     — detach hook, flush, close file");
    console.log("[Registry]   flush()    — drain in-memory buffer to disk");
    console.log("[Registry]   path()     — current dump path");
    console.log("[Registry]   size()     — { armed, buffered, written, path }");
})();

// Top-level alias for REPL convenience.
var Registry = RW.Registry;
