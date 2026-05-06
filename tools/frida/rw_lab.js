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
    console.log('[rw_lab] ready. Load capabilities with loadPower("Name"):');
    console.log('[rw_lab]   ChapterBoss   Currency   SaveDiagnostic   TalentPicker   Teleport');
    console.log('[rw_lab] help() lists every loaded power; help("Name.method") for full docs.');
    console.log('[rw_lab] CODE_STANDARDS.md documents the conventions.');
}
