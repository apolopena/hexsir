// enemy_capture.js — capture every oCDtEntityCpntEnemyController
// construction during a window. One fire per enemy spawn, exact 1:1.
//
// Why a separate hook from spawn_capture.js:
//   spawn_capture.js hooks oCEntity::ctor (RVA 0x6c96f0). That fires
//   ~283 times per cauldron fight including barriers, decorations,
//   anchors, etc. — and the component hashmap on those captures is
//   either empty (ctor too early) or unreadable (slab reused after
//   destruction). enemy_capture targets the EnemyController component
//   ctor directly: one fire = one enemy, no filter, no race.
//
// Hook target:
//   oCDtEntityCpntEnemyController_ctor at RVA 0x37bbe0. Single-arg
//   `void ctor(this)`. Zero-inits ~0x108 bytes, installs vtable at
//   RVA 0xf0a6c8. Class hash key 0x1561073c.
//
// Owner-entity offset is unknown (NOT set by the ctor — the engine
// writes it during a later component-attach step). dump() discovers
// it empirically by scanning each captured controller's first 0x108
// bytes for a qword whose deref is the oCEntity vtable (RVA 0xf4cc40).
//
// Usage:
//   loadMod("enemy_capture")
//   EnemyCapture.start()
//   <fight a cauldron / approach a camp / etc.>
//   EnemyCapture.stop()        // do this BEFORE the enemies die when
//                              // possible — destroyed controllers are
//                              // unreadable for the dump scan
//   EnemyCapture.dump()        // per-controller hex addr + matching
//                              // offsets; aggregate histogram so the
//                              // single-stable-offset answer pops out

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[EnemyCapture] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;
    var imageEnd  = imageBase.add(mod.size);

    var ENEMY_CTOR_RVA   = 0x37bbe0;
    var OCENTITY_VT_RVA  = 0xf4cc40;
    var SCAN_BYTES       = 0x108;     // ctor zero-inits up to +0x100; round up to qword boundary

    if (!RW.EnemyCapture) RW.EnemyCapture = {};
    var EnemyCapture = RW.EnemyCapture;

    if (EnemyCapture._hook) { try { EnemyCapture._hook.detach(); } catch (e) {} }
    EnemyCapture._hook = null;
    EnemyCapture._captures = EnemyCapture._captures || [];

    function vtRva(obj) {
        try {
            var vt = obj.readPointer();
            if (vt.compare(imageBase) >= 0 && vt.compare(imageEnd) < 0) {
                return vt.sub(imageBase).toInt32();
            }
        } catch (e) {}
        return -1;
    }

    /*
     * ----------------------------------------------------------------
     * EnemyCapture.start(): void
     *
     * Arm a hook at oCDtEntityCpntEnemyController_ctor (RVA 0x37bbe0).
     * Each fire captures (ts, controller) — `controller` is the
     * `this` pointer passed in RCX. Wipes any prior captures.
     *
     * Result: logs "[EnemyCapture] armed". Buffer fills as enemies
     * spawn. Detaches automatically on re-load (idempotent).
     *
     * Caveats:
     *   - Capture is exact 1:1 with enemy creation. No filter needed.
     *   - Owner-entity pointer is NOT available at ctor time; only
     *     the controller pointer is captured here. dump() resolves
     *     the owner offset later via memory scan.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Hooks RVA 0x37bbe0 (oCDtEntityCpntEnemyController_ctor).
     *   onEnter: stash ptr(args[0]) and Date.now() on `this`.
     *   onLeave: append { ts, controller } to _captures.
     *   No work in the hot path beyond pointer capture — keeps the
     *   per-spawn cost negligible.
     */
    EnemyCapture.start = function () {
        EnemyCapture._captures = [];
        if (EnemyCapture._hook) { try { EnemyCapture._hook.detach(); } catch (e) {} }
        EnemyCapture._hook = Interceptor.attach(imageBase.add(ENEMY_CTOR_RVA), {
            onEnter: function (args) {
                try {
                    this._ctrl = ptr(args[0]);
                    this._ts   = Date.now();
                } catch (e) { this._ctrl = null; }
            },
            onLeave: function () {
                if (!this._ctrl) return;
                EnemyCapture._captures.push({ ts: this._ts, controller: this._ctrl });
            },
        });
        console.log("[EnemyCapture] armed at oCDtEntityCpntEnemyController_ctor (RVA 0x" +
                    ENEMY_CTOR_RVA.toString(16) + ")");
    };

    /*
     * ----------------------------------------------------------------
     * EnemyCapture.stop(): void
     *
     * Detach the hook and print the capture count. Captures stay in
     * the buffer for dump() / programmatic access via _captures.
     * ----------------------------------------------------------------
     */
    EnemyCapture.stop = function () {
        if (EnemyCapture._hook) { try { EnemyCapture._hook.detach(); } catch (e) {} }
        EnemyCapture._hook = null;
        console.log("[EnemyCapture] detached. " + EnemyCapture._captures.length + " enemies captured");
    };

    /*
     * ----------------------------------------------------------------
     * EnemyCapture.dump(): void
     *
     * Per-controller report + aggregate offset histogram. For each
     * captured controller, scans the first 0x108 bytes a qword at a
     * time looking for any value V such that ptr(V) is in the module
     * range and *(uint*)V == OCENTITY_VT_RVA when reduced to RVA. The
     * single-stable offset that matches across most/all controllers
     * is the owner-entity field.
     *
     * Run after stop() and before killing every enemy (a destroyed
     * controller's memory may have been freed/reused — those reads
     * will fault or yield garbage).
     *
     * Result:
     *   For each controller: hex address + the offsets at which an
     *   oCEntity backref was found (typically 0 or 1 hits).
     *   Aggregate: histogram of "offset X matched in N/total
     *   controllers" — sorted by frequency. The owner offset will
     *   dominate the histogram.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   For each (ctrl, off in 0..SCAN_BYTES step 8):
     *     try { v = ctrl.add(off).readPointer(); }
     *     if (v in [imageBase, imageEnd))    // pointer-shaped within module is a vtable, not the entity
     *        continue
     *     if (vtRva(v) === OCENTITY_VT_RVA)
     *        record (ctrl_idx, off)
     *   Aggregate by off; print ordered by hit count descending.
     *
     *   Note: also records hits where the qword value itself is a
     *   heap pointer that, when dereferenced, yields the oCEntity
     *   vtable. Vtables (which would also be in module range) are
     *   excluded by the "pointer-shaped within module" filter so the
     *   sub-object vtable slots at +0x18 / +0x38 don't pollute the
     *   histogram.
     */
    EnemyCapture.dump = function () {
        var caps = EnemyCapture._captures;
        if (!caps.length) { console.log("[EnemyCapture] no captures"); return; }

        var hist = {};      // offset -> hit count
        var perCtrl = [];   // [{ctrl, hits:[off, ...]}]

        caps.forEach(function (c) {
            var hits = [];
            for (var off = 0; off < SCAN_BYTES; off += 8) {
                var v;
                try { v = c.controller.add(off).readPointer(); }
                catch (e) { continue; }

                // Skip pointers into the module image (vtables, statics, etc.)
                if (v.compare(imageBase) >= 0 && v.compare(imageEnd) < 0) continue;

                // Heap-shaped: check if it points to an oCEntity.
                if (vtRva(v) === OCENTITY_VT_RVA) {
                    hits.push(off);
                    hist[off] = (hist[off] || 0) + 1;
                }
            }
            perCtrl.push({ ctrl: c.controller, hits: hits });
        });

        console.log("[EnemyCapture.dump] " + caps.length + " controllers; oCEntity-backref scan over first 0x" +
                    SCAN_BYTES.toString(16) + " bytes:");

        perCtrl.forEach(function (r, i) {
            var hitStr = r.hits.length
                ? r.hits.map(function (o) { return "+0x" + o.toString(16); }).join(",")
                : "(none)";
            console.log("  [" + i + "] " + r.ctrl + " hits: " + hitStr);
        });

        var offs = Object.keys(hist).map(function (k) { return parseInt(k, 10); });
        offs.sort(function (a, b) { return hist[b] - hist[a]; });
        console.log("\n[EnemyCapture.dump] offset histogram (most frequent first):");
        if (!offs.length) {
            console.log("  (no oCEntity backrefs found in any controller)");
        } else {
            offs.forEach(function (o) {
                console.log("  +0x" + o.toString(16) + "  matched " + hist[o] + "/" + caps.length + " controllers");
            });
        }
    };

    RW.registerMod("enemy_capture", version);
    console.log("[EnemyCapture] " + version + " loaded. start() / stop() / dump()");
})();

// Top-level alias
var EnemyCapture = RW.EnemyCapture;
