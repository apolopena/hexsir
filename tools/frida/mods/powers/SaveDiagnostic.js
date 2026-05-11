// SaveDiagnostic.js — EXPERIMENTAL WORK IN PROGRESS.
//
// Tools for investigating Ravenswatch's save-write pipeline:
//   - probeForBossKillSave()  arm a one-shot prep-chain dump on the
//                             next call to session_finalize_and_save
//   - findBuffer()            heap-scan to locate the live oCDtRootGs
//                             instance (the save buffer's owner)
//   - logBuffer(label)        log the buffer's live state at a labeled
//                             checkpoint
//
// Used to test the incremental-vs-single-serialize hypothesis for
// chapter-end saves: does the buffer at data_source+0x1948 grow over
// gameplay (incremental writes per event), or is it filled in one shot
// inside session_finalize_and_save? Cross-referenced against
// rw/findings/save-subsystem.md and
// rw/findings/frida-pipeline-hardware-breakpoint.md.
//
// Status: EXPERIMENTAL. This is research scaffolding, not a finalized
// API — expect interfaces to change. Re-loading is safe; prior hooks
// detach before new ones arm.
//
// REPL surface (after loadPower("SaveDiagnostic")):
//   SaveDiagnostic.probeForBossKillSave(): void
//   SaveDiagnostic.findBuffer(): NativePointer | null
//   SaveDiagnostic.logBuffer(label: string): void
//   SaveDiagnostic.dataSource: NativePointer | null

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[SaveDiagnostic] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    // File-scope: used by the file-scope hook AND by helpers shared
    // between the hook and findBuffer().
    var SESSION_FINALIZE_RVA = 0x28d6a0;
    var DS_VTABLE0_RVA       = 0x1c6830;   // typedesc-getter — vtable[0] of every oCDtRootGs

    if (!RW.SaveDiagnostic) RW.SaveDiagnostic = {};
    var SaveDiagnostic = RW.SaveDiagnostic;

    SaveDiagnostic.dataSource = SaveDiagnostic.dataSource || null;
    SaveDiagnostic._probeArmed = false;
    SaveDiagnostic._hook = SaveDiagnostic._hook || null;

    function _hex(v) { return '0x' + v.toString(16); }

    function _validatePtr(p) {
        if (p === null || p.isNull()) return false;
        return p.compare(ptr('0x10000')) > 0
            && p.compare(ptr('0x7fffffffffff')) < 0;
    }

    function _vtableInImage(p) {
        if (!_validatePtr(p)) return false;
        var end = imageBase.add(mod.size);
        return p.compare(imageBase) >= 0 && p.compare(end) < 0;
    }

    function _ptrToBytes(p) {
        var big = BigInt(p.toString());
        var out = [];
        for (var i = 0; i < 8; i++) {
            out.push(Number((big >> BigInt(i * 8)) & 0xffn).toString(16).padStart(2, '0'));
        }
        return out.join(' ');
    }

    function _readBufferState(ds) {
        // Field offsets within the live oCDtRootGs instance. Validated via
        // tools/frida/save_now.js and Ghidra decompile of
        // oCMemoryBinaryStream_grow_buffer (image+0x24e700).
        var DS_BUF_PTR_OFF        = 0x1958;   // qword: data buffer pointer
        var DS_BUF_SIZE_OFF       = 0x1960;   // u32:   current size
        var DS_BUF_CAP_OFF        = 0x1964;   // u32:   allocated capacity
        var DS_JOB_PEND_OFF       = 0x19a4;   // u32:   pending sequence
        var DS_JOB_DONE_OFF       = 0x19a8;   // u32:   completed sequence
        var DS_JOB_RESULT_OFF     = 0x19ac;   // u8:    last result code
        var DS_SAVES_DISABLED_OFF = 0x1ef4;   // u8:    saves-disabled silencer

        if (!_validatePtr(ds)) return null;
        try {
            return {
                bufPtr:   ds.add(DS_BUF_PTR_OFF).readPointer(),
                size:     ds.add(DS_BUF_SIZE_OFF).readU32(),
                capacity: ds.add(DS_BUF_CAP_OFF).readU32(),
                pend:     ds.add(DS_JOB_PEND_OFF).readU32(),
                done:     ds.add(DS_JOB_DONE_OFF).readU32(),
                result:   ds.add(DS_JOB_RESULT_OFF).readU8(),
                flag:     ds.add(DS_SAVES_DISABLED_OFF).readU8(),
            };
        } catch (e) { return null; }
    }

    function _formatBufferState(s) {
        return 'bufPtr=' + s.bufPtr +
               ' size=' + s.size +
               ' capacity=' + s.capacity +
               ' pend=' + s.pend + ' done=' + s.done +
               ' result=0x' + s.result.toString(16) +
               ' flag=' + s.flag;
    }

    // Walk the data_source linked list at session+0x8 looking for an
    // oCDtRootGs (or sibling) by matching vtable[0] == image+0x1c6830 and
    // structural fields. Used inside the probe to auto-cache without
    // requiring a manual findBuffer() call first.
    function _walkAndCacheDataSource(session) {
        var expectedFn = imageBase.add(DS_VTABLE0_RVA);
        try {
            var node = session.add(0x08).readPointer();
            for (var i = 0; i < 32 && _validatePtr(node); i++) {
                var vt = null;
                try { vt = node.readPointer(); } catch (_) {}
                if (vt && _vtableInImage(vt)) {
                    var slot0 = null;
                    try { slot0 = vt.readPointer(); } catch (_) {}
                    if (slot0 && slot0.equals(expectedFn)) {
                        var state = _readBufferState(node);
                        if (state !== null
                            && state.flag <= 1
                            && state.done <= state.pend
                            && (state.result < 16 || state.result === 0xff)) {
                            return node;
                        }
                    }
                }
                try { node = node.add(0x08).readPointer(); } catch (_) { break; }
            }
        } catch (e) {}
        return null;
    }

    // Detach prior hook (re-load safety) and arm a fresh one on the
    // session_finalize_and_save entry. The hook is permanent but inert
    // unless probeArmed is set; firing dumps the prep chain once.
    if (SaveDiagnostic._hook) {
        try { SaveDiagnostic._hook.detach(); } catch (e) {}
        SaveDiagnostic._hook = null;
    }
    SaveDiagnostic._hook = Interceptor.attach(imageBase.add(SESSION_FINALIZE_RVA), {
        onEnter: function (args) {
            if (!SaveDiagnostic._probeArmed) return;
            SaveDiagnostic._probeArmed = false;
            var tag = ' [PROBE/sfas]';
            try {
                var session = this.context.rcx;
                console.log(tag + ' enter session=' + session);

                // Auto-cache data_source via the linked-list walk.
                try {
                    var ds = _walkAndCacheDataSource(session);
                    if (ds !== null) {
                        SaveDiagnostic.dataSource = ds;
                        var state = _readBufferState(ds);
                        if (state !== null) {
                            console.log(tag + '/buffer ds=' + ds + ' ' + _formatBufferState(state));
                        } else {
                            console.log(tag + '/buffer ds=' + ds + ' state-read FAIL');
                        }
                    } else {
                        console.log(tag + '/buffer no oCDtRootGs found in data_source list');
                    }
                } catch (e) {
                    console.log(tag + '/buffer walk ERR ' + e.message);
                }

                var gate = '?';
                try { gate = '0x' + session.add(0xa5).readU8().toString(16); }
                catch (e) { gate = 'ERR:' + e.message; }
                console.log(tag + ' session+0xa5 (saves-enabled gate) = ' + gate);

                // Verified chain (Ghidra decompile of session_finalize_and_save,
                // 2026-05-04): scene_manager = *(*(session+0x20)+0x18). Decompile
                // pins it to this single path; no candidate logic.
                var outer = null, sceneManager = null, gameMode = null,
                    factory = null, factoryVT = null, createFn = null;
                try { outer = session.add(0x20).readPointer(); } catch (e) {
                    console.log(tag + ' *(session+0x20) read fail ' + e.message); return;
                }
                console.log(tag + ' *(session+0x20)        = ' + outer);

                try { sceneManager = outer.add(0x18).readPointer(); } catch (e) {
                    console.log(tag + ' scene_manager (+0x18) read fail ' + e.message); return;
                }
                console.log(tag + ' scene_manager          = ' + sceneManager);

                try { gameMode = sceneManager.add(0x708).readPointer(); } catch (e) {
                    console.log(tag + ' GameModeDefault (+0x708) read fail ' + e.message); return;
                }
                var gmVT = null;
                try { gmVT = gameMode.readPointer(); } catch (e) {}
                var gmVtInImage = _vtableInImage(gmVT);
                console.log(tag + ' GameModeDefault        = ' + gameMode +
                            ' vt=' + gmVT +
                            (gmVtInImage ? ' (RVA +' + _hex(gmVT.sub(imageBase).toUInt32()) + ')'
                                         : ' (NOT in image — chain may have shifted)'));

                try { factory = gameMode.add(0x38).readPointer(); } catch (e) {
                    console.log(tag + ' factory (+0x38) read fail ' + e.message); return;
                }
                if (!_validatePtr(factory)) {
                    console.log(tag + ' factory invalid: ' + factory + ' — aborting phase 2'); return;
                }

                try { factoryVT = factory.readPointer(); } catch (e) {
                    console.log(tag + ' factory vtable read fail ' + e.message); return;
                }
                try { createFn = factoryVT.add(0xf8).readPointer(); } catch (e) {
                    console.log(tag + ' factoryVT+0xf8 read fail ' + e.message); return;
                }
                var factoryVtRVA = _vtableInImage(factoryVT)
                    ? _hex(factoryVT.sub(imageBase).toUInt32()) : 'NOT-IN-IMAGE';
                var createRVA = _vtableInImage(createFn)
                    ? _hex(createFn.sub(imageBase).toUInt32()) : 'NOT-IN-IMAGE';
                console.log(tag + ' factory_vtable=' + factoryVT + ' (RVA +' + factoryVtRVA + ')' +
                            ' create_serializer=' + createFn + ' (RVA +' + createRVA + ')');

                if (!_vtableInImage(createFn)) {
                    console.log(tag + ' create_serializer not in image; aborting phase 2'); return;
                }

                var phase2 = Interceptor.attach(createFn, {
                    onLeave: function (retval) {
                        try {
                            var serializer = retval;
                            console.log(tag + ' phase2 create_serializer returned ' + serializer);
                            if (!_validatePtr(serializer)) {
                                console.log(tag + ' phase2 retval invalid; aborting phase 3'); return;
                            }
                            var serialVT = serializer.readPointer();
                            if (!_vtableInImage(serialVT)) {
                                console.log(tag + ' phase2 serializer vtable NOT in image: ' + serialVT); return;
                            }
                            var serializeFn = serialVT.add(0x40).readPointer();
                            var serialVtRVA = _hex(serialVT.sub(imageBase).toUInt32());
                            var serializeRVA = _vtableInImage(serializeFn)
                                ? _hex(serializeFn.sub(imageBase).toUInt32()) : 'NOT-IN-IMAGE';
                            console.log(tag + ' phase2 serializer_vtable=' + serialVT +
                                        ' (RVA +' + serialVtRVA + ')' +
                                        ' serialize=' + serializeFn + ' (RVA +' + serializeRVA + ')');

                            if (!_vtableInImage(serializeFn)) return;

                            var phase3 = Interceptor.attach(serializeFn, {
                                onEnter: function (args3) {
                                    try {
                                        console.log(tag + ' phase3 serialize enter rcx=' +
                                                    this.context.rcx + ' rdx=' + this.context.rdx);
                                        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                            .slice(0, 8)
                                            .map(function (a) {
                                                var inImg = a.compare(imageBase) >= 0
                                                    && a.compare(imageBase.add(mod.size)) < 0;
                                                return a + (inImg
                                                    ? ' (img+' + _hex(a.sub(imageBase).toUInt32()) + ')'
                                                    : '');
                                            })
                                            .join(' | ');
                                        console.log(tag + ' phase3 backtrace: ' + bt);
                                    } catch (e) {
                                        console.log(tag + ' phase3 onEnter ERR ' + e.message);
                                    }
                                    phase3.detach();
                                }
                            });
                        } catch (e) {
                            console.log(tag + ' phase2 onLeave ERR ' + e.message);
                        }
                        phase2.detach();
                    }
                });
            } catch (e) {
                console.log(tag + ' onEnter ERR ' + e.message);
            }
        }
    });

    /*
     * ----------------------------------------------------------------
     * SaveDiagnostic.probeForBossKillSave(): void
     *
     * Arm a one-shot probe on session_finalize_and_save. The next call
     * to that function (any route — chapter-end Save and Quit, settings
     * save, etc.) dumps the prep chain (factory, create_serializer,
     * serialize callsite + backtrace) and auto-caches the data_source
     * via the linked-list walk.
     *
     * Result:
     *   The next save event logs [PROBE/sfas] / [PROBE/sfas/buffer]
     *   lines and arms phase-2/3 hooks that auto-detach. Disarms
     *   itself after firing. Anti-debug safe (pure Frida hooks).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Toggles SaveDiagnostic._probeArmed. The permanent hook on
     *   session_finalize_and_save (RVA 0x28d6a0) checks the flag on
     *   entry and, if armed, walks the verified chain
     *     session+0x20 -> +0x18 -> +0x708 -> +0x38 -> *vt[+0xf8].
     *   Phase 2 hooks the returned serializer's vtable[+0x40] = serialize.
     *   Phase 3 captures rcx/rdx + 8-frame backtrace, then detaches.
     *   See rw/findings/frida-pipeline-hardware-breakpoint.md and
     *   rw/findings/save-subsystem.md.
     */
    SaveDiagnostic.probeForBossKillSave = function () {
        SaveDiagnostic._probeArmed = true;
        console.log('[SaveDiagnostic] PROBE-BOSS-KILL-SAVE armed: next call to ' +
                    'session_finalize_and_save (image+' + _hex(SESSION_FINALIZE_RVA) +
                    ') will dump the prep chain');
    };

    /*
     * ----------------------------------------------------------------
     * SaveDiagnostic.findBuffer(): NativePointer | null
     *
     * Heap-scan to locate the live oCDtRootGs instance and cache it on
     * SaveDiagnostic.dataSource. Modeled on tools/frida/save_now.js.
     * Scan typically takes 10–80s. Call once after a profile/run is
     * loaded. If multiple instances match, refuses to auto-pick.
     *
     * Result:
     *   Returns the NativePointer on single match (also cached on
     *   .dataSource). Returns null on no match or ambiguous match.
     *   Logs scan progress and candidate states.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Phase 1: scan image for qwords == image+0x1c6830 (the
     *   typedesc-getter that occupies vtable[0] of every oCDtRootGs).
     *   Each match is a candidate vtable.
     *   Phase 2: scan rw- ranges for any qword equal to those vtable
     *   addresses; each match is a candidate instance. Validate
     *   structurally (saves-disabled flag in {0,1}, done<=pend, result
     *   small or sentinel). Same discriminator as save_now.js.
     */
    SaveDiagnostic.findBuffer = function () {
        // Heap-scan tuning (mirrors tools/frida/save_now.js).
        var HEAP_SCAN_MIN_RANGE_SIZE = 0x4000;
        var HEAP_SCAN_CHUNK          = 16 * 1024 * 1024;
        var HEAP_SCAN_OVERLAP        = 0x4000;

        var tag = '[SaveDiagnostic.findBuffer]';
        var expectedFn = imageBase.add(DS_VTABLE0_RVA);
        console.log(tag + ' scanning image for vtable[0]=' + expectedFn);

        var vtblHits;
        try { vtblHits = Memory.scanSync(imageBase, mod.size, _ptrToBytes(expectedFn)); }
        catch (e) { console.log(tag + ' image scan ERR ' + e.message); return null; }
        var vtables = vtblHits.filter(function (h) {
            return Number(BigInt(h.address.toString()) & 7n) === 0;
        }).map(function (h) { return h.address; });
        console.log(tag + ' vtable candidates: ' + vtables.length);
        if (vtables.length === 0) {
            console.log(tag + ' no vtables; engine state may be uninitialized');
            return null;
        }

        var ranges = Process.enumerateRanges({ protection: 'rw-', coalesce: false });
        console.log(tag + ' scanning ' + ranges.length + ' rw- ranges');
        var t0 = Date.now();
        var candidates = [];

        for (var ri = 0; ri < ranges.length; ri++) {
            var r = ranges[ri];
            if (r.size < HEAP_SCAN_MIN_RANGE_SIZE) continue;
            var off = 0;
            while (off < r.size) {
                var sz = Math.min(HEAP_SCAN_CHUNK, r.size - off);
                var cbase = r.base.add(off);
                var bytes;
                try { bytes = cbase.readByteArray(sz); }
                catch (_) { off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP; continue; }
                if (!bytes || bytes.byteLength === 0) {
                    off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP; continue;
                }
                var view = new DataView(bytes);
                var limit = bytes.byteLength - 8;
                for (var p = 0; p < limit; p += 8) {
                    var lo = view.getUint32(p, true);
                    var hi = view.getUint32(p + 4, true);
                    for (var vi = 0; vi < vtables.length; vi++) {
                        var vbig = BigInt(vtables[vi].toString());
                        var vlo = Number(vbig & 0xffffffffn);
                        var vhi = Number(vbig >> 32n);
                        if (lo !== vlo || hi !== vhi) continue;
                        var addr = cbase.add(p);
                        var state = _readBufferState(addr);
                        if (state === null) break;
                        if (state.flag <= 1 && state.done <= state.pend &&
                            (state.result < 16 || state.result === 0xff)) {
                            candidates.push({ addr: addr, vtbl: vtables[vi], state: state });
                        }
                        break;
                    }
                }
                if (sz === r.size - off) break;
                off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP;
            }
        }
        var dt = Date.now() - t0;
        console.log(tag + ' scan complete in ' + dt + 'ms; ' + candidates.length + ' candidate(s)');
        for (var ci = 0; ci < candidates.length; ci++) {
            console.log(tag + '   ' + candidates[ci].addr + '  ' + _formatBufferState(candidates[ci].state));
        }

        if (candidates.length === 0) {
            console.log(tag + ' no oCDtRootGs found — is a profile/run loaded?');
            return null;
        }
        if (candidates.length > 1) {
            console.log(tag + ' MULTIPLE candidates — refusing to auto-pick. ' +
                        'Inspect log and set SaveDiagnostic.dataSource manually.');
            return null;
        }
        SaveDiagnostic.dataSource = candidates[0].addr;
        console.log(tag + ' cached dataSource = ' + SaveDiagnostic.dataSource);
        return SaveDiagnostic.dataSource;
    };

    /*
     * ----------------------------------------------------------------
     * SaveDiagnostic.logBuffer(label: string): void
     *
     * Read the cached dataSource's buffer state and log one labeled
     * line. Call at gameplay checkpoints during a run to time-series
     * the buffer growth (see save-subsystem.md §"Usage protocol").
     *
     * Result:
     *   Logs "[BUFFER/<label>] ds=... bufPtr=... size=N capacity=N
     *   pend=... done=... result=... flag=...".
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads bufPtr/size/capacity at +0x1958/+0x1960/+0x1964 and the
     *   job sequence numbers at +0x19a4..+0x19ac and the
     *   saves-disabled gate at +0x1ef4. Field offsets validated via
     *   Ghidra decompile of oCMemoryBinaryStream_grow_buffer
     *   (image+0x24e700) showing the embedded memstream layout.
     */
    SaveDiagnostic.logBuffer = function (label) {
        if (!label || typeof label !== 'string') {
            console.log('[SaveDiagnostic.logBuffer] usage: SaveDiagnostic.logBuffer("label-string")');
            return;
        }
        if (SaveDiagnostic.dataSource === null) {
            console.log('[BUFFER/' + label + '] no cached dataSource — call SaveDiagnostic.findBuffer() first');
            return;
        }
        var state = _readBufferState(SaveDiagnostic.dataSource);
        if (state === null) {
            console.log('[BUFFER/' + label + '] cache=' + SaveDiagnostic.dataSource +
                        ' — read FAIL (heap may have changed; re-run findBuffer)');
            return;
        }
        console.log('[BUFFER/' + label + '] ds=' + SaveDiagnostic.dataSource +
                    ' ' + _formatBufferState(state));
    };

    RW.registerMod("power:SaveDiagnostic", version);
    console.log("[SaveDiagnostic] " + version + " loaded (EXPERIMENTAL). Try: SaveDiagnostic.findBuffer()");
})();

// Top-level alias for REPL convenience
var SaveDiagnostic = RW.SaveDiagnostic;
