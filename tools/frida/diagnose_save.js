// Ravenswatch save diagnostics — Frida script.
//
// Loads quickly, then exposes REPL/stdin commands:
//   diag()                 find oCDtRootGs, print job buffer state, direct refs
//   session()              find GameSessionGs owner by exact vtable scan
//   saveDiag()             same, then call save_request_sync and print before/after
//   refs("0x...")          scan writable memory for qword refs to an address
//   owners(depth=2)         fast owner-chain search near data_source heap ranges
//   ownersFull(depth=2)     slower owner-chain search across all rw- ranges
//   finalizer("0x...")     experimental: call FUN_14028d6a0(owner)
//
// Drive from WSL:
//   printf 'diag()\nexit\n' | frida.exe -n Ravenswatch.exe -l diagnose_save.js

'use strict';

const MODULE_NAME = 'Ravenswatch.exe';

// Static RVAs, relative to image base 0x140000000 in Ghidra.
const RVA_TYPEDESC_GETTER    = 0x1c6830;
const RVA_SAVE_REQUEST_SYNC  = 0x6797b0;
const RVA_SAVE_FINALIZER     = 0x28d6a0;  // FUN_14028d6a0(owner)
const RVA_GAMESESSION_VTABLE = 0xefa0f8;  // live oe::dt::GameSessionGs vptr value

// Field offsets within oCDtRootGs.
const OFF_JOB_PTR        = 0x1928;
const OFF_JOB_SEQ_PEND   = 0x19a4;
const OFF_JOB_SEQ_DONE   = 0x19a8;
const OFF_JOB_RESULT     = 0x19ac;
const OFF_SAVES_DISABLED = 0x1ef4;

// Field offsets within job.
const JOB_OPCODE    = 0x0c;
const JOB_DATA_PTR  = 0x30;
const JOB_DATA_SIZE = 0x38;
const JOB_EXT_FLAG  = 0x48;
const JOB_SEQ_PEND  = 0x7c;
const JOB_SEQ_DONE  = 0x80;
const JOB_RESULT    = 0x84;

const STRUCT_MIN_SIZE = 0x4000;
const CHUNK_SIZE      = 16 * 1024 * 1024;
const CHUNK_OVERLAP   = 0x4000;
const MAX_DS          = 1;
const MAX_REFS        = 256;
const MAX_BUFFER_READ = 8 * 1024 * 1024;
const NEAR_WINDOW     = 0x80000000n; // +/- 2GB around heap object; enough for same heap arena.
const MAX_LIST_WALK   = 256;
const SESSION_SCAN_MAX_MB = 1536;

let MOD = null;
let IMAGE_BASE = null;
let IMAGE_END = null;
let LAST_DS = null;

function info(m) { console.log('[+] ' + m); }
function warn(m) { console.log('[!] ' + m); }
function fail(m) { console.log('[X] ' + m); }

function init() {
    MOD = Process.findModuleByName(MODULE_NAME);
    if (!MOD) throw new Error(MODULE_NAME + ' not loaded');
    IMAGE_BASE = BigInt(MOD.base.toString());
    IMAGE_END = IMAGE_BASE + BigInt(MOD.size);
}

function ptrToBytes(p) {
    const big = BigInt(p.toString());
    const b = [];
    for (let i = 0; i < 8; i++) {
        b.push(Number((big >> BigInt(i * 8)) & 0xffn).toString(16).padStart(2, '0'));
    }
    return b.join(' ');
}

function ptrParts(p) {
    const big = BigInt(p.toString());
    return { lo: Number(big & 0xffffffffn), hi: Number(big >> 32n) };
}

function ptrEq(a, b) {
    return a.toString() === b.toString();
}

function isImagePtr(p) {
    if (!p || p.isNull()) return false;
    const x = BigInt(p.toString());
    return x >= IMAGE_BASE && x < IMAGE_END;
}

function safePtr(addr) {
    try { return addr.readPointer(); } catch (_) { return NULL; }
}

function safeU8(addr) {
    try { return addr.readU8(); } catch (_) { return -1; }
}

function safeU32(addr) {
    try { return addr.readU32(); } catch (_) { return 0xffffffff; }
}

function findVtables() {
    const expectedFn = MOD.base.add(RVA_TYPEDESC_GETTER);
    info('image_base = ' + MOD.base);
    info('expected oCDtRootGs vtable[0] = ' + expectedFn);
    const hits = Memory.scanSync(MOD.base, MOD.size, ptrToBytes(expectedFn));
    const out = [];
    for (const h of hits) {
        const big = BigInt(h.address.toString());
        if ((big & 7n) !== 0n) continue;
        const pp = ptrParts(h.address);
        out.push({ addr: h.address, lo: pp.lo, hi: pp.hi });
    }
    info(out.length + ' aligned vtable candidate(s)');
    for (const v of out) info('  vtable: ' + v.addr);
    return out;
}

function cachedDataSourceLooksValid(ds) {
    if (!ds) return false;
    try {
        const vtbl = ds.addr.readPointer();
        const pend = ds.addr.add(OFF_JOB_SEQ_PEND).readU32();
        const done = ds.addr.add(OFF_JOB_SEQ_DONE).readU32();
        const result = ds.addr.add(OFF_JOB_RESULT).readU8();
        const flag = ds.addr.add(OFF_SAVES_DISABLED).readU8();
        return isImagePtr(vtbl) && flag === 0 && done <= pend &&
               (result < 16 || result === 0xff);
    } catch (_) {
        return false;
    }
}

function findDataSource() {
    if (cachedDataSourceLooksValid(LAST_DS)) {
        info('reusing cached data source: ' + LAST_DS.addr);
        return LAST_DS;
    }

    const vtables = findVtables();
    if (vtables.length === 0) return null;

    const ranges = Process.enumerateRanges({ protection: 'rw-', coalesce: false });
    const t0 = Date.now();
    const matches = [];

    for (const r of ranges) {
        if (r.size < STRUCT_MIN_SIZE) continue;
        let offset = 0;
        while (offset < r.size) {
            const sz = Math.min(CHUNK_SIZE, r.size - offset);
            const cbase = r.base.add(offset);
            let bytes;
            try { bytes = cbase.readByteArray(sz); }
            catch (_) { offset += CHUNK_SIZE - CHUNK_OVERLAP; continue; }
            if (!bytes || bytes.byteLength === 0) {
                offset += CHUNK_SIZE - CHUNK_OVERLAP;
                continue;
            }

            const view = new DataView(bytes);
            const limit = bytes.byteLength - 8;
            for (let p = 0; p < limit; p += 8) {
                const lo = view.getUint32(p, true);
                const hi = view.getUint32(p + 4, true);
                for (const vt of vtables) {
                    if (lo !== vt.lo || hi !== vt.hi) continue;
                    const addr = cbase.add(p);
                    let pend, done, result, flag;
                    try {
                        pend = addr.add(OFF_JOB_SEQ_PEND).readU32();
                        done = addr.add(OFF_JOB_SEQ_DONE).readU32();
                        result = addr.add(OFF_JOB_RESULT).readU8();
                        flag = addr.add(OFF_SAVES_DISABLED).readU8();
                    } catch (_) { continue; }
                    if (flag !== 0 || done > pend || (result >= 16 && result !== 0xff)) continue;
                    matches.push({ addr: addr, vtbl: vt.addr, pend: pend, done: done, result: result, flag: flag });
                    info('found data source candidate: ' + addr + ' vtbl=' + vt.addr + ' (' + (Date.now() - t0) + 'ms)');
                    if (matches.length >= MAX_DS) {
                        LAST_DS = matches[0];
                        return LAST_DS;
                    }
                    break;
                }
            }

            if (sz === r.size - offset) break;
            offset += CHUNK_SIZE - CHUNK_OVERLAP;
        }
    }
    LAST_DS = matches.length ? matches[0] : null;
    return LAST_DS;
}

function linkedListContains(head, target) {
    let cur = head;
    const seen = new Set();
    for (let i = 0; i < MAX_LIST_WALK; i++) {
        if (cur.isNull()) return { found: false, depth: i };
        const key = cur.toString();
        if (seen.has(key)) return { found: false, depth: i, loop: true };
        seen.add(key);
        if (ptrEq(cur, target)) return { found: true, depth: i };
        try { cur = cur.add(8).readPointer(); }
        catch (_) { return { found: false, depth: i, unreadable: true }; }
    }
    return { found: false, depth: MAX_LIST_WALK, truncated: true };
}

function findGameSessions(dsAddr) {
    const vt = MOD.base.add(RVA_GAMESESSION_VTABLE);
    const fp = ptrParts(vt);
    info('scanning for GameSessionGs vtable ' + vt);

    const ranges = dsAddr ? refScanRanges([dsAddr], false)
                          : Process.enumerateRanges({ protection: 'rw-', coalesce: false });
    const t0 = Date.now();
    const out = [];
    let scanned = 0;

    for (const r of ranges) {
        if (r.size < 0x180) continue;
        if ((scanned / 1024 / 1024) >= SESSION_SCAN_MAX_MB) {
            warn('stopping GameSessionGs scan after ' + SESSION_SCAN_MAX_MB +
                 ' MB without a linked-list hit');
            break;
        }
        let offset = 0;
        while (offset < r.size) {
            const sz = Math.min(CHUNK_SIZE, r.size - offset);
            const cbase = r.base.add(offset);
            let bytes;
            try { bytes = cbase.readByteArray(sz); }
            catch (_) { offset += CHUNK_SIZE - CHUNK_OVERLAP; continue; }
            if (!bytes || bytes.byteLength === 0) {
                offset += CHUNK_SIZE - CHUNK_OVERLAP;
                continue;
            }
            scanned += bytes.byteLength;
            const view = new DataView(bytes);
            const limit = bytes.byteLength - 0x180;
            for (let p = 0; p < limit; p += 8) {
                if (view.getUint32(p, true) !== fp.lo ||
                    view.getUint32(p + 4, true) !== fp.hi) {
                    continue;
                }
                const addr = cbase.add(p);
                const head = safePtr(addr.add(8));
                const p20 = safePtr(addr.add(0x20));
                const phase = safeU32(addr.add(0x150));
                const a5 = safeU8(addr.add(0xa5));
                const list = dsAddr ? linkedListContains(head, dsAddr) : { found: false };
                const plausible = !head.isNull() && !p20.isNull() &&
                                  (a5 === 0 || a5 === 1) && phase < 16;
                out.push({
                    addr: addr,
                    head: head,
                    p20: p20,
                    phase: phase,
                    a5: a5,
                    list: list,
                    plausible: plausible
                });
                if (list.found) {
                    info('found GameSessionGs owner containing data source at ' + addr +
                         ' after ' + (Date.now() - t0) + 'ms');
                    return out;
                }
            }
            if (sz === r.size - offset) break;
            offset += CHUNK_SIZE - CHUNK_OVERLAP;
        }
    }

    out.sort(function(a, b) {
        if (a.list.found && !b.list.found) return -1;
        if (!a.list.found && b.list.found) return 1;
        if (a.plausible && !b.plausible) return -1;
        if (!a.plausible && b.plausible) return 1;
        return 0;
    });

    info('GameSessionGs scan done in ' + (Date.now() - t0) + 'ms, scanned ' +
         (scanned / 1024 / 1024).toFixed(1) + ' MB, candidates=' + out.length);
    for (let i = 0; i < Math.min(out.length, 20); i++) {
        const s = out[i];
        info('  session? ' + s.addr +
             ' head=' + s.head +
             ' p20=' + s.p20 +
             ' phase=' + s.phase +
             ' a5=' + s.a5 +
             ' plausible=' + s.plausible +
             ' contains_ds=' + s.list.found +
             ' depth=' + s.list.depth);
    }
    return out;
}

function fnv1a(bytes) {
    let h = 0x811c9dc5;
    for (let i = 0; i < bytes.byteLength; i++) {
        h ^= bytes.getUint8(i);
        h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h >>> 0;
}

function countPattern(bytes, pat) {
    let n = 0;
    outer:
    for (let i = 0; i <= bytes.byteLength - pat.length; i++) {
        for (let j = 0; j < pat.length; j++) {
            if (bytes.getUint8(i + j) !== pat[j]) continue outer;
        }
        n++;
    }
    return n;
}

function sampleHex(bytes, start, count) {
    const out = [];
    const end = Math.min(bytes.byteLength, start + count);
    for (let i = start; i < end; i++) {
        out.push(bytes.getUint8(i).toString(16).padStart(2, '0'));
    }
    return out.join(' ');
}

function describeJob(dsAddr, label) {
    const job = dsAddr.add(OFF_JOB_PTR);
    const dataPtr = safePtr(job.add(JOB_DATA_PTR));
    const size = safeU32(job.add(JOB_DATA_SIZE));
    const opcode = safeU32(job.add(JOB_OPCODE));
    const extFlag = safePtr(job.add(JOB_EXT_FLAG));
    const pend = safeU32(job.add(JOB_SEQ_PEND));
    const done = safeU32(job.add(JOB_SEQ_DONE));
    const result = safeU8(job.add(JOB_RESULT));

    info(label + ' job=' + job +
         ' data=' + dataPtr + ' size=' + size +
         ' opcode=' + opcode + ' extFlag=' + extFlag +
         ' pend=' + pend + ' done=' + done + ' result=' + result);

    if (dataPtr.isNull() || size === 0 || size === 0xffffffff) return null;
    if (size > MAX_BUFFER_READ) {
        warn('buffer size too large for diagnostic read: ' + size);
        return null;
    }

    let ab;
    try { ab = dataPtr.readByteArray(size); }
    catch (e) { warn('buffer read failed: ' + e.message); return null; }
    if (!ab) return null;

    const view = new DataView(ab);
    const hash = fnv1a(view);
    const openMarkers = countPattern(view, [0x11, 0x11, 0xbb, 0xaa]);
    const closeMarkers = countPattern(view, [0x22, 0x22, 0xbb, 0xaa]);
    const tag1a = countPattern(view, [0x11, 0x11, 0xbb, 0xaa, 0x1a, 0x00, 0x00, 0x00]);
    const tag12 = countPattern(view, [0x11, 0x11, 0xbb, 0xaa, 0x12, 0x00, 0x00, 0x00]);

    info(label + ' buffer fnv1a32=0x' + hash.toString(16).padStart(8, '0') +
         ' markers=' + openMarkers + '/' + closeMarkers +
         ' tag12=' + tag12 + ' tag1a=' + tag1a);
    info(label + ' buffer first64=' + sampleHex(view, 0, 64));
    if (size > 64) info(label + ' buffer last64=' + sampleHex(view, Math.max(0, size - 64), 64));
    return { ptr: dataPtr, size: size, hash: hash, tag12: tag12, tag1a: tag1a };
}

function rangeEndBig(r) {
    return BigInt(r.base.toString()) + BigInt(r.size);
}

function rangeDistanceToTargets(r, targetBigs) {
    const start = BigInt(r.base.toString());
    const end = start + BigInt(r.size);
    let best = null;
    for (const t of targetBigs) {
        let d;
        if (t < start) d = start - t;
        else if (t >= end) d = t - end;
        else d = 0n;
        if (best === null || d < best) best = d;
    }
    return best === null ? 0n : best;
}

function refScanRanges(targets, fullScan) {
    const targetBigs = targets.map(function(t0) {
        const t = (typeof t0 === 'string') ? ptr(t0) : t0;
        return BigInt(t.toString());
    });
    const ranges = Process.enumerateRanges({ protection: 'rw-', coalesce: false });
    const selected = [];

    for (const r of ranges) {
        if (r.size < 0x1000) continue;
        if (fullScan) {
            selected.push(r);
            continue;
        }

        const start = BigInt(r.base.toString());
        const end = rangeEndBig(r);
        for (const t of targetBigs) {
            if ((start <= t && t < end) ||
                (start > t ? start - t : t - end) <= NEAR_WINDOW) {
                selected.push(r);
                break;
            }
        }
    }

    selected.sort(function(a, b) {
        const da = rangeDistanceToTargets(a, targetBigs);
        const db = rangeDistanceToTargets(b, targetBigs);
        if (da < db) return -1;
        if (da > db) return 1;
        return b.size - a.size;
    });
    return selected;
}

function scanRefsMulti(targets, opts) {
    opts = opts || {};
    const fullScan = opts.fullScan === true;
    const label = opts.label || 'refs';
    const wanted = [];
    const out = {};
    for (const t0 of targets) {
        const t = (typeof t0 === 'string') ? ptr(t0) : t0;
        const parts = ptrParts(t);
        const key = parts.hi + ':' + parts.lo;
        wanted.push({ ptr: t, lo: parts.lo, hi: parts.hi, key: key });
        out[t.toString()] = [];
    }

    const ranges = refScanRanges(targets, fullScan);
    let totalBytes = 0;
    for (const r of ranges) totalBytes += r.size;
    info(label + ': scanning ' + ranges.length + ' rw- ranges (' +
         (totalBytes / 1024 / 1024).toFixed(1) + ' MB), targets=' +
         wanted.length + ', full=' + fullScan);

    const t0 = Date.now();
    let scanned = 0;

    for (const r of ranges) {
        let offset = 0;
        while (offset < r.size) {
            const sz = Math.min(CHUNK_SIZE, r.size - offset);
            const cbase = r.base.add(offset);
            let bytes;
            try { bytes = cbase.readByteArray(sz); }
            catch (_) { offset += CHUNK_SIZE - CHUNK_OVERLAP; continue; }
            if (!bytes || bytes.byteLength === 0) {
                offset += CHUNK_SIZE - CHUNK_OVERLAP;
                continue;
            }
            scanned += bytes.byteLength;
            const view = new DataView(bytes);
            const limit = bytes.byteLength - 8;
            for (let p = 0; p < limit; p += 8) {
                const lo = view.getUint32(p, true);
                const hi = view.getUint32(p + 4, true);
                for (const w of wanted) {
                    if (lo !== w.lo || hi !== w.hi) continue;
                    const bucket = out[w.ptr.toString()];
                    bucket.push(cbase.add(p));
                    break;
                }
            }
            if (sz === r.size - offset) break;
            offset += CHUNK_SIZE - CHUNK_OVERLAP;
        }
    }
    info(label + ': done in ' + (Date.now() - t0) + 'ms, scanned ' +
         (scanned / 1024 / 1024).toFixed(1) + ' MB');
    return out;
}

function scanRefsTo(target, opts) {
    if (typeof target === 'string') target = ptr(target);
    const all = scanRefsMulti([target], opts);
    return all[target.toString()] || [];
}

function ownerScore(candidate, head) {
    let score = 0;
    const vtbl = safePtr(candidate);
    const p8 = safePtr(candidate.add(8));
    const p20 = safePtr(candidate.add(0x20));
    const a5 = safeU8(candidate.add(0xa5));
    const state = safeU32(candidate.add(0x150));

    if (isImagePtr(vtbl)) score++;
    if (p8.equals(head)) score++;
    if (!p20.isNull()) {
        const scene = safePtr(p20.add(0x18));
        if (!scene.isNull()) score++;
    }
    if (a5 === 0 || a5 === 1) score++;
    if (state < 16) score++;
    return { score: score, vtbl: vtbl, p20: p20, a5: a5, state: state };
}

function printDirectRefs(dsAddr) {
    info('scanning direct refs to data source ' + dsAddr);
    const refs = scanRefsTo(dsAddr, { fullScan: false, label: 'direct refs' }).slice(0, MAX_REFS);
    info('direct refs: ' + refs.length);
    for (let i = 0; i < Math.min(refs.length, 80); i++) {
        const refLoc = refs[i];
        const candidate = refLoc.sub(8);
        const meta = ownerScore(candidate, dsAddr);
        info('  ref@' + refLoc +
             ' candidate=' + candidate +
             ' score=' + meta.score +
             ' vtbl=' + meta.vtbl +
             ' p20=' + meta.p20 +
             ' a5=' + meta.a5 +
             ' state=' + meta.state);
    }
    return refs;
}

function findOwnerCandidates(dsAddr, maxDepth, fullScan) {
    maxDepth = maxDepth === undefined ? 2 : maxDepth;
    fullScan = fullScan === true;
    info('scanning refs/chains for owner of data source ' + dsAddr +
         ' depth=' + maxDepth + ' full=' + fullScan);
    const seenHeads = new Set([dsAddr.toString()]);
    let frontier = [dsAddr];
    const owners = [];
    const prevNodes = [];

    for (let depth = 0; depth < 8; depth++) {
        if (depth > maxDepth) break;
        const next = [];
        const refsByTarget = scanRefsMulti(frontier, {
            fullScan: fullScan,
            label: 'owner depth ' + depth
        });
        for (const head of frontier) {
            const refs = refsByTarget[head.toString()] || [];
            info('  depth ' + depth + ' head=' + head + ' refs=' + refs.length);
            for (const refLoc of refs) {
                const candidate = refLoc.sub(8);
                const meta = ownerScore(candidate, head);

                if (meta.score >= 3) {
                    owners.push({ addr: candidate, refLoc: refLoc, head: head, depth: depth, meta: meta });
                }

                // If refLoc is candidate+8 and candidate starts with an image vtable,
                // it may be the previous node in the linked list.
                if (isImagePtr(meta.vtbl) && safePtr(candidate.add(8)).equals(head)) {
                    const key = candidate.toString();
                    if (!seenHeads.has(key)) {
                        seenHeads.add(key);
                        next.push(candidate);
                        prevNodes.push(candidate);
                    }
                }
            }
        }
        if (next.length > 64) {
            warn('trimming next frontier from ' + next.length + ' to 64');
            next.length = 64;
        }
        frontier = next;
        if (frontier.length === 0) break;
    }

    owners.sort(function(a, b) { return b.meta.score - a.meta.score; });
    info('owner-like candidates: ' + owners.length);
    for (let i = 0; i < Math.min(owners.length, 20); i++) {
        const o = owners[i];
        info('  owner? ' + o.addr +
             ' score=' + o.meta.score +
             ' depth=' + o.depth +
             ' ref@' + o.refLoc +
             ' head=' + o.head +
             ' vtbl=' + o.meta.vtbl +
             ' p20=' + o.meta.p20 +
             ' a5=' + o.meta.a5 +
             ' state=' + o.meta.state);
    }
    info('previous linked-list nodes found: ' + prevNodes.length);
    return owners;
}

function doDiag(opts) {
    opts = opts || {};
    const ds = findDataSource();
    if (!ds) { fail('no plausible oCDtRootGs data source found'); return null; }
    info('selected data source: ' + ds.addr +
         ' pend=' + ds.pend + ' done=' + ds.done +
         ' result=' + ds.result + ' flag=' + ds.flag);

    const before = describeJob(ds.addr, 'before');
    const refs = printDirectRefs(ds.addr);

    if (opts.save) {
        const saveFn = new NativeFunction(MOD.base.add(RVA_SAVE_REQUEST_SYNC), 'void', ['pointer', 'pointer']);
        const job = ds.addr.add(OFF_JOB_PTR);
        info('calling save_request_sync(NULL, ' + job + ')');
        const t0 = Date.now();
        try { saveFn(NULL, job); }
        catch (e) { fail('save_request_sync threw: ' + e.message); return null; }
        info('save_request_sync returned in ' + (Date.now() - t0) + 'ms');
        describeJob(ds.addr, 'after ');
    }

    return { ds: ds.addr, before: before, refs: refs };
}

globalThis.diag = function() {
    try { return doDiag({ save: false }); }
    catch (e) { fail(e.stack || e.message); return null; }
};

globalThis.session = function() {
    try {
        const ds = findDataSource();
        if (!ds) { fail('no plausible oCDtRootGs data source found'); return []; }
        info('selected data source: ' + ds.addr);
        return findGameSessions(ds.addr);
    } catch (e) { fail(e.stack || e.message); return []; }
};

globalThis.saveDiag = function() {
    try { return doDiag({ save: true }); }
    catch (e) { fail(e.stack || e.message); return null; }
};

globalThis.refs = function(addr) {
    try {
        if (typeof addr === 'string') addr = ptr(addr);
        const out = scanRefsTo(addr, { fullScan: false, label: 'refs' });
        info('refs to ' + addr + ': ' + out.length);
        for (let i = 0; i < Math.min(out.length, 80); i++) info('  ' + out[i]);
        return out;
    } catch (e) { fail(e.stack || e.message); return []; }
};

globalThis.owners = function(depth) {
    try {
        const ds = findDataSource();
        if (!ds) { fail('no plausible oCDtRootGs data source found'); return []; }
        return findOwnerCandidates(ds.addr, depth === undefined ? 2 : depth, false);
    } catch (e) { fail(e.stack || e.message); return []; }
};

globalThis.ownersFull = function(depth) {
    try {
        const ds = findDataSource();
        if (!ds) { fail('no plausible oCDtRootGs data source found'); return []; }
        return findOwnerCandidates(ds.addr, depth === undefined ? 2 : depth, true);
    } catch (e) { fail(e.stack || e.message); return []; }
};

globalThis.finalizer = function(ownerAddr) {
    try {
        if (typeof ownerAddr === 'string') ownerAddr = ptr(ownerAddr);
        warn('EXPERIMENTAL: calling FUN_14028d6a0(' + ownerAddr + ')');
        const fn = new NativeFunction(MOD.base.add(RVA_SAVE_FINALIZER), 'void', ['pointer']);
        const t0 = Date.now();
        fn(ownerAddr);
        info('finalizer returned in ' + (Date.now() - t0) + 'ms');
    } catch (e) { fail(e.stack || e.message); }
};

try {
    init();
    console.log('Loaded diagnose_save.js. Run: diag(), session(), or saveDiag()');
} catch (e) {
    fail('init failed: ' + e.message);
}
