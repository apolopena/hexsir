// Ravenswatch — forced-seed harness for the skill picker.
//
// Target: SkillController_roll_proposed_skills @ image+0x39c300.
// The function uses an inline PCG loop reading TLS+0xff3c. We force a
// deterministic seed by writing that slot on function entry.
//
// Why this implementation:
//   - GS-relative shims fail. Frida's NativeFunction call doesn't preserve
//     the game thread's GS base — even `mov rax, gs:[0x30]` faults.
//   - Hooking at the IMUL site (mid-loop) crashed the game (Frida relocator
//     issue with IMUL using [R12 + R9*1 + 4] addressing).
//   - Solution: get the TEB via NtQueryInformationThread (syscall, GS-free).
//     Walk TEB+0x58 → TLS array → array[0] = TLS data. Write at +0xff3c.
//     All reads done via Memory.readPointer (absolute addresses, no GS).
//
// Race timing: on the FIRST entry per thread, the function's own
// __dyn_tls_on_demand_init hasn't run yet, so the TLS data block may be
// too small to access offset 0xff3c. We catch the access violation and
// skip — by the second entry, init has run and the write succeeds.
//
// ===========================================================================
// REPL commands (call inside the Frida REPL after the script is loaded).
// All commands write a labeled line to LOG_PATH and to stdout. The picker
// must FIRE in-game (level-up or reroll) before any of the per-entry
// behaviors take effect.
// ===========================================================================
//
// SEED FORCING
// ------------
// force(seed)
//   uint32. On every subsequent picker entry, overwrite TLS+0xff3c with
//   `seed` BEFORE the picker reads it, so the talent selection becomes
//   deterministic. Re-writing happens every entry, so rerolls without
//   forceFresh use the original seed each draw and produce IDENTICAL picks.
//   Live test: call force(0xDEADBEEF) at the in-game main menu, then start
//   a run; first level-up's three talents will be the same every time you
//   reload the save.
//
// forceFresh(seed)
//   Same as force(seed) PLUS nulls param_3 (R8) on entry. param_3 is the
//   "exclude previous proposal" pool used by the reroll path; nulling it
//   lets every reroll see the SAME pool, so all rerolls within one level-up
//   produce identical talents under the forced seed. Use when you want
//   reroll-stable determinism (e.g., chained reroll testing).
//
// unforce()
//   Stop forcing. TLS seed is no longer overwritten and param_3 nulling
//   stops. Reroll exclusion behaves normally again.
//
// forceAggressive(seed)
//   Disabled stub; prints a warning. Aggressive mode required hooking the
//   IMUL inside the inline PCG loop, which crashed Frida's relocator. Kept
//   for backward compat with old REPL muscle memory.
//
// LOGGING
// -------
// mark(label)
//   Write a single labeled line to the log: `--- mark: <label> ... ---`.
//   Use to delimit phases during a live test ("about to level up",
//   "just rerolled", etc.) so you can grep the log afterwards.
//
// ONE-SHOT DUMPS (talent picker only — armed before the next entry)
// -----------------------------------------------------------------
// dumpTalentSlotsNext()
//   On the NEXT picker entry, dump the 10×0x20 slot record array at
//   `param_1+0xff0`. One log line per slot, with the 32-byte hex of the
//   slot record. Used to diff committed vs auto-filled vs empty/selectable
//   slot states. Auto-disarms after firing once.
//   Live test: call right before triggering a level-up; the picker entry
//   captures the in-memory slot states the engine reads.
//
// dumpTalentPoolNext()
//   On the NEXT picker entry, dump the UNPRUNED talent pool the picker
//   selects from. Logs slot index, class index, count, and a 32-byte
//   preview of each pool entry. Pruning (slot occupancy, modifier blocks,
//   previous-proposal exclusion) happens AFTER this dump inside the picker;
//   the offline brute-force seed solver replicates pruning from this input.
//   Auto-disarms after firing once.
//   Live test: call before a known picker fires (e.g., level-up); the dump
//   gives you the pool array as input to rw/dumps/picker_seed_solver.py.
//
// SLOT MANIPULATION (talent picker only — armed before the next entry)
// --------------------------------------------------------------------
// clearHeldTalentNext()       — zero held-talent ptrs for ALL 10 slots.
// clearHeldTalentNext(i)      — zero held-talent ptr for engine-slot i (0..9).
//   On the NEXT picker entry, write 0 to slot[i]+0x00 (the held-talent
//   pointer). Restored on function exit. Effect: the picker iterates
//   `param_1+0xff0` and fires for the FIRST slot whose held ptr is now
//   null. Targeting a specific slot only works if all earlier slots are
//   already populated (otherwise the picker fires for the lowest empty
//   slot instead of yours).
//   Live test: arm before a level-up, observe the picker fire for the
//   targeted slot.
//
// LOG OUTPUT (always-on per-entry)
// --------------------------------
// Every picker entry writes one line:
//   [T+<sec>s] [#N] FORCE/entry  tid=... seed=0x... slotTiers=<40-byte hex>
//   - slotTiers is the 10 × u32 persistent slot tier array (engine offset
//     param_1+0x1d48 -> persistent block +0x18). One short line; can't be
//     disabled — it's a primary signal for picker state.

'use strict';

const LOG_PATH        = 'C:\\Users\\KidSqid\\AppData\\Local\\Temp\\frida_seed_diag.log';
const TARGET_RVA      = 0x39c300;
const TLS_SEED_OFFSET = 0xff3c;
const TARGET_NAME     = 'SkillController_roll_proposed_skills';

// ThreadBasicInformation class (NtQueryInformationThread).
const ThreadBasicInformation = 0;
const TBI_SIZE               = 0x30;
const TBI_TEB_OFFSET         = 0x08;

const startedAt = Date.now();
let logFile = null;
let entryCount = 0;
let forceEnabled = false;
let forceSeed = 0;
let nullPrevProposal = false;   // null param_3 (R8) on entry to disable
                                // the "exclude previous proposal" filter
let clearHeldOnce = false;      // one-shot: zero held-talent pointer(s)
                                // on the NEXT picker entry, restore on exit
let clearHeldIndex = -1;         // -1 = clear all 10; 0..9 = clear only that
                                 // engine-slot index
let dumpSlotsOnce = false;       // one-shot: dump 10×0x20 slot records on
                                 // NEXT picker entry
let dumpPoolOnce = false;        // one-shot: dump unpruned pool array on
                                 // NEXT picker entry

function ts() {
    return '[T+' + ((Date.now() - startedAt) / 1000).toFixed(2) + 's]';
}

function logLine(s) {
    if (logFile !== null) {
        logFile.write(s + '\n');
        logFile.flush();
    }
    console.log(s);
}

// Lazy-resolved syscall to fetch the calling thread's TEB.
let _NtQueryInformationThread = null;
let _tbiBuffer = null;
function getCurrentTeb() {
    if (_NtQueryInformationThread === null) {
        const ntdll = Process.findModuleByName('ntdll.dll')
                    || Process.findModuleByName('NTDLL.DLL');
        if (ntdll === null) throw new Error('ntdll.dll module not found');
        const p = ntdll.findExportByName('NtQueryInformationThread');
        if (p === null) throw new Error('NtQueryInformationThread export not found');
        _NtQueryInformationThread = new NativeFunction(p, 'uint32',
            ['pointer', 'uint32', 'pointer', 'uint32', 'pointer'], 'win64');
        _tbiBuffer = Memory.alloc(TBI_SIZE);
    }
    // Pseudo-handle for current thread = -2 (0xFFFFFFFFFFFFFFFE).
    const status = _NtQueryInformationThread(
        ptr('0xfffffffffffffffe'),
        ThreadBasicInformation,
        _tbiBuffer,
        TBI_SIZE,
        ptr(0)
    );
    if (status !== 0) {
        throw new Error('NtQueryInformationThread failed: 0x' + status.toString(16));
    }
    return _tbiBuffer.add(TBI_TEB_OFFSET).readPointer();
}

function getSeedAddr() {
    const teb = getCurrentTeb();
    const tlsArray = teb.add(0x58).readPointer();
    const tlsData = tlsArray.readPointer();
    return tlsData.add(TLS_SEED_OFFSET);
}

const mod = Process.findModuleByName('Ravenswatch.exe');
if (mod === null) {
    console.log('[diag] Ravenswatch.exe not loaded — abort.');
} else {
    logFile = new File(LOG_PATH, 'w');
    logLine('=== Frida skill-RNG harness @ ' + new Date().toISOString() + ' ===');
    logLine('=== module base ' + mod.base + ' ===');

    const targetAddr = mod.base.add(TARGET_RVA);
    Interceptor.attach(targetAddr, {
        onEnter(args) {
            entryCount++;
            let teb = '?', tlsArr = '?', tlsData = '?', seedAddr = null, oldSeed = '?';
            try {
                teb = getCurrentTeb();
                tlsArr = teb.add(0x58).readPointer();
                tlsData = tlsArr.readPointer();
                seedAddr = tlsData.add(TLS_SEED_OFFSET);
                oldSeed = '0x' + seedAddr.readU32().toString(16).padStart(8, '0');
            } catch (e) {
                logLine(ts() + ' [#' + entryCount + '] entry  FAIL ' + e.message +
                        ' teb=' + teb + ' tlsArr=' + tlsArr + ' tlsData=' + tlsData);
                return;
            }

            // Diagnostic dump: read the SkillController's persistent slot.tier
            // array. param_1 (the SkillController) is in RCX (Win64 ABI).
            // *(rcx+0x1d48) -> persistent block; +0x18 -> 10 × u32 slot tiers.
            let slotTiersHex = '?';
            try {
                const skillCtrl = this.context.rcx;
                const persistent = skillCtrl.add(0x1d48).readPointer();
                const tiersAddr = persistent.add(0x18);
                const buf = tiersAddr.readByteArray(40);  // 10 × 4 bytes
                slotTiersHex = Array.from(new Uint8Array(buf))
                    .map(b => b.toString(16).padStart(2, '0'))
                    .join('');
            } catch (e) {
                slotTiersHex = 'ERR:' + e.message;
            }

            // Dump the 10-slot record array at param_1+0xff0 (stride 0x20).
            // ARMED via dumpTalentSlotsNext() — one-shot, auto-disarms.
            if (dumpSlotsOnce) {
                dumpSlotsOnce = false;
                try {
                    const skillCtrl = this.context.rcx;
                    for (let i = 0; i < 10; i++) {
                        const slotAddr = skillCtrl.add(0xff0 + i * 0x20);
                        const bytes = slotAddr.readByteArray(0x20);
                        const hex = Array.from(new Uint8Array(bytes))
                            .map(b => b.toString(16).padStart(2, '0'))
                            .join('');
                        logLine(ts() + ' [#' + entryCount + '] slot[' + i + '] @ ' +
                                slotAddr + ' = ' + hex);
                    }
                } catch (e) {
                    logLine(ts() + ' [#' + entryCount + '] slot dump ERR: ' + e.message);
                }
            }

            // Pool dump for the offline brute-force seed solver.
            // ARMED via dumpTalentPoolNext() — one-shot, auto-disarms.
            //
            // Per the decompile of SkillController_roll_proposed_skills:
            //   - The first empty slot index is found by scanning
            //     param_1+0xff0 stride 0x20 for the first slot whose
            //     held-talent ptr (+0x00) is zero.
            //   - Slot's class index lives at param_1+0xfe0+slot*0x20.
            //   - Pool struct at param_1+0xf98 stride 0x10:
            //       +0x00: data pointer (array of longlongs / talent ptrs)
            //       +0x08: count u32
            //   - The picker copies this pool into a local buffer, then
            //     prunes (slot occupants, modifier-blocked items, previous
            //     proposal). The dump here captures the UNPRUNED pool —
            //     pruning is replicated offline.
            if (dumpPoolOnce) {
                dumpPoolOnce = false;
                try {
                    const skillCtrl = this.context.rcx;
                    let slotIdx = -1;
                    for (let i = 0; i < 10; i++) {
                        if (skillCtrl.add(0xff0 + i * 0x20).readPointer().isNull()) {
                            slotIdx = i;
                            break;
                        }
                    }
                    if (slotIdx < 0) {
                        logLine(ts() + ' [#' + entryCount + '] pool: no empty slot');
                    } else {
                        const classIdx = skillCtrl.add(0xfe0 + slotIdx * 0x20).readU32();
                        const poolEntry = skillCtrl.add(0xf98 + classIdx * 0x10);
                        const poolData = poolEntry.readPointer();
                        const poolCount = poolEntry.add(0x08).readU32();
                        logLine(ts() + ' [#' + entryCount + '] pool: slot=' + slotIdx +
                                ' class=' + classIdx + ' count=' + poolCount +
                                ' data=' + poolData);
                        const dumpN = Math.min(poolCount, 64);
                        for (let i = 0; i < dumpN; i++) {
                            const entryPtr = poolData.add(i * 8).readPointer();
                            let preview = '';
                            let derefPreview = '';
                            try {
                                const bytes = entryPtr.readByteArray(0x20);
                                preview = Array.from(new Uint8Array(bytes))
                                    .map(b => b.toString(16).padStart(2, '0'))
                                    .join('');
                            } catch (e) {
                                preview = 'ERR:' + e.message;
                            }
                            // Follow per-talent pointer at +0x10 and dump 256
                            // bytes from there — the talent's 16-byte GUID
                            // typically sits at some offset within the
                            // definition struct (e.g. +0x70 per the picker's
                            // own access pattern). Wider dump lets offline
                            // analysis grep the inner bytes for any known
                            // talent GUID from the hero registry yaml.
                            try {
                                const innerPtr = entryPtr.add(0x10).readPointer();
                                const innerBytes = innerPtr.readByteArray(0x100);
                                derefPreview = Array.from(new Uint8Array(innerBytes))
                                    .map(b => b.toString(16).padStart(2, '0'))
                                    .join('');
                            } catch (e) {
                                derefPreview = 'ERR:' + e.message;
                            }
                            logLine(ts() + ' [#' + entryCount + '] pool[' + i + '] @ ' +
                                    entryPtr + ' = ' + preview);
                            logLine(ts() + ' [#' + entryCount + '] pool[' + i + '] inner = ' +
                                    derefPreview);
                        }
                    }
                } catch (e) {
                    logLine(ts() + ' [#' + entryCount + '] pool dump ERR: ' + e.message);
                }
            }

            // One-shot: zero held-talent pointer(s) at param_1+0xff0,
            // stride 0x20. Restored on onLeave. clearHeldIndex==-1 zeroes
            // all 10 entries; 0..9 zeroes only that engine-slot index.
            this.savedHeld = null;
            if (clearHeldOnce) {
                clearHeldOnce = false;
                const targetIdx = clearHeldIndex;
                clearHeldIndex = -1;
                try {
                    const skillCtrl = this.context.rcx;
                    const saved = [];
                    const indices = (targetIdx === -1)
                        ? [0,1,2,3,4,5,6,7,8,9]
                        : [targetIdx];
                    for (const i of indices) {
                        const addr = skillCtrl.add(0xff0 + i * 0x20);
                        saved.push({ addr: addr, value: addr.readPointer() });
                        addr.writePointer(ptr(0));
                    }
                    this.savedHeld = saved;
                    const which = (targetIdx === -1) ? 'all 10' : 'slot ' + targetIdx;
                    logLine(ts() + ' [#' + entryCount + '] CLEAR-HELD: zeroed ' + which +
                            ' held-talent pointer(s)');
                } catch (e) {
                    logLine(ts() + ' [#' + entryCount + '] CLEAR-HELD failed: ' + e.message);
                }
            }

            if (forceEnabled) {
                let writeStatus = 'OK';
                try { seedAddr.writeU32(forceSeed >>> 0); }
                catch (e) { writeStatus = 'ERR ' + e.message; }
                let nulledPrev = '';
                if (nullPrevProposal) {
                    const oldR8 = this.context.r8;
                    this.context.r8 = ptr(0);
                    nulledPrev = ' nulledPrev(was=' + oldR8 + ')';
                }
                logLine(ts() + ' [#' + entryCount + '] FORCE  tid=' + this.threadId +
                        ' tlsData=' + tlsData + ' addr=' + seedAddr +
                        ' was=' + oldSeed +
                        ' wrote=0x' + (forceSeed >>> 0).toString(16).padStart(8, '0') +
                        ' write=' + writeStatus + nulledPrev +
                        ' slotTiers=' + slotTiersHex);
            } else {
                logLine(ts() + ' [#' + entryCount + '] entry  tid=' + this.threadId +
                        ' tlsData=' + tlsData + ' addr=' + seedAddr +
                        ' seed=' + oldSeed +
                        ' slotTiers=' + slotTiersHex);
            }
        },
        onLeave(retval) {
            // Restore held-talent pointers if we cleared them on entry.
            if (this.savedHeld) {
                try {
                    for (const e of this.savedHeld) {
                        e.addr.writePointer(e.value);
                    }
                    logLine(ts() + ' [#' + entryCount + '] CLEAR-HELD: restored 10 held-talent pointers');
                } catch (e) {
                    logLine(ts() + ' [#' + entryCount + '] CLEAR-HELD restore failed: ' + e.message);
                }
            }
        }
    });

    logLine('[diag] hooked entry @ ' + targetAddr + ' (rva 0x' + TARGET_RVA.toString(16) + ')');

    globalThis.force = function (seed) {
        if (typeof seed !== 'number') {
            console.log('[diag] usage: force(seed_uint32) — e.g. force(0xDEADBEEF)');
            return;
        }
        forceSeed = seed >>> 0;
        forceEnabled = true;
        logLine(ts() + ' === FORCE enabled seed=0x' +
                forceSeed.toString(16).padStart(8, '0') + ' ===');
    };

    globalThis.forceAggressive = function (seed) {
        console.log('[diag] aggressive mode disabled — IMUL hook crashes the game.');
        console.log('[diag] use forceFresh() instead for a visual smoke test.');
    };

    // Forces the seed AND nulls param_3 (R8) so the "exclude previous proposal"
    // filter is skipped. Result: every reroll sees the SAME pool, our forced
    // seed produces SAME talents across all rerolls in the same level-up.
    globalThis.forceFresh = function (seed) {
        if (typeof seed !== 'number') {
            console.log('[diag] usage: forceFresh(seed_uint32)');
            return;
        }
        forceSeed = seed >>> 0;
        forceEnabled = true;
        nullPrevProposal = true;
        logLine(ts() + ' === FORCE enabled seed=0x' +
                forceSeed.toString(16).padStart(8, '0') +
                ' (FRESH - param_3 nulled, identical rerolls expected) ===');
    };

    // One-shot diagnostic: on the NEXT picker entry, zero held-talent pointer(s)
    // at param_1+0xff0+i*0x20. Restored on function exit.
    //
    //   clearHeldTalentNext()      — zero all 10 entries (whole array empty).
    //   clearHeldTalentNext(i)     — zero only engine-slot i (0..9). The
    //                                picker will then iterate and find slot i
    //                                as a target (or fall through if some
    //                                other slot is also empty earlier).
    //
    // Caveat: the picker fires for the FIRST empty slot in iteration order.
    // Clearing all 10 always fires for engine-slot 0. To target a specific
    // slot, you may need to leave earlier slots populated.
    globalThis.clearHeldTalentNext = function (slotIdx) {
        if (typeof slotIdx === 'number') {
            if (slotIdx < 0 || slotIdx > 9) {
                console.log('[diag] clearHeldTalentNext: slotIdx must be 0..9, got ' + slotIdx);
                return;
            }
            clearHeldIndex = slotIdx;
        } else {
            clearHeldIndex = -1;
        }
        clearHeldOnce = true;
        const which = (clearHeldIndex === -1) ? 'all 10 slots' : 'slot ' + clearHeldIndex;
        logLine(ts() + ' === CLEAR-HELD-TALENT armed: next picker entry will zero ' +
                which + ' (one-shot, auto-restored on exit) ===');
    };

    globalThis.unforce = function () {
        forceEnabled = false;
        nullPrevProposal = false;
        logLine(ts() + ' === FORCE disabled ===');
    };

    // One-shot diagnostic: dump the 10×0x20 slot record array on the next
    // picker entry. Auto-disarms after firing once.
    globalThis.dumpTalentSlotsNext = function () {
        dumpSlotsOnce = true;
        logLine(ts() + ' === DUMP-TALENT-SLOTS armed: next picker entry will dump 10 slot records ===');
    };

    // One-shot diagnostic: dump the unpruned talent pool array (entry-relative,
    // before the picker copies it locally) on the next picker entry.
    // Auto-disarms after firing once.
    globalThis.dumpTalentPoolNext = function () {
        dumpPoolOnce = true;
        logLine(ts() + ' === DUMP-TALENT-POOL armed: next picker entry will dump pool array ===');
    };

    globalThis.mark = function (label) {
        logLine(ts() + ' --- mark: ' + label + ' entries=' + entryCount + ' ---');
    };

    console.log('[diag] ready. REPL: force(seed) | forceFresh(seed) | unforce() | mark("label")');
    console.log('[diag]        dumpTalentSlotsNext() | dumpTalentPoolNext() | clearHeldTalentNext(idx?)');
}
