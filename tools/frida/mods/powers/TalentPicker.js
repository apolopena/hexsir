// TalentPicker.js — control SkillController_roll_proposed_skills.
//
// Forces deterministic talent rolls by overwriting the TLS seed slot
// the picker reads on entry. Also exposes a byte-patch for the per-slot
// picker count and one-shot diagnostics for slot/pool state.
//
// Status: PARTIALLY VERIFIED. Seed forcing (force / forceFresh /
// unforce) hasn't been exhaustively tested — the TLS write path and
// the param_3 nulling are live-confirmed individually but rerolls,
// edge cases (first-entry-per-thread race), and reroll-stability under
// forceFresh need more shake-out. Picker-count byte patch is the
// best-tested path. Treat outputs critically until the suite is
// rerun and confirmed.
//
// Why TLS via NtQueryInformationThread:
//   - GS-relative shims fail. Frida's NativeFunction call doesn't preserve
//     the game thread's GS base — even `mov rax, gs:[0x30]` faults.
//   - Hooking at the IMUL site (mid-loop) crashed the game (Frida relocator
//     issue with IMUL using [R12 + R9*1 + 4] addressing).
//   - Solution: get the TEB via NtQueryInformationThread (syscall, GS-free).
//     Walk TEB+0x58 → TLS array → array[0] = TLS data. Write at +0xff3c.
//     All reads use Memory.readPointer (absolute addresses, no GS).
//
// Race timing: on the FIRST entry per thread, the function's own
// __dyn_tls_on_demand_init hasn't run yet, so the TLS data block may be
// too small to access offset 0xff3c. We catch the access violation and
// skip — by the second entry, init has run and the write succeeds.
//
// REPL surface (after loadPower("TalentPicker")):
//   TalentPicker.force(seed: number): void
//   TalentPicker.forceFresh(seed: number): void
//   TalentPicker.unforce(): void
//   TalentPicker.count(n: number): void
//   TalentPicker.unpatchCount(): void
//   TalentPicker.dumpSlots(): void
//   TalentPicker.dumpPool(): void
//   TalentPicker.clearHeld(slotIdx?: number): void
//   TalentPicker.mark(label: string): void
//   TalentPicker.entries: number   (count of picker entries seen)

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[TalentPicker] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    // Domain vocabulary — every offset describes the SkillController /
    // talent-picker state. See header for cross-references.
    var TARGET_RVA            = 0x39c300;   // SkillController_roll_proposed_skills
    var TLS_SEED_OFFSET       = 0xff3c;     // PCG seed slot in TLS data
    var PICKER_LEA_IMM_RVA    = 0x39c4cd;   // LEA ECX,[RBX+0x2] imm — non-zero slot picker count
    var PICKER_ADD_IMM_RVA    = 0x39c4e4;   // ADD EBX, 0x4 imm — slot-0 picker count
    var SC_PERSISTENT_OFF     = 0x1d48;     // SkillController -> persistent block ptr
    var SC_SLOT_TIERS_OFF     = 0x18;       // within persistent: 10×u32 slot tiers
    var SC_SLOT_RECORDS_OFF   = 0xff0;      // 10 × 0x20 slot record array (held-talent ptr at +0x00)
    var SC_SLOT_CLASS_OFF     = 0xfe0;      // u32 class index per slot
    var SC_POOL_OFF           = 0xf98;      // pool entries: stride 0x10 (data ptr +0x00, count u32 +0x08)

    // ThreadBasicInformation — used by getCurrentTeb (NtQueryInformationThread).
    var TBI_CLASS_TBI         = 0;
    var TBI_SIZE              = 0x30;
    var TBI_TEB_OFFSET        = 0x08;

    if (!RW.TalentPicker) RW.TalentPicker = {};
    var TalentPicker = RW.TalentPicker;

    TalentPicker.entries          = TalentPicker.entries || 0;
    TalentPicker._forceEnabled    = false;
    TalentPicker._forceSeed       = 0;
    TalentPicker._nullPrevProposal = false;
    TalentPicker._clearHeldOnce   = false;
    TalentPicker._clearHeldIndex  = -1;
    TalentPicker._dumpSlotsOnce   = false;
    TalentPicker._dumpPoolOnce    = false;
    TalentPicker._hook            = TalentPicker._hook || null;
    TalentPicker._pickerOriginal  = TalentPicker._pickerOriginal || null;

    // ----- TLS access helpers (file-scope; used by hook only) -----
    var _NtQueryInformationThread = null;
    var _tbiBuffer = null;
    function getCurrentTeb() {
        if (_NtQueryInformationThread === null) {
            var ntdll = Process.findModuleByName('ntdll.dll')
                     || Process.findModuleByName('NTDLL.DLL');
            if (ntdll === null) throw new Error('ntdll.dll module not found');
            var p = ntdll.findExportByName('NtQueryInformationThread');
            if (p === null) throw new Error('NtQueryInformationThread export not found');
            _NtQueryInformationThread = new NativeFunction(p, 'uint32',
                ['pointer', 'uint32', 'pointer', 'uint32', 'pointer'], 'win64');
            _tbiBuffer = Memory.alloc(TBI_SIZE);
        }
        // Pseudo-handle for current thread = -2 (0xfffffffffffffffe).
        var status = _NtQueryInformationThread(
            ptr('0xfffffffffffffffe'),
            TBI_CLASS_TBI,
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
        var teb = getCurrentTeb();
        var tlsArray = teb.add(0x58).readPointer();
        var tlsData = tlsArray.readPointer();
        return tlsData.add(TLS_SEED_OFFSET);
    }

    // ----- Hook: detach prior + arm fresh on every reload -----
    if (TalentPicker._hook) {
        try { TalentPicker._hook.detach(); } catch (e) {}
        TalentPicker._hook = null;
    }
    TalentPicker._hook = Interceptor.attach(imageBase.add(TARGET_RVA), {
        onEnter: function (args) {
            TalentPicker.entries++;
            var teb = '?', tlsArr = '?', tlsData = '?', seedAddr = null, oldSeed = '?';
            try {
                teb = getCurrentTeb();
                tlsArr = teb.add(0x58).readPointer();
                tlsData = tlsArr.readPointer();
                seedAddr = tlsData.add(TLS_SEED_OFFSET);
                oldSeed = '0x' + seedAddr.readU32().toString(16).padStart(8, '0');
            } catch (e) {
                console.log('[TalentPicker] [#' + TalentPicker.entries + '] entry FAIL ' + e.message +
                            ' teb=' + teb + ' tlsArr=' + tlsArr + ' tlsData=' + tlsData);
                return;
            }

            // Diagnostic dump: read the SkillController's persistent slot.tier
            // array. param_1 (the SkillController) is in RCX (Win64 ABI).
            var slotTiersHex = '?';
            try {
                var skillCtrl = this.context.rcx;
                var persistent = skillCtrl.add(SC_PERSISTENT_OFF).readPointer();
                var tiersAddr = persistent.add(SC_SLOT_TIERS_OFF);
                var buf = tiersAddr.readByteArray(40);
                slotTiersHex = Array.from(new Uint8Array(buf))
                    .map(function (b) { return b.toString(16).padStart(2, '0'); })
                    .join('');
            } catch (e) { slotTiersHex = 'ERR:' + e.message; }

            // ---- one-shot: dump 10 slot records ----
            if (TalentPicker._dumpSlotsOnce) {
                TalentPicker._dumpSlotsOnce = false;
                try {
                    var sc = this.context.rcx;
                    for (var i = 0; i < 10; i++) {
                        var slotAddr = sc.add(SC_SLOT_RECORDS_OFF + i * 0x20);
                        var bytes = slotAddr.readByteArray(0x20);
                        var hex = Array.from(new Uint8Array(bytes))
                            .map(function (b) { return b.toString(16).padStart(2, '0'); })
                            .join('');
                        console.log('[TalentPicker] [#' + TalentPicker.entries + '] slot[' + i + '] @ ' +
                                    slotAddr + ' = ' + hex);
                    }
                } catch (e) {
                    console.log('[TalentPicker] [#' + TalentPicker.entries + '] slot dump ERR: ' + e.message);
                }
            }

            // ---- one-shot: dump unpruned talent pool ----
            if (TalentPicker._dumpPoolOnce) {
                TalentPicker._dumpPoolOnce = false;
                try {
                    var sc = this.context.rcx;
                    var slotIdx = -1;
                    for (var i = 0; i < 10; i++) {
                        if (sc.add(SC_SLOT_RECORDS_OFF + i * 0x20).readPointer().isNull()) {
                            slotIdx = i;
                            break;
                        }
                    }
                    if (slotIdx < 0) {
                        console.log('[TalentPicker] [#' + TalentPicker.entries + '] pool: no empty slot');
                    } else {
                        var classIdx = sc.add(SC_SLOT_CLASS_OFF + slotIdx * 0x20).readU32();
                        var poolEntry = sc.add(SC_POOL_OFF + classIdx * 0x10);
                        var poolData = poolEntry.readPointer();
                        var poolCount = poolEntry.add(0x08).readU32();
                        console.log('[TalentPicker] [#' + TalentPicker.entries + '] pool: slot=' + slotIdx +
                                    ' class=' + classIdx + ' count=' + poolCount + ' data=' + poolData);
                        var dumpN = Math.min(poolCount, 64);
                        for (var pi = 0; pi < dumpN; pi++) {
                            var entryPtr = poolData.add(pi * 8).readPointer();
                            var preview = '', derefPreview = '';
                            try {
                                var ebytes = entryPtr.readByteArray(0x20);
                                preview = Array.from(new Uint8Array(ebytes))
                                    .map(function (b) { return b.toString(16).padStart(2, '0'); })
                                    .join('');
                            } catch (e) { preview = 'ERR:' + e.message; }
                            try {
                                var innerPtr = entryPtr.add(0x10).readPointer();
                                var ibytes = innerPtr.readByteArray(0x100);
                                derefPreview = Array.from(new Uint8Array(ibytes))
                                    .map(function (b) { return b.toString(16).padStart(2, '0'); })
                                    .join('');
                            } catch (e) { derefPreview = 'ERR:' + e.message; }
                            console.log('[TalentPicker] [#' + TalentPicker.entries + '] pool[' + pi + '] @ ' +
                                        entryPtr + ' = ' + preview);
                            console.log('[TalentPicker] [#' + TalentPicker.entries + '] pool[' + pi + '] inner = ' +
                                        derefPreview);
                        }
                    }
                } catch (e) {
                    console.log('[TalentPicker] [#' + TalentPicker.entries + '] pool dump ERR: ' + e.message);
                }
            }

            // ---- one-shot: zero held-talent pointer(s) at param_1+0xff0 ----
            this.savedHeld = null;
            if (TalentPicker._clearHeldOnce) {
                TalentPicker._clearHeldOnce = false;
                var targetIdx = TalentPicker._clearHeldIndex;
                TalentPicker._clearHeldIndex = -1;
                try {
                    var sc = this.context.rcx;
                    var saved = [];
                    var indices = (targetIdx === -1)
                        ? [0,1,2,3,4,5,6,7,8,9] : [targetIdx];
                    for (var ii = 0; ii < indices.length; ii++) {
                        var addr = sc.add(SC_SLOT_RECORDS_OFF + indices[ii] * 0x20);
                        saved.push({ addr: addr, value: addr.readPointer() });
                        addr.writePointer(ptr(0));
                    }
                    this.savedHeld = saved;
                    var which = (targetIdx === -1) ? 'all 10' : 'slot ' + targetIdx;
                    console.log('[TalentPicker] [#' + TalentPicker.entries + '] CLEAR-HELD: zeroed ' +
                                which + ' held-talent pointer(s)');
                } catch (e) {
                    console.log('[TalentPicker] [#' + TalentPicker.entries + '] CLEAR-HELD failed: ' + e.message);
                }
            }

            // ---- seed force / param_3 null on entry ----
            if (TalentPicker._forceEnabled) {
                var writeStatus = 'OK';
                try { seedAddr.writeU32(TalentPicker._forceSeed >>> 0); }
                catch (e) { writeStatus = 'ERR ' + e.message; }
                var nulledPrev = '';
                if (TalentPicker._nullPrevProposal) {
                    var oldR8 = this.context.r8;
                    this.context.r8 = ptr(0);
                    nulledPrev = ' nulledPrev(was=' + oldR8 + ')';
                }
                console.log('[TalentPicker] [#' + TalentPicker.entries + '] FORCE tid=' + this.threadId +
                            ' tlsData=' + tlsData + ' addr=' + seedAddr +
                            ' was=' + oldSeed +
                            ' wrote=0x' + (TalentPicker._forceSeed >>> 0).toString(16).padStart(8, '0') +
                            ' write=' + writeStatus + nulledPrev +
                            ' slotTiers=' + slotTiersHex);
            } else {
                console.log('[TalentPicker] [#' + TalentPicker.entries + '] entry tid=' + this.threadId +
                            ' tlsData=' + tlsData + ' addr=' + seedAddr +
                            ' seed=' + oldSeed +
                            ' slotTiers=' + slotTiersHex);
            }
        },
        onLeave: function (retval) {
            // Restore held-talent pointers if we cleared them on entry.
            if (this.savedHeld) {
                try {
                    for (var ri = 0; ri < this.savedHeld.length; ri++) {
                        this.savedHeld[ri].addr.writePointer(this.savedHeld[ri].value);
                    }
                    console.log('[TalentPicker] [#' + TalentPicker.entries +
                                '] CLEAR-HELD: restored held-talent pointers');
                } catch (e) {
                    console.log('[TalentPicker] [#' + TalentPicker.entries +
                                '] CLEAR-HELD restore failed: ' + e.message);
                }
            }
        }
    });

    /*
     * ----------------------------------------------------------------
     * TalentPicker.force(seed: number): void
     *
     * Force every subsequent picker entry to use `seed` as its TLS RNG
     * input. Result: deterministic, repeatable talent picks across
     * reloads of the same save.
     *
     * Usage:
     *   TalentPicker.force(0xDEADBEEF)
     *
     * Result:
     *   On every picker entry, TLS+0xff3c is overwritten with `seed`
     *   BEFORE the picker reads it. Each draw therefore starts from the
     *   same seed. Rerolls within a level-up still mutate the seed
     *   internally, so reroll picks differ; for reroll-stable
     *   determinism use forceFresh() instead.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sets _forceEnabled=true, _forceSeed=seed. The hook on
     *   SkillController_roll_proposed_skills (RVA 0x39c300) calls
     *   getSeedAddr() to walk TEB+0x58 -> TLS array -> [0] -> +0xff3c
     *   and writes the seed there before the picker's inline PCG loop
     *   reads it.
     */
    TalentPicker.force = function (seed) {
        if (typeof seed !== 'number') {
            console.log('[TalentPicker.force] usage: TalentPicker.force(seed_uint32)');
            return;
        }
        TalentPicker._forceSeed = seed >>> 0;
        TalentPicker._forceEnabled = true;
        console.log('[TalentPicker] FORCE enabled seed=0x' +
                    TalentPicker._forceSeed.toString(16).padStart(8, '0'));
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.forceFresh(seed: number): void
     *
     * Same as force(seed) but ALSO nulls param_3 (R8) on entry so the
     * "exclude previous proposal" filter is bypassed. Result: every
     * reroll within one level-up sees the same pool, so the forced
     * seed produces identical talents across rerolls.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sets _nullPrevProposal=true in addition to force()'s seed
     *   write. The hook then writes ctx.r8 = 0 on entry — param_3 in
     *   the Win64 ABI — so the picker's exclude-previous-proposal
     *   filter has no input and falls through.
     */
    TalentPicker.forceFresh = function (seed) {
        if (typeof seed !== 'number') {
            console.log('[TalentPicker.forceFresh] usage: TalentPicker.forceFresh(seed_uint32)');
            return;
        }
        TalentPicker._forceSeed = seed >>> 0;
        TalentPicker._forceEnabled = true;
        TalentPicker._nullPrevProposal = true;
        console.log('[TalentPicker] FORCE enabled seed=0x' +
                    TalentPicker._forceSeed.toString(16).padStart(8, '0') +
                    ' (FRESH — param_3 nulled, identical rerolls expected)');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.unforce(): void
     *
     * Stop forcing. TLS seed is no longer overwritten on picker entry,
     * and param_3 nulling stops. Reroll exclusion behaves normally.
     * ----------------------------------------------------------------
     */
    TalentPicker.unforce = function () {
        TalentPicker._forceEnabled = false;
        TalentPicker._nullPrevProposal = false;
        console.log('[TalentPicker] FORCE disabled');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.count(n: number): void
     *
     * Byte-patch every per-level-up offer to `iVar18 + n` talents,
     * where iVar18 is the player's "Extra skill choice" gameplay
     * modifier. Persists until unpatchCount() or game relaunch.
     *
     * Usage:
     *   TalentPicker.count(5)   // every level-up offers iVar18 + 5
     *
     * Constraints:
     *   n must be 1..127 (signed-byte immediate). First call captures
     *   original bytes for restore.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Vanilla logic in SkillController_roll_proposed_skills:
     *     local_148 = iVar18 + 2;             // non-zero slot index
     *     if (slot_index == 0) local_148 = iVar18 + 4;
     *   We rewrite both immediate operands to `n`:
     *     image+0x39c4cd  (LEA ECX,[RBX+0x2]  imm)  vanilla 0x02
     *     image+0x39c4e4  (ADD EBX, 0x4       imm)  vanilla 0x04
     *   so every slot offers the same iVar18 + n count.
     */
    TalentPicker.count = function (n) {
        if (typeof n !== 'number' || !Number.isInteger(n) || n < 1 || n > 127) {
            console.log('[TalentPicker.count] usage: TalentPicker.count(n)  — integer 1..127');
            return;
        }
        var leaAddr = imageBase.add(PICKER_LEA_IMM_RVA);
        var addAddr = imageBase.add(PICKER_ADD_IMM_RVA);
        if (TalentPicker._pickerOriginal === null) {
            TalentPicker._pickerOriginal = {
                lea: leaAddr.readU8(),
                add: addAddr.readU8(),
            };
        }
        try {
            Memory.patchCode(leaAddr, 1, function (p) { p.writeU8(n & 0xff); });
            Memory.patchCode(addAddr, 1, function (p) { p.writeU8(n & 0xff); });
        } catch (e) {
            console.log('[TalentPicker.count] patch FAILED ' + e.message);
            return;
        }
        console.log('[TalentPicker.count] every slot now offers iVar18 + ' + n +
                    ' talents (was +' + TalentPicker._pickerOriginal.lea +
                    ' / +' + TalentPicker._pickerOriginal.add + ' for slot 0)');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.unpatchCount(): void
     *
     * Restore the vanilla picker-count bytes patched by count(n). No-op
     * if the patch was never applied this session.
     * ----------------------------------------------------------------
     */
    TalentPicker.unpatchCount = function () {
        if (TalentPicker._pickerOriginal === null) {
            console.log('[TalentPicker.unpatchCount] not patched — nothing to restore');
            return;
        }
        var leaAddr = imageBase.add(PICKER_LEA_IMM_RVA);
        var addAddr = imageBase.add(PICKER_ADD_IMM_RVA);
        var orig = TalentPicker._pickerOriginal;
        try {
            Memory.patchCode(leaAddr, 1, function (p) { p.writeU8(orig.lea); });
            Memory.patchCode(addAddr, 1, function (p) { p.writeU8(orig.add); });
        } catch (e) {
            console.log('[TalentPicker.unpatchCount] restore FAILED ' + e.message);
            return;
        }
        console.log('[TalentPicker.unpatchCount] restored vanilla (slot0=+' +
                    orig.add + ', others=+' + orig.lea + ')');
        TalentPicker._pickerOriginal = null;
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.dumpSlots(): void
     *
     * Arm a one-shot dump of the SkillController's 10 × 0x20 slot
     * record array on the next picker entry. Auto-disarms after firing.
     *
     * Result:
     *   On the next picker entry, logs one line per slot containing
     *   the 32-byte hex of the slot record. Used to diff committed vs.
     *   auto-filled vs. empty/selectable slot states.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sets _dumpSlotsOnce=true. The hook reads param_1+0xff0 stride
     *   0x20 on next entry and dumps 0x20 bytes per slot.
     */
    TalentPicker.dumpSlots = function () {
        TalentPicker._dumpSlotsOnce = true;
        console.log('[TalentPicker.dumpSlots] armed — next picker entry will dump 10 slot records');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.dumpPool(): void
     *
     * Arm a one-shot dump of the UNPRUNED talent pool (entry-relative,
     * before the picker copies it locally and prunes) on the next
     * picker entry. Auto-disarms after firing.
     *
     * Result:
     *   Logs slot index, class index, count, and a 32-byte preview +
     *   256-byte inner-pointer dump of each pool entry. Pool is the
     *   input to rw/dumps/picker_seed_solver.py for offline brute force.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads the first empty slot via param_1+0xff0 scan, then the
     *   class index at param_1+0xfe0+slot*0x20, then the pool entry at
     *   param_1+0xf98+class*0x10 (data ptr +0x00, count u32 +0x08).
     *   The picker copies this pool into a local buffer and then
     *   prunes (slot occupancy, modifier blocks, previous proposal);
     *   the dump captures the input to that pruning.
     */
    TalentPicker.dumpPool = function () {
        TalentPicker._dumpPoolOnce = true;
        console.log('[TalentPicker.dumpPool] armed — next picker entry will dump pool array');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.clearHeld(slotIdx?: number): void
     *
     * Arm a one-shot zero of held-talent pointer(s) on the next picker
     * entry. With no arg, zeros all 10 entries (whole array empty);
     * with `slotIdx` (0..9), zeros only that slot. Restored on
     * function exit. Auto-disarms after firing.
     *
     * Caveat:
     *   The picker fires for the FIRST empty slot in iteration order.
     *   Clearing all 10 always fires for slot 0. To target a specific
     *   slot you may need to leave earlier slots populated.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sets _clearHeldOnce=true and _clearHeldIndex=slotIdx (or -1
     *   for all). On next entry, the hook saves the held-talent
     *   pointers at param_1+0xff0+i*0x20 for the targeted indices,
     *   writes zero, and restores in onLeave.
     */
    TalentPicker.clearHeld = function (slotIdx) {
        if (typeof slotIdx === 'number') {
            if (slotIdx < 0 || slotIdx > 9) {
                console.log('[TalentPicker.clearHeld] slotIdx must be 0..9, got ' + slotIdx);
                return;
            }
            TalentPicker._clearHeldIndex = slotIdx;
        } else {
            TalentPicker._clearHeldIndex = -1;
        }
        TalentPicker._clearHeldOnce = true;
        var which = (TalentPicker._clearHeldIndex === -1) ? 'all 10 slots' : 'slot ' + TalentPicker._clearHeldIndex;
        console.log('[TalentPicker.clearHeld] armed — next picker entry will zero ' +
                    which + ' (one-shot, auto-restored on exit)');
    };

    /*
     * ----------------------------------------------------------------
     * TalentPicker.mark(label: string): void
     *
     * Write a labeled separator line to the log. Use to delimit phases
     * during a live test ("about to level up", "just rerolled") so you
     * can grep the log afterwards. Includes the running entry count.
     * ----------------------------------------------------------------
     */
    TalentPicker.mark = function (label) {
        console.log('[TalentPicker] --- mark: ' + label + ' entries=' + TalentPicker.entries + ' ---');
    };

    RW.registerMod("power:TalentPicker", version);
    console.log("[TalentPicker] " + version + " loaded. Try: TalentPicker.force(0xDEADBEEF)");
})();

// Top-level alias for REPL convenience
var TalentPicker = RW.TalentPicker;
