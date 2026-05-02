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
// REPL:
//   force(seed)            — uint32. Write at TLS+0xff3c on each entry.
//   forceAggressive(seed)  — currently same as force; aggressive mode
//                            requires the IMUL hook which crashes the game.
//   unforce()              — stop forcing.
//   mark(label)            — bookmark.

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

    globalThis.unforce = function () {
        forceEnabled = false;
        nullPrevProposal = false;
        logLine(ts() + ' === FORCE disabled ===');
    };

    globalThis.mark = function (label) {
        logLine(ts() + ' --- mark: ' + label + ' entries=' + entryCount + ' ---');
    };

    console.log('[diag] ready. REPL: force(seed) | forceFresh(seed) | unforce() | mark("label")');
}
