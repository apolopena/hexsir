// Ravenswatch — live-patch lab hub.
//
// rw_lab.js is the entry point. It owns the mod loader, the docstring
// parser, RW.help / RW.after / registerMod / status. Capability code
// lives in mods/powers/<Name>.js (loaded via loadPower) and
// mods/<name>.js (loaded via loadMod).
//
// Currently extracted to powers (load with loadPower("<Name>")):
//   ChapterBoss     — force chapter-end boss arrival
//   Currency        — global wallet writes (shards today)
//   SaveDiagnostic  — save-buffer probes (EXPERIMENTAL)
//   TalentPicker    — talent-picker seed forcing + diagnostics (PARTIALLY VERIFIED)
//   Teleport        — player teleport primitive
//
// Conventions are documented in tools/frida/CODE_STANDARDS.md. Read that
// first before adding capabilities.
//
// Reload semantics:
//   Edit a mod or power → loadMod("name") / loadPower("Name") again —
//   re-evals the file. Each capability's IIFE is idempotent: state is
//   preserved (`if (!RW.X) RW.X = {}`), prior hooks are detached and
//   re-armed without stacking.
//   Edit rw_lab.js → exit Frida and relaunch. The hub uses const at top
//   level and is not reload-safe via eval.

'use strict';

if (!globalThis.RW) globalThis.RW = {};
RW.FRIDA_DIR = '//wsl.localhost/Void/home/ks73/repos/work/ravensmith/tools/frida';
RW.mods = RW.mods || {};
RW.docs = RW.docs || {};   // "PowerName.method" -> docstring text (sig + body)

// Internal — eval an arbitrary absolute path into this script's scope.
// Used by loadMod and loadPower.
RW.loadFile = function (absPath) { (0, eval)(File.readAllText(absPath)); };

/*
 * ----------------------------------------------------------------
 * loadMod(name: string): void
 *
 * Load a research-grade mod from mods/<name>.js into the current scope.
 * Idempotent — re-load to pick up source edits.
 *
 * Result:
 *   The mod's IIFE runs; any RW.<...> namespaces it defines are now
 *   reachable. Re-runs RW.status() to log the registered mod set.
 * ----------------------------------------------------------------
 */
RW.loadMod = function (name) {
    RW.loadFile(RW.FRIDA_DIR + '/mods/' + name + '.js');
    RW.status();
};

/*
 * ----------------------------------------------------------------
 * loadPower(name: string): void
 *
 * Load a capability from mods/powers/<Name>.js, parse its fenced
 * docstrings into RW.docs (so help() picks them up), and run its IIFE.
 * Idempotent — re-load to pick up source edits.
 *
 * Result:
 *   RW.<Name> is populated with the power's API. help("<Name>") and
 *   help("<Name>.method") return the parsed docstrings. Powers
 *   register as "power:<Name>" in RW.mods.
 * ----------------------------------------------------------------
 * MECHANISM:
 *   Reads mods/powers/<name>.js, calls RW._parseDocs to extract
 *   docstrings (block comments with two `---` fences), merges those
 *   into RW.docs, then evals the source. Eval lands the IIFE in the
 *   script's global scope so the power can reference RW.* helpers.
 */
RW.loadPower = function (name) {
    var path = RW.FRIDA_DIR + '/mods/powers/' + name + '.js';
    var src = File.readAllText(path);
    var docs = RW._parseDocs(src);
    for (var k in docs) RW.docs[k] = docs[k];
    (0, eval)(src);
    RW.status();
};

// Parse fenced docstrings out of a source string. Convention defined
// in CODE_STANDARDS.md §The docstring contract:
//
//   /*
//    * ---------------------- (fence #1, opens help)
//    * Power.method(args): returnType
//    * ...prose body...
//    * ---------------------- (fence #2, closes help)
//    * MECHANISM: ...developer-only, not parsed
//    */
//
// A fence is a line whose contents (after stripping leading "* ") are
// 3+ dashes and nothing else. Block comments without two fence lines
// are ignored — that's how plain block comments and commented-out code
// stay invisible to help().
RW._parseDocs = function (src) {
    var out = {};
    var i = 0;
    var FENCE = /^-{3,}\s*$/;
    while (i < src.length) {
        var openIdx = src.indexOf('/*', i);
        if (openIdx < 0) break;
        var closeIdx = src.indexOf('*/', openIdx + 2);
        if (closeIdx < 0) break;
        var block = src.slice(openIdx + 2, closeIdx);
        i = closeIdx + 2;
        var lines = block.split('\n').map(function (l) {
            return l.replace(/^\s*\*?\s?/, '');
        });
        var fences = [];
        for (var j = 0; j < lines.length && fences.length < 2; j++) {
            if (FENCE.test(lines[j])) fences.push(j);
        }
        if (fences.length < 2) continue;          // not a parsed docstring
        var docLines = lines.slice(fences[0] + 1, fences[1]);
        var sigIdx = -1;
        for (var k = 0; k < docLines.length; k++) {
            if (docLines[k].trim().length > 0) { sigIdx = k; break; }
        }
        if (sigIdx < 0) continue;
        var sig = docLines[sigIdx].trim();
        var paren = sig.indexOf('(');
        var key = paren > 0 ? sig.slice(0, paren).trim() : sig;
        var body = docLines.slice(sigIdx + 1).join('\n').replace(/^\s+|\s+$/g, '');
        out[key] = sig + (body.length ? '\n' + body : '');
    }
    return out;
};

/*
 * ----------------------------------------------------------------
 * help(target?: string): void
 *
 * Terse REPL lookup of registered docstrings.
 *   help()                — list every loaded power and its methods
 *   help("Teleport")      — sig + one-line summary for each method
 *   help("Teleport.to")   — sig + one-line summary for that method
 *
 * Output is intentionally terse: the signature line and the first
 * non-blank prose line. For full prose, requirements, mechanism, and
 * caveats, read the source comment block.
 * ----------------------------------------------------------------
 */
RW.help = function (target) {
    function terse(text) {
        var lines = text.split('\n');
        var sig = lines[0];
        for (var i = 1; i < lines.length; i++) {
            if (lines[i].trim().length > 0) return sig + '\n  ' + lines[i].trim();
        }
        return sig;
    }

    var keys = Object.keys(RW.docs).sort();
    if (!keys.length) { console.log('[help] no docs registered'); return; }
    if (!target) {
        var byPower = {};
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var dot = k.indexOf('.');
            var p = dot > 0 ? k.slice(0, dot) : k;
            if (!byPower[p]) byPower[p] = [];
            byPower[p].push(k);
        }
        for (var pname in byPower) {
            console.log('\n=== ' + pname + ' ===');
            for (var j = 0; j < byPower[pname].length; j++) console.log('  ' + byPower[pname][j]);
        }
        console.log('\nhelp("Power") for one power, help("Power.method") for one entry.');
        return;
    }
    if (RW.docs[target]) {
        console.log('HELP TEXT:');
        console.log(terse(RW.docs[target]));
        return;
    }
    var matched = keys.filter(function (k) { return k.indexOf(target + '.') === 0; });
    if (matched.length) {
        console.log('HELP TEXT:');
        for (var m = 0; m < matched.length; m++) {
            console.log('\n' + terse(RW.docs[matched[m]]));
        }
        return;
    }
    console.log('[help] no docs for "' + target + '"');
};

/*
 * ----------------------------------------------------------------
 * RW.after(seconds: number, fn: () => void): number
 *
 * Shared wall-clock delay used by powers' delay<X> helpers. Validates
 * seconds (non-negative number) and fn (function), schedules via
 * setTimeout, returns the timeout handle. Each power's delay variant
 * is a one-liner around this — see CODE_STANDARDS.md §Delays.
 *
 * Not pause-aware: setTimeout fires on wall-clock regardless of game
 * state.
 * ----------------------------------------------------------------
 */
RW.after = function (seconds, fn) {
    if (typeof seconds !== 'number' || seconds < 0) {
        throw new Error('RW.after: seconds must be a non-negative number');
    }
    if (typeof fn !== 'function') {
        throw new Error('RW.after: fn must be a function');
    }
    return setTimeout(fn, seconds * 1000);
};

/*
 * ----------------------------------------------------------------
 * RW.registerMod(name: string, version: string): void
 *
 * Register a mod or power as loaded. Called once per file from inside
 * the IIFE. Powers prefix `name` with "power:" so status() can
 * distinguish them. Stores load timestamp for diagnostics.
 * ----------------------------------------------------------------
 */
RW.registerMod = function (name, version) {
    RW.mods[name] = { version: version, loadedAt: new Date().toISOString() };
};

/*
 * ----------------------------------------------------------------
 * status(): void
 *
 * Log the set of currently-registered mods and powers (one line each
 * with version). Auto-runs after every loadMod / loadPower so the
 * REPL shows the current state.
 * ----------------------------------------------------------------
 */
RW.status = function () {
    var names = Object.keys(RW.mods);
    if (!names.length) { console.log('[mods] (none)'); return; }
    console.log('[mods] ' + names.map(function (n) {
        return n + ' v=' + RW.mods[n].version;
    }).join(', '));
};

/*
 * ----------------------------------------------------------------
 * RW.Player.loc: {x, y, z} | null
 *
 * Live world position of the player (re-reads on every access).
 * Returns null if RW.Player.refresh() hasn't captured yet — call
 * refresh, then play one frame, then loc is populated. On null,
 * logs a one-time hint to the REPL.
 * ----------------------------------------------------------------
 * MECHANISM:
 *   Reads three contiguous float32s from RW.Player.entity+0x324 —
 *   the canonical position field that oCEntity::setPosition writes.
 */
/*
 * ----------------------------------------------------------------
 * RW.Player.refresh(): void
 *
 * Arm a one-shot capture of the player on the next ticked frame,
 * then detach. Required after hub load and after every chapter
 * reload (heap addresses change). The capture fires only when the
 * game ticks at least one frame — pause the game and the capture
 * never completes.
 * ----------------------------------------------------------------
 * MECHANISM:
 *   Hooks HC_per_frame_update at RVA 0x38e260. param_2 is the HC
 *   array header (count at +0x00, array ptr at +0x08). HC[0]+0x08
 *   is the player oCEntity. Detaches the hook on first capture.
 */
if (!RW.Player) RW.Player = {};
RW.Player.entity = null;
RW.Player.hc = null;
RW.Player._captureHook = null;
RW.Player._warnedNull = false;

Object.defineProperty(RW.Player, 'loc', {
    get: function () {
        if (RW.Player.entity === null || RW.Player.entity.isNull()) {
            if (!RW.Player._warnedNull) {
                console.log('[RW.Player] loc=null — call RW.Player.refresh() then play one frame');
                RW.Player._warnedNull = true;
            }
            return null;
        }
        try {
            var p = RW.Player.entity.add(0x324);
            return { x: p.readFloat(), y: p.add(4).readFloat(), z: p.add(8).readFloat() };
        } catch (e) { return null; }
    },
    configurable: true,
});

RW.Player.refresh = function () {
    if (RW.Player._captureHook) {
        try { RW.Player._captureHook.detach(); } catch (e) {}
    }
    RW.Player._captureHook = null;
    RW.Player.entity = null;
    RW.Player.hc = null;
    RW.Player._warnedNull = false;
    var rwMod = Process.findModuleByName('Ravenswatch.exe');
    if (rwMod === null) { console.log('[RW.Player] no Ravenswatch.exe'); return; }
    RW.Player._captureHook = Interceptor.attach(rwMod.base.add(0x38e260), {
        onEnter: function (args) {
            if (RW.Player.entity !== null) return;
            try {
                var hdr = ptr(args[1]);
                if (hdr.readU32() <= 0) return;
                var hc = hdr.add(0x08).readPointer().readPointer();
                RW.Player.hc = hc;
                RW.Player.entity = hc.add(0x08).readPointer();
                RW.Player._captureHook.detach();
                RW.Player._captureHook = null;
                var l = RW.Player.loc;
                console.log('[RW.Player] captured entity=' + RW.Player.entity +
                            ' loc=(' + l.x.toFixed(2) + ',' + l.y.toFixed(2) + ',' + l.z.toFixed(2) + ')');
            } catch (e) { console.log('[RW.Player] capture EXC: ' + e.message); }
        },
    });
    console.log('[RW.Player] capture armed (game must be unpaused)');
};

// Self-contained encyclopedia walker. Backs RW.Entity.find / .list with no
// dependency on external mods. Walks oCEntitySettingsEncyclopediaSceneContext
// via scene_manager_find_context_by_type. Needs the engine's scene_manager
// pointer, which is captured lazily on first use via a one-shot hook on the
// find-by-type function (auto-detaches on first fire). Hub stays passive on
// load — no hooks armed until RW.Entity is actually called.
if (!RW.Entity) RW.Entity = {};
RW.Entity._sm = null;
RW.Entity._smHook = null;
RW.Entity._tester = null;

function _entityInit() {
    var rwMod = Process.findModuleByName('Ravenswatch.exe');
    if (!rwMod) return null;
    var ib = rwMod.base;
    if (!RW.Entity._tester) {
        var t = Memory.alloc(16);
        t.writePointer(ib.add(0xf536d0));                       // encyclopedia type-tester vftable
        t.add(8).writePointer(ib.add(0x1447c18).readPointer()); // gTypeIdEnc (runtime-init pointer)
        RW.Entity._tester = t;
    }
    return ib;
}

function _entityArmSMCapture() {
    var ib = _entityInit();
    if (!ib) return;
    if (RW.Entity._smHook) return;
    RW.Entity._smHook = Interceptor.attach(ib.add(0x653f80), {
        onEnter: function (args) {
            if (RW.Entity._sm) return;
            RW.Entity._sm = ptr(args[0]);
            try { RW.Entity._smHook.detach(); } catch (e) {}
            RW.Entity._smHook = null;
            console.log('[RW.Entity] scene_manager captured');
        },
    });
}

function _entityWalk() {
    var ib = _entityInit();
    if (!ib) return null;
    if (!RW.Entity._sm) {
        _entityArmSMCapture();
        console.log('[RW.Entity] scene_manager not captured — hook armed; try again after one game frame');
        return null;
    }
    var smFindByType = new NativeFunction(ib.add(0x653f80),
        'pointer', ['pointer', 'pointer']);
    var enc;
    try { enc = smFindByType(RW.Entity._sm, RW.Entity._tester); }
    catch (e) { console.log('[RW.Entity] findByType EXC: ' + e.message); return null; }
    if (enc.isNull()) return null;

    var ctrl     = enc.add(0x28).readPointer();
    var entries  = enc.add(0x30).readPointer();
    var capMask  = enc.add(0x40).readU64().toNumber();
    var capacity = capMask + 1;
    var out = [];
    for (var i = 0; i < capacity; i++) {
        var c;
        try { c = ctrl.add(i).readU8(); } catch (e) { break; }
        if (c & 0x80) continue;
        var value;
        try { value = entries.add(i * 0x18).add(0x10).readPointer(); } catch (e) { continue; }
        if (value.isNull()) continue;
        try {
            var strPtr = value.add(0x08).readPointer();
            var len = value.add(0x10).readU32();
            if (len <= 0 || len > 512) continue;
            var name = strPtr.readUtf8String(len);
            var ent = value.add(0x48).readPointer();
            var p = ent.add(0x324);
            out.push({
                name: name,
                value: value,
                entity: ent,
                loc: { x: p.readFloat(), y: p.add(4).readFloat(), z: p.add(8).readFloat() },
            });
        } catch (e) {}
    }
    return out;
}

/*
 * ----------------------------------------------------------------
 * RW.Entity.find(name: string): { name, value, entity, loc } | null
 *
 * Case-insensitive substring lookup against the streaming asset
 * cache. Returns the first match's { name, value, entity, loc }
 * where loc is { x, y, z }, or null on no-match. Returns undefined
 * if the scene_manager isn't captured yet (hook auto-arms; retry
 * after the game has ticked one frame).
 * ----------------------------------------------------------------
 * EXPERIMENTAL — only sees encyclopedia entries currently streamed
 * into the active scene (typically 15-30 near the player, up to
 * ~2000 after exploration). NOT a full chapter POI list; full
 * per-instance enumeration is an open dig.
 *
 * MECHANISM:
 *   Walks oCEntitySettingsEncyclopediaSceneContext via scene_manager_
 *   find_context_by_type (RVA 0x653f80) with a tester built from the
 *   encyclopedia type-tester vftable (RVA 0xf536d0) and runtime
 *   type-id read from DAT_141447c18. Each entry's value
 *   (oCEntitySettingsResource) has display name at +0x08 (char*,
 *   length at +0x10), and an instance back-pointer at +0x48 to one
 *   live oCEntity. The oCEntity's position is at +0x324. Swiss-
 *   Tables iteration via control bytes at encyclopedia+0x28;
 *   capacity-mask at +0x40.
 */
RW.Entity.find = function (name) {
    var raw = _entityWalk();
    if (!raw) return;
    var key = String(name).toLowerCase();
    for (var i = 0; i < raw.length; i++) {
        if (raw[i].name.toLowerCase().indexOf(key) >= 0) return raw[i];
    }
    return null;
};

/*
 * ----------------------------------------------------------------
 * RW.Entity.list(): array of { name, value, entity, loc }
 *
 * Print every cached entry with its world position to the REPL,
 * then return the array (same shape as RW.Entity.find). Returns
 * undefined if scene_manager isn't captured yet.
 * ----------------------------------------------------------------
 * EXPERIMENTAL — same scope caveat as RW.Entity.find (only sees
 * streamed-in cache, not a full POI list).
 */
RW.Entity.list = function () {
    var out = _entityWalk();
    if (!out) return;
    console.log('[RW.Entity.list] ' + out.length + ' entries:');
    out.forEach(function (e, i) {
        var l = e.loc;
        console.log('  [' + i + '] ' + e.name +
                    ' @ (' + l.x.toFixed(1) + ',' + l.y.toFixed(1) + ',' + l.z.toFixed(1) + ')');
    });
    return out;
};

// REPL aliases
var loadMod   = RW.loadMod;
var loadPower = RW.loadPower;
var status    = RW.status;
var help      = RW.help;

// Parse rw_lab's own fenced docstrings into RW.docs so help() lists the
// hub API alongside loaded powers.
try {
    var _hubSrc = File.readAllText(RW.FRIDA_DIR + '/rw_lab.js');
    var _hubDocs = RW._parseDocs(_hubSrc);
    for (var _k in _hubDocs) RW.docs[_k] = _hubDocs[_k];
} catch (e) { /* hub help entries are optional — don't block boot */ }

// Boot banner.
const mod = Process.findModuleByName('Ravenswatch.exe');
if (mod === null) {
    console.log('[rw_lab] Ravenswatch.exe not loaded — abort.');
} else {
    console.log('=== rw_lab @ ' + new Date().toISOString() + ' ===');
    console.log('=== module base ' + mod.base + ' ===');
    console.log('[rw_lab] hub helpers: RW.Player.loc / .entity / .hc / .refresh()  (call refresh to capture)');
    console.log('[rw_lab] hub helpers: RW.Entity.find(name) / .list()  (experimental)');
    console.log('[rw_lab] ready. Load capabilities with loadPower("Name"):');
    console.log('[rw_lab]   ChapterBoss   Currency   SaveDiagnostic   TalentPicker   Teleport   Transporter');
    console.log('[rw_lab] help() lists every loaded power; help("Name.method") for full docs.');
    console.log('[rw_lab] CODE_STANDARDS.md documents the conventions.');
}
