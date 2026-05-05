// Ravensmith Rule-A budget dig — Frida probe.
//
// Goal: pinpoint the per-save data field that determines Rule A's
// fresh-reference-allocation cap (chapter 2 = +2, chapter 3 = +3, epilogue = +7).
// Static analysis (rw/findings/items-add-primitive-cap.md +
// rw/findings/ghidra-rule-c-investigation.md) ruled out the obvious suspects
// (items vec, records-replay loop, vec_u64_assign_resize itself). The cap is
// enforced upstream of the records-replay loop and exposed to the loop only
// through entity preconditions that are not visible in static decomp.
//
// DESIGN NOTES
//   vec_u64_assign_resize is a generic vector helper called ~500 Hz during
//   normal gameplay. It is NOT specific to save-load. Hooking it globally is
//   prohibitively noisy. This probe gates all per-call logging behind an
//   `inDeserialize` flag set on entry to serde_hero_controller_persistent_data
//   and cleared on leave. Per-call logging only fires during the brief window
//   when the records-replay path is actually executing.
//
// REPL commands:
//   armBudgetTrace()              install hooks. Quiet mode by default:
//                                 only persistent-struct dump + per-serde
//                                 summary line. No per-call noise.
//   armBudgetTrace({verbose:true}) verbose mode: add per-record sync trace
//                                 and per-call vec-resize trace. Use only
//                                 when chasing a specific record's failure.
//                                 Still gated to deserialize window.
//   disarmBudgetTrace()           uninstall everything.
//   dumpPersistentAt(addr)        manual dumper. Bare call reuses the address
//                                 captured by the most recent serde hit.
//   budgetTraceStatus()           install state + counters.
//
// Logs go to:
//   C:\Users\KidSqid\AppData\Local\Temp\frida_seed_diag.log
//
// Drive from WSL:
//   /mnt/c/Users/KidSqid/AppData/Local/Python/pythoncore-3.14-64/Scripts/frida.exe \
//     -n Ravenswatch.exe -l /home/ks73/repos/work/ravensmith/tools/frida/probe_item_budget.js
//
// Test sequence:
//   1. Launch this probe BEFORE clicking Continue.
//   2. armBudgetTrace() in the REPL.
//   3. Load a known proof. Observe one persistent-struct dump per serde hit.
//   4. Repeat across {laser-lenses_1 (+2), chapter-3 proof (+3), epilogue (+7)}.
//      Diff persistent dumps; fields that vary in lockstep with the budget are
//      candidates.
//   5. To chase a known-crashing lab: disarmBudgetTrace(); armBudgetTrace({verbose:true});
//      load the lab; capture the wild vec_u64_assign_resize call inside the
//      deserialize window. Backtrace identifies the budget-allocation site.

'use strict';

const LOG_PATH       = 'C:\\Users\\KidSqid\\AppData\\Local\\Temp\\frida_seed_diag.log';
const MODULE_NAME    = 'Ravenswatch.exe';

// RVAs (image base 0x140000000 in Ghidra).
//
// 2026-05-04 (initial): hooked `serde_hero_controller_persistent_data` at
// 0x140380490 — never fired on save load. Almost certainly the write-side
// serializer, misnamed by an earlier session.
//
// 2026-05-04 (round 2): switched to `hero_controller_init_replay_persistent_data`
// at 0x140384610 — fires per save load (sync=21/resize=42 confirmed for
// chapter-2's 21 records). But this function's first arg is the hero_state
// struct, not the persistent struct. Walking *(*(hero_state+8)+0x30)+0x1a8
// gave the entry-time `lVar21`, which is REASSIGNED later in the function:
// the records-loop's lVar21 (line 1495 of the decomp) is `local_b60`,
// populated by FUN_1402b7810 at line 1445. So we hook FUN_1402b7810 onLeave
// to capture the post-mutation pointer, which IS the records-loop persistent
// struct.
const RVA_HERO_INIT_REPLAY          = 0x384610;
const RVA_FIND_PERSISTENT_CONTEXT   = 0x2b7810;  // FUN_1402b7810; mutates &local_b60
const RVA_ENTITY_SYNC_COMPONENT_VEC = 0x6db4b0;
const RVA_VEC_U64_ASSIGN_RESIZE     = 0x2046e0;

const startedAt = Date.now();
let logFile = null;
let imageBase = null;

let hookSerde         = null;
let hookFindContext   = null;
let hookEntitySync    = null;
let hookVecResize     = null;

let verboseMode       = false;
let inDeserialize     = false;
let serdeHits         = 0;
let entitySyncHits    = 0;
let vecResizeHits     = 0;
let wildHits          = 0;
let lastPersistent    = null;

// Per-deserialize counters (reset on serde onEnter, summarized on onLeave).
let dsEntitySync      = 0;
let dsVecResize       = 0;
let dsWild            = 0;
let firstFindHitThisLoad = true;

function ts() {
    const dt = Date.now() - startedAt;
    return '[' + (dt / 1000).toFixed(3) + 's]';
}

function logLine(s) {
    try {
        if (logFile === null) logFile = new File(LOG_PATH, 'a');
        logFile.write(s + '\n');
        logFile.flush();
    } catch (e) {
        // best-effort
    }
    console.log(s);
}

function hex(p, n) {
    try {
        const bytes = p.readByteArray(n);
        const arr = new Uint8Array(bytes);
        let out = '';
        for (let i = 0; i < arr.length; i++) {
            out += ('0' + arr[i].toString(16)).slice(-2);
            if ((i & 0xf) === 0xf) out += '\n  ';
            else if ((i & 3) === 3) out += ' ';
        }
        return out;
    } catch (e) {
        return '<read fail: ' + e.message + '>';
    }
}

function dumpU32Field(label, p, off) {
    try {
        const v = p.add(off).readU32();
        logLine(ts() + ' [PERSIST] ' + label + ' (+0x' + off.toString(16) + ') = 0x' +
                v.toString(16) + ' (' + v + ')');
    } catch (e) {
        logLine(ts() + ' [PERSIST] ' + label + ' (+0x' + off.toString(16) + ') = <read fail>');
    }
}

function dumpPtrField(label, p, off) {
    try {
        const v = p.add(off).readPointer();
        logLine(ts() + ' [PERSIST] ' + label + ' (+0x' + off.toString(16) + ') = ' + v);
    } catch (e) {
        logLine(ts() + ' [PERSIST] ' + label + ' (+0x' + off.toString(16) + ') = <read fail>');
    }
}

function dumpPersistent(p) {
    logLine(ts() + ' === PERSISTENT-STRUCT-DUMP this=' + p + ' ===');
    dumpU32Field('+0x50 u32        ', p, 0x50);
    dumpU32Field('+0x58 u32        ', p, 0x58);
    dumpU32Field('+0x5c u32        ', p, 0x5c);
    dumpU32Field('+0x60 u32        ', p, 0x60);
    dumpU32Field('+0x64 u16-pair   ', p, 0x64);
    for (let i = 0; i < 10; i++) {
        dumpU32Field('+0x' + (0x68 + i*4).toString(16) + ' slot' + i + '       ',
                     p, 0x68 + i*4);
    }
    dumpU32Field('+0x90 u16-pair   ', p, 0x90);
    dumpPtrField ('+0x98 vec.ptr    ', p, 0x98);
    dumpU32Field ('+0xa0 vec.count  ', p, 0xa0);
    dumpU32Field ('+0xa4 vec.cap    ', p, 0xa4);
    dumpPtrField ('+0xa8 items.ptr  ', p, 0xa8);
    dumpU32Field ('+0xb0 items.count', p, 0xb0);
    dumpU32Field ('+0xb4 items.cap  ', p, 0xb4);
    dumpPtrField ('+0xb8 vec.ptr    ', p, 0xb8);
    dumpU32Field ('+0xc0 vec.count  ', p, 0xc0);
    dumpPtrField ('+0xc8 vec.ptr    ', p, 0xc8);
    dumpU32Field ('+0xd0 vec.count  ', p, 0xd0);
    dumpPtrField ('+0xd8 strvec.ptr ', p, 0xd8);
    dumpU32Field ('+0xe0 strvec.cnt ', p, 0xe0);
    dumpPtrField ('+0xe8 vec.ptr    ', p, 0xe8);
    dumpU32Field ('+0xf0 vec.count  ', p, 0xf0);
    dumpPtrField ('+0xf8 vec.ptr    ', p, 0xf8);
    dumpU32Field ('+0x100 vec.count ', p, 0x100);
    logLine(ts() + ' --- raw 0x100 bytes from ' + p + ':');
    logLine('  ' + hex(p, 0x100));
}

function symFor(addr) {
    try {
        const s = DebugSymbol.fromAddress(addr).toString();
        return s.length > 0 ? s : addr.toString();
    } catch (e) {
        return addr.toString();
    }
}

function backtrace3(ctx) {
    try {
        const frames = Thread.backtrace(ctx, Backtracer.ACCURATE).slice(0, 3);
        return frames.map(symFor).join(' <- ');
    } catch (e) {
        return '<backtrace fail: ' + e.message + '>';
    }
}

function isReadablePointer(p) {
    if (p.isNull()) return false;
    try {
        Memory.readU8(p);
        return true;
    } catch (e) {
        return false;
    }
}

function ensureImageBase() {
    if (imageBase !== null) return imageBase;
    const m = Process.findModuleByName(MODULE_NAME);
    if (m === null) {
        throw new Error(MODULE_NAME + ' not loaded');
    }
    imageBase = m.base;
    logLine(ts() + ' [init] image base = ' + imageBase);
    return imageBase;
}

globalThis.armBudgetTrace = function (opts) {
    if (hookSerde !== null) {
        console.log('[budget] already armed; call disarmBudgetTrace() first');
        return;
    }
    verboseMode = !!(opts && opts.verbose);
    const base = ensureImageBase();

    const addrReplay      = base.add(RVA_HERO_INIT_REPLAY);
    const addrFindContext = base.add(RVA_FIND_PERSISTENT_CONTEXT);
    const addrEntitySync  = base.add(RVA_ENTITY_SYNC_COMPONENT_VEC);
    const addrVecResize   = base.add(RVA_VEC_U64_ASSIGN_RESIZE);

    serdeHits = 0;
    entitySyncHits = 0;
    vecResizeHits = 0;
    wildHits = 0;

    hookSerde = Interceptor.attach(addrReplay, {
        onEnter: function (args) {
            const heroState = args[0];
            serdeHits += 1;
            inDeserialize = true;
            firstFindHitThisLoad = true;
            dsEntitySync = 0;
            dsVecResize = 0;
            dsWild = 0;
            logLine(ts() + ' === HERO-INIT-REPLAY entry hit#' + serdeHits +
                    ' hero_state=' + heroState + ' ===');
            // Don't dump anything here — the entry-time persistent struct
            // (resolved via *(*(hero+8)+0x30)+0x1a8) gets superseded by the
            // records-loop's lVar21 = local_b60, populated by FUN_1402b7810
            // (see hookFindContext below).
        },
        onLeave: function (retval) {
            inDeserialize = false;
            logLine(ts() + ' === HERO-INIT-REPLAY leave hit#' + serdeHits +
                    ' [during-load: sync=' + dsEntitySync +
                    ' resize=' + dsVecResize + '] ===');
        },
    });

    // Hook the function that mutates `local_b60` (decomp line 1445):
    //   FUN_1402b7810(param_1, &local_b60);
    // Microsoft x64 ABI: param_2 (&local_b60) is in RDX = args[1]. Save it on
    // entry, deref on leave to read the value FUN_1402b7810 wrote — that's
    // the records-loop's lVar21 (persistent struct with +0xb0 items.count,
    // +0xa8 items.ptr, etc.). Only fires during deserialize; logs only the
    // first hit per deserialize window.
    hookFindContext = Interceptor.attach(addrFindContext, {
        onEnter: function (args) {
            if (!inDeserialize) return;
            this.outPtrAddr = args[1];
            this.shouldLog  = firstFindHitThisLoad;
            firstFindHitThisLoad = false;
        },
        onLeave: function (retval) {
            if (!this.outPtrAddr || !this.shouldLog) return;
            try {
                const persistent = this.outPtrAddr.readPointer();
                lastPersistent = persistent;
                logLine(ts() + ' [find-context] FUN_1402b7810 wrote persistent=' + persistent);
                dumpPersistent(persistent);
            } catch (e) {
                logLine(ts() + ' [find-context] read FAIL ' + e.message);
            }
        },
    });

    // Per-record sync hook gated to deserialize window. Counts always; logs
    // only in verbose mode. Wild detection removed — Frida's Memory.readU8
    // has false positives on valid heap addresses.
    hookEntitySync = Interceptor.attach(addrEntitySync, {
        onEnter: function (args) {
            if (!inDeserialize) return;
            const p1 = args[0];
            entitySyncHits += 1;
            dsEntitySync += 1;
            if (verboseMode) {
                try {
                    const compBase  = p1.add(0x08).readPointer();
                    const compCount = p1.add(0x10).readU32();
                    logLine(ts() + ' [SYNC] hit#' + dsEntitySync +
                            ' param1=' + p1 +
                            ' comp.base=' + compBase +
                            ' comp.count=' + compCount);
                } catch (e) {
                    logLine(ts() + ' [SYNC] hit#' + dsEntitySync + ' param1=' + p1 +
                            ' read FAIL ' + e.message);
                }
            }
        },
    });

    // Per-call vec-resize hook gated to deserialize window. Counts always;
    // logs only in verbose mode. We rely on the actual save-load crash to
    // identify the budget-overflow site rather than synthetic wild detection.
    hookVecResize = Interceptor.attach(addrVecResize, {
        onEnter: function (args) {
            if (!inDeserialize) return;
            vecResizeHits += 1;
            dsVecResize += 1;
            if (verboseMode) {
                const vecPtr   = args[0];
                const srcPtr   = args[1];
                const newCount = args[2].toUInt32();
                let dstBase = '<read fail>', dstCount = -1, dstCap = -1;
                try {
                    dstBase  = vecPtr.readPointer().toString();
                    dstCount = vecPtr.add(0x8).readU32();
                    dstCap   = vecPtr.add(0xc).readU32();
                } catch (e) {}
                logLine(ts() + ' [VECRSZ] hit#' + dsVecResize +
                        ' vec=' + vecPtr +
                        ' dst=(' + dstBase + ',' + dstCount + ',' + dstCap + ')' +
                        ' src=' + srcPtr +
                        ' new_count=' + newCount +
                        ' bt: ' + backtrace3(this.context));
            }
        },
    });

    logLine(ts() + ' === BUDGET-TRACE armed mode=' + (verboseMode ? 'VERBOSE' : 'QUIET') +
            ' (replay=' + addrReplay +
            ', find-context=' + addrFindContext +
            ', sync=' + addrEntitySync +
            ', resize=' + addrVecResize + ') ===');
    console.log('[budget] armed (' + (verboseMode ? 'verbose' : 'quiet') +
                '). Load a save now.');
};

globalThis.disarmBudgetTrace = function () {
    if (hookSerde       !== null) { hookSerde.detach();       hookSerde = null; }
    if (hookFindContext !== null) { hookFindContext.detach(); hookFindContext = null; }
    if (hookEntitySync  !== null) { hookEntitySync.detach();  hookEntitySync = null; }
    if (hookVecResize   !== null) { hookVecResize.detach();   hookVecResize = null; }
    inDeserialize = false;
    logLine(ts() + ' === BUDGET-TRACE disarmed' +
            ' (serde=' + serdeHits +
            ' sync=' + entitySyncHits +
            ' resize=' + vecResizeHits +
            ' wild=' + wildHits + ') ===');
};

globalThis.dumpPersistentAt = function (addrLike) {
    let p;
    if (typeof addrLike === 'string') {
        p = ptr(addrLike);
    } else if (addrLike && addrLike.constructor && addrLike.constructor.name === 'NativePointer') {
        p = addrLike;
    } else if (addrLike === undefined && lastPersistent !== null) {
        p = lastPersistent;
    } else {
        console.log('[budget] usage: dumpPersistentAt("0x...") or dumpPersistentAt() to reuse last serde-captured this');
        return;
    }
    dumpPersistent(p);
};

globalThis.budgetTraceStatus = function () {
    console.log('[budget] armed: ' + (hookSerde !== null) +
                ' | mode: ' + (verboseMode ? 'verbose' : 'quiet') +
                ' | inDeserialize: ' + inDeserialize +
                ' | serde=' + serdeHits +
                ' sync=' + entitySyncHits +
                ' resize=' + vecResizeHits +
                ' wild=' + wildHits +
                ' | lastPersistent=' + lastPersistent);
};

console.log('[budget] probe loaded. REPL: armBudgetTrace() | armBudgetTrace({verbose:true}) | disarmBudgetTrace() | dumpPersistentAt(addr?) | budgetTraceStatus()');
