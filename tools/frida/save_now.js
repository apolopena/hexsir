// Ravenswatch save-now — Frida script.
//
// Finds the heap-allocated oCDtRootGs instance and triggers a save by
// calling save_request_sync(NULL, instance + 0x1928).
//
// Usage:
//   frida -n Ravenswatch.exe -l save_now.js
//
// Will load, then auto-run. On the REPL prompt that follows, type 'exit'
// to leave (or pipe stdin: `printf 'exit\n' | frida ...`).
//
// Reference: rw/findings/save-subsystem.md and HANDOFF.md

'use strict';

// Static RVAs (relative to image base 0x140000000 in Ghidra).
const RVA_TYPEDESC_GETTER  = 0x1c6830;
const RVA_SAVE_REQUEST_SYNC = 0x6797b0;

// Field offsets within oCDtRootGs.
const OFF_JOB_PTR        = 0x1928;
const OFF_JOB_SEQ_PEND   = 0x19a4;
const OFF_JOB_SEQ_DONE   = 0x19a8;
const OFF_JOB_RESULT     = 0x19ac;
const OFF_SAVES_DISABLED = 0x1ef4;

const STRUCT_MIN_SIZE = 0x4000;
const CHUNK_SIZE      = 16 * 1024 * 1024;
const CHUNK_OVERLAP   = 0x4000;
const MAX_INSTANCES   = 1;       // expect exactly 1; early-exit on first hit

// ---- helpers ------------------------------------------------------------

function ptrToBytes(p) {
    const big = BigInt(p.toString());
    const b = [];
    for (let i = 0; i < 8; i++) {
        b.push(Number((big >> BigInt(i*8)) & 0xffn).toString(16).padStart(2,'0'));
    }
    return b.join(' ');
}

function info(m) { console.log('[+] ' + m); }
function warn(m) { console.log('[!] ' + m); }
function fail(m) { console.log('[X] ' + m); }

// ---- main ---------------------------------------------------------------

function main() {
    const mod = Process.findModuleByName('Ravenswatch.exe');
    if (!mod) { fail('Ravenswatch.exe not loaded'); return; }
    info('image_base = ' + mod.base);

    const expectedFn = mod.base.add(RVA_TYPEDESC_GETTER);
    const saveFn     = mod.base.add(RVA_SAVE_REQUEST_SYNC);
    info('expected vtable[0] = ' + expectedFn);
    info('save_request_sync   = ' + saveFn);

    // Step 1: find vtable address(es) in image — the unique vtable[0] reveals
    // every oCDtRootGs vtable, since we know vtable[0] points to that function.
    info('finding vtable addresses in image...');
    let vtblHits;
    try { vtblHits = Memory.scanSync(mod.base, mod.size, ptrToBytes(expectedFn)); }
    catch (e) { fail('image scan err: ' + e.message); return; }

    const vtblFingerprints = [];
    for (const h of vtblHits) {
        const aBig = BigInt(h.address.toString());
        if (Number(aBig & 7n) !== 0) continue;  // skip unaligned
        vtblFingerprints.push({
            addr: h.address,
            lo:   Number(aBig & 0xffffffffn),
            hi:   Number(aBig >> 32n)
        });
    }
    info('  ' + vtblFingerprints.length + ' aligned vtable address(es) found');
    for (const vp of vtblFingerprints) info('    vtable: ' + vp.addr);

    if (vtblFingerprints.length === 0) {
        fail('no vtable found — engine state may be uninitialized.');
        return;
    }

    // Step 2: scan heap for any qword == one of those vtable addresses.
    // For matches, verify structural signature, then save.
    info('scanning heap for instances...');
    const instances = scanHeapForInstances(vtblFingerprints);

    if (instances.length === 0) {
        fail('no oCDtRootGs instance found in heap. Is a profile loaded?');
        return;
    }

    info('found ' + instances.length + ' candidate(s):');
    for (const inst of instances) {
        info('  ' + inst.addr + '  pend=' + inst.pend +
             ' done=' + inst.done + ' result=' + inst.result + ' flag=' + inst.flag);
    }

    // Pick the instance with the most plausible state: saves enabled (flag=0),
    // result code valid, sequence invariants satisfied.
    const valid = instances.filter(function(i) {
        return i.flag === 0 && i.done <= i.pend &&
               (i.result < 16 || i.result === 0xff);
    });
    if (valid.length === 0) {
        fail('found candidates but none have plausible field values; refusing to save.');
        return;
    }
    if (valid.length > 1) {
        fail('multiple plausible candidates; refusing to save. Inspect manually:');
        for (const v of valid) info('  ' + v.addr);
        return;
    }

    const ds = valid[0];
    info('selected: ' + ds.addr);
    triggerSave(saveFn, ds);
}

// ---- heap scan ----------------------------------------------------------

function scanHeapForInstances(vtblFingerprints) {
    const ranges = Process.enumerateRanges({ protection: 'rw-', coalesce: false });
    info('  ' + ranges.length + ' rw- ranges to scan');

    const t0 = Date.now();
    const matches = [];
    let scannedBytes = 0;
    let progress = 0;

    for (const r of ranges) {
        progress++;
        if (r.size < STRUCT_MIN_SIZE) continue;
        let offset = 0;
        while (offset < r.size) {
            const sz = Math.min(CHUNK_SIZE, r.size - offset);
            const cbase = r.base.add(offset);
            let bytes;
            try { bytes = cbase.readByteArray(sz); }
            catch (_) { offset += CHUNK_SIZE - CHUNK_OVERLAP; continue; }
            if (!bytes || bytes.byteLength === 0) {
                offset += CHUNK_SIZE - CHUNK_OVERLAP; continue;
            }
            scannedBytes += bytes.byteLength;
            const view = new DataView(bytes);
            const limit = bytes.byteLength - 8;
            for (let p = 0; p < limit; p += 8) {
                const lo = view.getUint32(p, true);
                const hi = view.getUint32(p + 4, true);
                for (const vp of vtblFingerprints) {
                    if (lo !== vp.lo || hi !== vp.hi) continue;
                    const addr = cbase.add(p);
                    let pend, done, result, flag;
                    try {
                        pend   = addr.add(OFF_JOB_SEQ_PEND).readU32();
                        done   = addr.add(OFF_JOB_SEQ_DONE).readU32();
                        result = addr.add(OFF_JOB_RESULT).readU8();
                        flag   = addr.add(OFF_SAVES_DISABLED).readU8();
                    } catch (_) { continue; }
                    matches.push({
                        addr: addr, vtbl: vp.addr,
                        pend: pend, done: done, result: result, flag: flag
                    });
                    info('  found: ' + addr + ' (' + (Date.now() - t0) + 'ms)');
                    if (matches.length >= MAX_INSTANCES) {
                        info('  early-exit at ' + MAX_INSTANCES + ' matches');
                        return matches;
                    }
                    break;
                }
            }
            if (sz === r.size - offset) break;
            offset += CHUNK_SIZE - CHUNK_OVERLAP;
        }
    }
    info('  scan complete in ' + (Date.now() - t0) + 'ms (' +
         (scannedBytes/1024/1024).toFixed(0) + ' MB)');
    return matches;
}

// ---- save trigger -------------------------------------------------------

function triggerSave(saveFn, ds) {
    const jobPtr = ds.addr.add(OFF_JOB_PTR);
    info('triggering save: save_request_sync(NULL, ' + jobPtr + ')');
    info('  before: pend=' + ds.pend + ' done=' + ds.done);

    const fn = new NativeFunction(saveFn, 'void', ['pointer', 'pointer']);
    const t0 = Date.now();
    try {
        fn(NULL, jobPtr);
    } catch (e) {
        fail('save_request_sync threw: ' + e.message);
        return;
    }
    const dt = Date.now() - t0;

    let pend, done, result;
    try {
        pend   = ds.addr.add(OFF_JOB_SEQ_PEND).readU32();
        done   = ds.addr.add(OFF_JOB_SEQ_DONE).readU32();
        result = ds.addr.add(OFF_JOB_RESULT).readU8();
    } catch (e) {
        warn('post-save read failed: ' + e.message);
        return;
    }
    info('  after:  pend=' + pend + ' done=' + done + ' result=' + result +
         ' (took ' + dt + 'ms)');
    if (result === 0) info('SAVE COMPLETE.');
    else fail('save failed with result code ' + result);
}

// ---- entry --------------------------------------------------------------
// Expose main() as globalThis.go(); call from REPL or stdin.
// (Script-load runs in <30s; the heap scan happens inside go() which has
// no timeout limit.)

globalThis.go = main;
console.log('Loaded. Run: go()');
