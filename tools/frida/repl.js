// Ravenswatch REPL toolkit — load once, iterate interactively.
//
// Usage:
//   frida -n Ravenswatch.exe -l repl.js
//
// On load, prints range stats and exposes these globals in the REPL:
//
//   help()                              — print this help
//   stats()                             — re-print range/protection stats
//   scan(filters?)                      — scan for oCDtRootGs candidates
//                                         filters object (all optional):
//                                           protections: ['rw-','rwx']  (default: both)
//                                           maxPend: 10000              (pend cap)
//                                           checkFlag: true             (require flag in {0,1})
//                                           checkResult: true           (require result < 16 or 0xff)
//                                           checkSeqInvariant: true     (require done <= pend)
//                                           verbose: true               (print samples)
//   dump(addr, n=64)                    — dump n qwords starting at addr
//   field(addr, off, type='u32')        — read addr+off as type (u8|u16|u32|u64|ptr)
//   imageInfo()                         — print image base/size/bounds
//   typedesc()                          — read g_oCDtRootGs_typedesc value
//   imageRanges()                       — list module's PE sections
//
// Call any of these directly at the REPL prompt:
//
//   [Local::Ravenswatch.exe ]-> scan()
//   [Local::Ravenswatch.exe ]-> scan({ checkFlag: false })
//   [Local::Ravenswatch.exe ]-> dump(ptr('0x1234abcd'))

'use strict';

const MODULE_NAME = 'Ravenswatch.exe';
const RVA_OCDTROOTGS_TYPEDESC = 0x14475a0;
const RVA_SAVE_REQUEST_SYNC   = 0x6797b0;

const STRUCT_MIN_SIZE = 0x2000;
const CHUNK_SIZE      = 16 * 1024 * 1024;
const CHUNK_OVERLAP   = 0x4000;

// ---- module + bounds (cached on load) -----------------------------------

let MOD = null;
let BASE_HI = 0, BASE_LO = 0, END_HI = 0, END_LO = 0;

function init() {
    MOD = Process.findModuleByName(MODULE_NAME);
    if (!MOD) throw new Error(MODULE_NAME + ' not loaded');
    const baseBig = BigInt(MOD.base.toString());
    const endBig  = baseBig + BigInt(MOD.size);
    BASE_HI = Number(baseBig >> 32n);
    BASE_LO = Number(baseBig & 0xffffffffn);
    END_HI  = Number(endBig >> 32n);
    END_LO  = Number(endBig & 0xffffffffn);
}

// ---- exposed REPL functions ---------------------------------------------

function help() {
    console.log([
        '',
        'Available REPL functions:',
        '  help()            print this help',
        '  imageInfo()       image base, size, bounds',
        '  stats()           memory range stats by protection',
        '  imageRanges()     PE sections of the module',
        '  typedesc()        read g_oCDtRootGs_typedesc value',
        '  scan(filters?)    scan heap for oCDtRootGs candidates',
        '                    filters: { protections, maxPend, checkFlag,',
        '                              checkResult, checkSeqInvariant, verbose }',
        '  dump(addr, n=64)  dump qwords starting at addr',
        '  field(addr, off, type)  read field at addr+off (u8|u16|u32|u64|ptr)',
        ''
    ].join('\n'));
}
globalThis.help = help;

function imageInfo() {
    console.log('image_base = ' + MOD.base);
    console.log('image_size = 0x' + MOD.size.toString(16));
    console.log('bounds: hi=' + BASE_HI.toString(16) + ' lo=' + BASE_LO.toString(16) +
                ' endLo=' + END_LO.toString(16));
    return MOD;
}
globalThis.imageInfo = imageInfo;

function imageRanges() {
    // Frida's Module.enumerateRanges shows the PE's loaded sections.
    const ranges = MOD.enumerateRanges('---');
    for (const r of ranges) {
        console.log('  ' + r.base + ' size=0x' + r.size.toString(16) +
                    ' prot=' + r.protection);
    }
    return ranges;
}
globalThis.imageRanges = imageRanges;

function typedesc() {
    const ptr = MOD.base.add(RVA_OCDTROOTGS_TYPEDESC);
    let val;
    try { val = ptr.readPointer(); }
    catch (e) { console.log('error: ' + e.message); return null; }
    console.log('g_oCDtRootGs_typedesc @ ' + ptr + ' = ' + val);
    return val;
}
globalThis.typedesc = typedesc;

function stats() {
    const variants = ['rw-', 'rwx', 'r-x', 'r--', 'rwc', 'rwxc', '---'];
    let totalRanges = 0, totalBytes = 0;
    console.log('Per-protection range counts:');
    for (const prot of variants) {
        let ranges = [];
        try {
            ranges = Process.enumerateRanges({ protection: prot, coalesce: false });
        } catch (e) {
            console.log('  ' + prot + ': error ' + e.message);
            continue;
        }
        let total = 0;
        for (const r of ranges) total += r.size;
        if (ranges.length > 0) {
            console.log('  ' + prot + ': ' + ranges.length + ' ranges, ' +
                        (total / 1024 / 1024).toFixed(1) + ' MB');
        }
        totalRanges += ranges.length;
        totalBytes += total;
    }
    console.log('Total queried: ' + totalRanges + ' ranges, ' +
                (totalBytes / 1024 / 1024).toFixed(1) + ' MB');
}
globalThis.stats = stats;

// ---- the main scanner ---------------------------------------------------

function scan(filters) {
    filters = filters || {};
    const opts = {
        protections:        filters.protections        || ['rw-', 'rwx'],
        maxPend:            filters.maxPend            !== undefined ? filters.maxPend : 10000,
        checkFlag:          filters.checkFlag          !== undefined ? filters.checkFlag : true,
        checkResult:        filters.checkResult        !== undefined ? filters.checkResult : true,
        checkSeqInvariant:  filters.checkSeqInvariant  !== undefined ? filters.checkSeqInvariant : true,
        verbose:            filters.verbose            !== undefined ? filters.verbose : true,
        maxResults:         filters.maxResults         || 50
    };

    console.log('scanning protections=' + JSON.stringify(opts.protections) +
                ' maxPend=' + opts.maxPend +
                ' checkFlag=' + opts.checkFlag +
                ' checkResult=' + opts.checkResult +
                ' checkSeqInvariant=' + opts.checkSeqInvariant);

    // Collect ranges from all requested protections, dedup by base.
    const seen = new Set();
    const collected = [];
    for (const prot of opts.protections) {
        let ranges = [];
        try { ranges = Process.enumerateRanges({ protection: prot, coalesce: false }); }
        catch (_) { continue; }
        for (const r of ranges) {
            const key = r.base.toString();
            if (!seen.has(key)) { seen.add(key); collected.push(r); }
        }
    }

    const matches = [];
    let scannedBytes = 0;
    const t0 = Date.now();

    for (const r of collected) {
        if (r.size < STRUCT_MIN_SIZE) continue;
        scannedBytes += r.size;
        scanRange(r.base, r.size, opts, matches);
        if (matches.length >= opts.maxResults) break;
    }

    const dt = Date.now() - t0;
    console.log('scanned ' + collected.length + ' ranges, ' +
                (scannedBytes / 1024 / 1024).toFixed(1) + ' MB in ' + dt + 'ms');
    console.log('matches: ' + matches.length);

    if (opts.verbose) {
        for (let i = 0; i < Math.min(matches.length, 10); i++) {
            const m = matches[i];
            console.log('  ' + m.addr + '  vtbl=' + m.vtbl +
                        '  pend=' + m.pend + ' done=' + m.done +
                        ' result=' + m.result + ' flag=' + m.flag);
        }
        if (matches.length > 10) console.log('  ... (' + (matches.length - 10) + ' more)');
    }

    return matches;
}
globalThis.scan = scan;

function scanRange(base, size, opts, out) {
    let offset = 0;
    while (offset < size) {
        const remaining = size - offset;
        const chunkSize = Math.min(CHUNK_SIZE, remaining);
        const chunkBase = base.add(offset);

        let bytes;
        try { bytes = chunkBase.readByteArray(chunkSize); }
        catch (_) { offset += CHUNK_SIZE - CHUNK_OVERLAP; continue; }
        if (!bytes || bytes.byteLength === 0) {
            offset += CHUNK_SIZE - CHUNK_OVERLAP;
            continue;
        }

        scanChunk(chunkBase, bytes, opts, out);
        if (out.length >= opts.maxResults) return;

        if (chunkSize === remaining) break;
        offset += CHUNK_SIZE - CHUNK_OVERLAP;
    }
}

function scanChunk(chunkBase, bytes, opts, out) {
    const view = new DataView(bytes);
    const limit = bytes.byteLength - STRUCT_MIN_SIZE - 8;
    if (limit < 0) return;

    for (let p = 0; p < limit; p += 8) {
        const vtblHi = view.getUint32(p + 4, true);
        if (vtblHi !== BASE_HI) continue;
        const vtblLo = view.getUint32(p, true);
        if (vtblLo < BASE_LO || vtblLo >= END_LO) continue;

        const pend = view.getUint32(p + 0x19a4, true);
        if (pend > opts.maxPend) continue;

        if (opts.checkSeqInvariant) {
            const done = view.getUint32(p + 0x19a8, true);
            if (done > pend) continue;
        }

        if (opts.checkResult) {
            const r = view.getUint8(p + 0x19ac);
            if (r >= 16 && r !== 0xff) continue;
        }

        if (opts.checkFlag) {
            const f = view.getUint8(p + 0x1ef4);
            if (f !== 0 && f !== 1) continue;
        }

        out.push({
            addr:   chunkBase.add(p),
            vtbl:   view.getUint32(p, true).toString(16) + ' (full ptr in addr)',
            pend:   pend,
            done:   view.getUint32(p + 0x19a8, true),
            result: view.getUint8(p + 0x19ac),
            flag:   view.getUint8(p + 0x1ef4)
        });
        if (out.length >= opts.maxResults) return;
    }
}

// ---- dump and field accessors -------------------------------------------

function dump(addr, n) {
    n = n || 64;
    if (typeof addr === 'string') addr = ptr(addr);
    for (let i = 0; i < n; i++) {
        const a = addr.add(i * 8);
        let v;
        try { v = a.readPointer(); }
        catch (_) { console.log('  +' + (i*8).toString(16).padStart(4,'0') + '  <unreadable>'); continue; }
        console.log('  +' + (i*8).toString(16).padStart(4,'0') + '  ' + v);
    }
}
globalThis.dump = dump;

function field(addr, off, type) {
    if (typeof addr === 'string') addr = ptr(addr);
    type = type || 'u32';
    const a = addr.add(off);
    try {
        if (type === 'u8')  return a.readU8();
        if (type === 'u16') return a.readU16();
        if (type === 'u32') return a.readU32();
        if (type === 'u64') return a.readU64();
        if (type === 'ptr') return a.readPointer();
        if (type === 's')   return a.readCString();
    } catch (e) { return 'error: ' + e.message; }
    return 'unknown type';
}
globalThis.field = field;

// ---- entry --------------------------------------------------------------

try {
    init();
    imageInfo();
    console.log('');
    console.log('Frida REPL toolkit loaded. Type help() for commands.');
    console.log('Quick start: scan() to look for the data source with default filters.');
} catch (e) {
    console.log('init failed: ' + e.message);
}
