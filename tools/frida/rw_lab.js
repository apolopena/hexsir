// Ravenswatch — live-patch lab.
//
// Hub script for runtime patches and diagnostics against Ravenswatch.exe.
// Currently focused on the talent picker (SkillController_roll_proposed_skills
// @ image+0x39c300), but new patches against unrelated subsystems can be
// added below alongside the existing ones.
//
// Conventions:
//   - Each feature is a self-contained block (Interceptor.attach or byte
//     patch) with its own REPL commands. Extracting a feature into its own
//     file later = copy the block + the REPL command bindings, no
//     untangling.
//   - Byte patches save the original bytes on first apply so they can be
//     restored without relaunching.
//   - All commands log a labeled line so behaviour is visible in LOG_PATH.
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
// PICKER COUNT (byte-patch — persists until unpatchPickerCount() or relaunch)
// --------------------------------------------------------------------------
// pickerCount(n)
//   Patch the two immediate offsets that compute how many talents the
//   picker offers per level-up. Vanilla logic is:
//     local_148 = iVar18 + 2;             // non-zero slot index
//     if (slot_index == 0) local_148 = iVar18 + 4;
//   where iVar18 is the "Extra skill choice" gameplay-modifier stat.
//   pickerCount(n) rewrites BOTH +2 and +4 to +n, so every slot offers
//   `iVar18 + n` talents. n must be 1..127 (signed-byte immediate).
//   Effect is global until unpatchPickerCount() restores the original
//   bytes. Log line on apply records the prior value; first call
//   captures original bytes for restore.
//
//   Patch sites:
//     image+0x39c4cd  (LEA ECX,[RBX+0x2]  imm)  vanilla 0x02
//     image+0x39c4e4  (ADD EBX, 0x4       imm)  vanilla 0x04
//
// unpatchPickerCount()
//   Restore vanilla picker count. No-op if not patched.
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
//
// SAVE-WRITE PREP-CHAIN PROBE (chapter-end / Save-and-Quit)
// ---------------------------------------------------------
// probeForBossKillSave()
//   Arms a one-shot probe of session_finalize_and_save (image+0x28d6a0,
//   GameSessionGs::vtable[6]). On the NEXT call to that function (any
//   route, e.g., chapter-end Save and Quit, settings-side save), walks
//   the prep chain documented in rw/findings/save-subsystem.md
//   §"Prep-chain dig — narrowed to factory+serialize on GameModeDefault"
//   and verified by Ghidra decompile 2026-05-04 (plate comment on the
//   function records the verified offsets).
//
//   Verified chain (single, no candidate logic — decompile-confirmed):
//     session                       (RCX, GameSessionGs*)
//       *(session + 0x20)           = scene_mgr_outer
//         *(... + 0x18)             = scene_manager
//           *(... + 0x708)          = GameModeDefault*
//             *(... + 0x38)         = serializer-factory subsystem*
//               *factory            = factory vtable
//                 [+0xf8]           = create_serializer  ★ phase 2 hooks here
//                 (returns serializer)
//                   *serializer     = serializer vtable
//                     [+0x40]       = serialize(GameMode)  ★ phase 3 hooks here
//
//   Phase 1 (onEnter): walk the chain, log each step's pointer and the
//     factory's create_serializer RVA. Bail with a clear log line at
//     whichever step fails (chain may have shifted in a future patch).
//   Phase 2 (one-shot Interceptor on create_serializer.onLeave):
//     capture returned serializer, deref vtable, read +0x40 = serialize.
//   Phase 3 (one-shot Interceptor on serialize.onEnter): log args and
//     8-frame backtrace to confirm the call site, then auto-detach.
//
//   Also logs session+0xa5 (saves-enabled gate). If 0, the engine skips
//   the prep block — phase 2/3 won't fire, but phase 1 still captures
//   the structural offsets.
//
//   Anti-debug safe: pure Frida hooks. NOT subject to the boss-spawn /
//   boss-kill STATUS_BREAKPOINT tripwire that terminates WinDbg sessions
//   (rw/findings/save-subsystem.md §"Empirical: WinDbg anti-debug
//   behavior"). The session_finalize_and_save hook is permanent but
//   inert when unarmed.
//
//   IMPORTANT (2026-05-04 finding): the captured RVAs from this probe
//   (factory.vtable[0xf8] = 0xc6ea0, GameModeDefault.vtable[0x40] = 0x31bc40)
//   are NOT a save-buffer serializer. The "prep block" actually performs
//   chapter-snapshot bookkeeping. See plate comment on session_finalize_
//   and_save and rw/findings/frida-pipeline-hardware-breakpoint.md
//   §"MAJOR CORRECTION".
//
// SAVE-BUFFER STATE DIAGNOSTIC (incremental-vs-single-serialize hypothesis test)
// -----------------------------------------------------------------------------
// Goal: determine whether the save buffer at data_source+0x1948 is populated
// (a) incrementally during gameplay (many small Write calls per state change),
// or (b) all at once during Save-and-Quit by a single serialize function.
// Outcome decides whether mid-run Frida saves are achievable.
//
// findSaveBuffer()
//   One-shot heap scan to locate the live oCDtRootGs instance and cache it.
//   Modeled on tools/frida/save_now.js (empirically validated). Scan takes
//   ~10-80s. Call once after a profile/run is loaded. Cached pointer is
//   reused by logSaveBuffer() and the probe. Caveat: if you fully reload
//   the profile (return to main menu and back into a run), the heap address
//   may change — call again.
//
// logSaveBuffer(label)
//   Read the cached data_source's embedded oCMemoryBinaryStream and log a
//   single line:
//     [T+...s] [BUFFER/<label>] ds=0x... bufPtr=0x... size=N capacity=N
//   Where:
//     bufPtr   = qword at data_source+0x1958 (the buffer pointer)
//     size     = u32  at data_source+0x1960 (current data length, what
//                save_atomic_orchestrator writes to disk)
//     capacity = u32  at data_source+0x1964 (allocated buffer capacity)
//
//   Field offsets verified via Ghidra decompile of
//   oCMemoryBinaryStream_grow_buffer (image+0x24e700) which shows the
//   memstream layout: *param_1 = buffer ptr, param_1[1] = size,
//   (longlong)param_1+0xc = capacity. The memstream is embedded at
//   job+0x30 = data_source+0x1958.
//
// USAGE PROTOCOL (the 20-minute experiment)
// -----------------------------------------
// One chapter-end run; ~20 min of focused play. Goal: get a buffer-size
// time series from chapter start through Save-and-Quit.
//
//   1. Launch game, attach Frida with this script. Reach the run-start
//      menu (any character). Start a chapter-1 run.
//   2. As soon as you have control: findSaveBuffer()
//      Wait for the cache hit (one log line). If multiple instances
//      reported, inspect manually before continuing.
//   3. logSaveBuffer("chapter1-start")
//   4. Play. After clearing room 1: logSaveBuffer("chapter1-room1-clear")
//   5. After room 2-3: logSaveBuffer("chapter1-mid")
//   6. Right before entering boss room: logSaveBuffer("chapter1-pre-boss")
//   7. After killing boss, BEFORE clicking save dialog:
//        logSaveBuffer("chapter1-post-boss")
//   8. Arm the probe: probeForBossKillSave()
//   9. Click Save and Quit. Probe fires; auto-logs buffer state at
//      session_finalize_and_save entry as [PROBE/sfas/buffer].
//   10. Quit Frida. Read frida_seed_diag.log.
//
// INTERPRETATION
// --------------
// Compare the size values across the [BUFFER/...] log lines:
//   - Monotonic growth across "start" → "room1" → "mid" → "pre-boss"
//     → "post-boss" → [PROBE/sfas/buffer]: INCREMENTAL model confirmed.
//     The engine writes records as gameplay events occur. Mid-run Frida
//     saves are fundamentally impossible without replicating the per-event
//     Write sites.
//   - Size near-zero or constant until Save-and-Quit, then large at probe:
//     SINGLE-SERIALIZER model. There IS a single big serialize call we
//     missed; it runs inside session_finalize_and_save (or downstream of
//     it) and is the missing prep we want to hook.
//   - Mostly flat with a big jump at "post-boss": HYBRID — most state is
//     incremental but boss-kill triggers a final serialize. Hooking the
//     post-boss serializer would be sufficient for chapter-end Frida
//     saves.
//
// BOSS-TIMER TRIGGER (force chapter-end boss arrival on demand)
// -------------------------------------------------------------
// Goal: collapse the ~20-min chapter-end iteration loop. The engine only
// emits a new save on chapter-boss kill (CLAUDE.md "Saves are only generated
// at chapter-boss kills"). The boss arrival is gated by a single float
// comparison in BossTimer_update at image+0x1e9d50:
//
//     if (this->elapsed (+0x12c) >= this->boss_time (+0x144)) {
//         this->is_boss_awaken = 1;
//         fire_named_event(scene, 0x17d8d901);   // "Boss time start"
//     }
//
// The named event's existing subscribers handle the actual portal/arena
// spawn — we don't reverse-engineer them. Per
// rw/findings/chapter-boss-portal-trigger.md.
//
// forceBossSpawn()
//   Write *(float*)(timer + 0x12c) = *(float*)(timer + 0x144). On the next
//   frame the engine's own Update logic fires 0x17d8d901 and the boss
//   content spawns identically to natural progression. Requires the
//   BossTimer instance to be captured first (any in-game frame ticks the
//   Update hook and captures args[0]).
//
// bossTimerStatus()
//   Dump the runtime state: elapsed, boss_time, remaining seconds, cycle
//   count, day/night durations, all gating booleans. Use to verify the
//   harness sees a live timer before forcing.
//
// bossTimerSetElapsed(seconds)
//   Write any arbitrary elapsed value. Useful for testing intermediate
//   thresholds (cross the warning offset ~30s before boss_time, observe
//   the "Boss warning start" event fire, without triggering awakening).

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
let probeArmed = false;          // one-shot: dump save prep-chain on
                                 // NEXT call to session_finalize_and_save

const SESSION_FINALIZE_RVA = 0x28d6a0;

// BossTimer trigger. See header §"BOSS-TIMER TRIGGER" and
// rw/findings/chapter-boss-portal-trigger.md for the field map.
const BOSS_TIMER_UPDATE_RVA   = 0x1e9d50;
const BT_DAY_DURATION_OFF     = 0xac;
const BT_NIGHT_DURATION_OFF   = 0xb0;
const BT_ARRIVAL_ENABLED_OFF  = 0xb8;
const BT_WARN_OFF             = 0xbc;
const BT_OVERTIME_OFF         = 0xc0;
const BT_TIMER_ENABLED_OFF    = 0x129;
const BT_ELAPSED_OFF          = 0x12c;
const BT_SPEED_MULT_OFF       = 0x130;
const BT_PHASE_INDICATOR_OFF  = 0x134;
const BT_CYCLE_COUNT_OFF      = 0x138;
const BT_PHASE_REMAINING_OFF  = 0x13c;
const BT_BOSS_TIME_OFF        = 0x144;
const BT_IS_BOSS_AWAKEN_OFF   = 0x148;
const BT_IS_OVERTIME_OFF      = 0x149;
const BT_BOSS_DISABLED_OFF    = 0x14b;

// Save-buffer diagnostic. See header §"SAVE-BUFFER STATE DIAGNOSTIC".
// Field offsets within the live oCDtRootGs instance, validated via
// tools/frida/save_now.js (empirically) and Ghidra decompile of
// oCMemoryBinaryStream_grow_buffer (image+0x24e700) which shows the
// embedded memstream layout.
const DS_VTABLE0_RVA   = 0x1c6830;  // typedesc-getter — vtable[0] of every oCDtRootGs
const DS_BUF_PTR_OFF   = 0x1958;    // qword: data buffer pointer
const DS_BUF_SIZE_OFF  = 0x1960;    // u32:   current size (what gets written to disk)
const DS_BUF_CAP_OFF   = 0x1964;    // u32:   allocated capacity
const DS_JOB_PEND_OFF  = 0x19a4;    // u32:   pending sequence
const DS_JOB_DONE_OFF  = 0x19a8;    // u32:   completed sequence
const DS_JOB_RESULT_OFF = 0x19ac;   // u8:    last result code
const DS_SAVES_DISABLED_OFF = 0x1ef4; // u8:  saves-disabled silencer flag

// Heap-scan tuning (mirrors tools/frida/save_now.js).
const HEAP_SCAN_MIN_RANGE_SIZE = 0x4000;
const HEAP_SCAN_CHUNK = 16 * 1024 * 1024;
const HEAP_SCAN_OVERLAP = 0x4000;

let cachedDataSource = null;     // NativePointer to the live oCDtRootGs.
                                 // Set by findSaveBuffer() or auto-cached
                                 // on probe entry. Read by logSaveBuffer().

let capturedBossTimer = null;    // NativePointer to the live BossTimer
                                 // entity. Set on every BossTimer_update
                                 // entry; tracks the current chapter's
                                 // timer across chapter transitions.

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

    // Picker-count byte patch. Rewrites the two immediates that compute
    // how many talents the picker offers per level-up:
    //   image+0x39c4cd : LEA ECX,[RBX+0x2]  imm   (non-zero slot)
    //   image+0x39c4e4 : ADD EBX, 0x4       imm   (slot 0)
    // Both get rewritten to the same value so every slot offers iVar18+n.
    const PICKER_LEA_IMM_RVA = 0x39c4cd;
    const PICKER_ADD_IMM_RVA = 0x39c4e4;
    let pickerOriginal = null;  // { lea: u8, add: u8 } once first patched

    globalThis.pickerCount = function (n) {
        if (typeof n !== 'number' || !Number.isInteger(n) || n < 1 || n > 127) {
            console.log('[diag] usage: pickerCount(n) — integer 1..127');
            return;
        }
        const leaAddr = mod.base.add(PICKER_LEA_IMM_RVA);
        const addAddr = mod.base.add(PICKER_ADD_IMM_RVA);
        if (pickerOriginal === null) {
            pickerOriginal = {
                lea: leaAddr.readU8(),
                add: addAddr.readU8(),
            };
        }
        try {
            Memory.patchCode(leaAddr, 1, function (p) { p.writeU8(n & 0xff); });
            Memory.patchCode(addAddr, 1, function (p) { p.writeU8(n & 0xff); });
        } catch (e) {
            logLine(ts() + ' === PICKER-COUNT: patch FAILED ' + e.message + ' ===');
            return;
        }
        logLine(ts() + ' === PICKER-COUNT: every slot offers iVar18 + ' + n +
                ' talents (was +' + pickerOriginal.lea + ' / +' + pickerOriginal.add +
                ' for slot 0) ===');
    };

    globalThis.unpatchPickerCount = function () {
        if (pickerOriginal === null) {
            console.log('[diag] picker count not patched — nothing to restore');
            return;
        }
        const leaAddr = mod.base.add(PICKER_LEA_IMM_RVA);
        const addAddr = mod.base.add(PICKER_ADD_IMM_RVA);
        try {
            Memory.patchCode(leaAddr, 1, function (p) { p.writeU8(pickerOriginal.lea); });
            Memory.patchCode(addAddr, 1, function (p) { p.writeU8(pickerOriginal.add); });
        } catch (e) {
            logLine(ts() + ' === PICKER-COUNT: restore FAILED ' + e.message + ' ===');
            return;
        }
        logLine(ts() + ' === PICKER-COUNT: restored vanilla (slot0=+' +
                pickerOriginal.add + ', others=+' + pickerOriginal.lea + ') ===');
        pickerOriginal = null;
    };

    // ============================================================
    // SAVE-WRITE PREP-CHAIN PROBE
    // See header comment §"SAVE-WRITE PREP-CHAIN PROBE" for design.
    // ============================================================
    function _hex(v) { return '0x' + v.toString(16); }

    // Cheap "ptr in user-mode space" check. Doesn't guarantee mapped.
    function _validatePtr(p) {
        if (p === null || p.isNull()) return false;
        return p.compare(ptr('0x10000')) > 0
            && p.compare(ptr('0x7fffffffffff')) < 0;
    }

    // Vtable sanity: pointer lives inside the loaded image.
    function _vtableInImage(p) {
        if (!_validatePtr(p)) return false;
        const end = mod.base.add(mod.size);
        return p.compare(mod.base) >= 0 && p.compare(end) < 0;
    }

    globalThis.probeForBossKillSave = function () {
        probeArmed = true;
        logLine(ts() + ' === PROBE-BOSS-KILL-SAVE armed: next call to ' +
                'session_finalize_and_save (image+' + _hex(SESSION_FINALIZE_RVA) +
                ') will dump the prep chain ===');
    };

    Interceptor.attach(mod.base.add(SESSION_FINALIZE_RVA), {
        onEnter(args) {
            if (!probeArmed) return;
            probeArmed = false;
            const tag = ' [PROBE/sfas]';
            try {
                const session = this.context.rcx;
                logLine(ts() + tag + ' enter session=' + session);

                // Auto-cache data_source via the linked-list walk. This is
                // cheap and gives us a fresh pointer at save time without
                // requiring the user to run findSaveBuffer() first.
                try {
                    const ds = _walkAndCacheDataSource(session);
                    if (ds !== null) {
                        cachedDataSource = ds;
                        const state = _readBufferState(ds);
                        if (state !== null) {
                            logLine(ts() + tag + '/buffer ds=' + ds + ' ' + _formatBufferState(state));
                        } else {
                            logLine(ts() + tag + '/buffer ds=' + ds + ' state-read FAIL');
                        }
                    } else {
                        logLine(ts() + tag + '/buffer no oCDtRootGs found in data_source list');
                    }
                } catch (e) {
                    logLine(ts() + tag + '/buffer walk ERR ' + e.message);
                }

                let gate = '?';
                try { gate = '0x' + session.add(0xa5).readU8().toString(16); }
                catch (e) { gate = 'ERR:' + e.message; }
                logLine(ts() + tag + ' session+0xa5 (saves-enabled gate) = ' + gate);

                // Verified chain (Ghidra decompile of session_finalize_and_save,
                // 2026-05-04): scene_manager = *(*(session+0x20)+0x18). The
                // earlier "two candidates" logic was speculative; the decompile
                // pins it to this single path.
                let outer = null, sceneManager = null, gameMode = null,
                    factory = null, factoryVT = null, createFn = null;
                try { outer = session.add(0x20).readPointer(); } catch (e) {
                    logLine(ts() + tag + ' *(session+0x20) read fail ' + e.message);
                    return;
                }
                logLine(ts() + tag + ' *(session+0x20)        = ' + outer);

                try { sceneManager = outer.add(0x18).readPointer(); } catch (e) {
                    logLine(ts() + tag + ' scene_manager (+0x18) read fail ' + e.message);
                    return;
                }
                logLine(ts() + tag + ' scene_manager          = ' + sceneManager);

                try { gameMode = sceneManager.add(0x708).readPointer(); } catch (e) {
                    logLine(ts() + tag + ' GameModeDefault (+0x708) read fail ' + e.message);
                    return;
                }
                let gmVT = null;
                try { gmVT = gameMode.readPointer(); } catch (e) {}
                const gmVtInImage = _vtableInImage(gmVT);
                logLine(ts() + tag + ' GameModeDefault        = ' + gameMode +
                        ' vt=' + gmVT +
                        (gmVtInImage ? ' (RVA +' + _hex(gmVT.sub(mod.base).toUInt32()) + ')'
                                     : ' (NOT in image — chain may have shifted)'));

                try { factory = gameMode.add(0x38).readPointer(); } catch (e) {
                    logLine(ts() + tag + ' factory (+0x38) read fail ' + e.message);
                    return;
                }
                if (!_validatePtr(factory)) {
                    logLine(ts() + tag + ' factory invalid: ' + factory + ' — aborting phase 2');
                    return;
                }

                try { factoryVT = factory.readPointer(); } catch (e) {
                    logLine(ts() + tag + ' factory vtable read fail ' + e.message);
                    return;
                }
                try { createFn = factoryVT.add(0xf8).readPointer(); } catch (e) {
                    logLine(ts() + tag + ' factoryVT+0xf8 read fail ' + e.message);
                    return;
                }
                const factoryVtRVA = _vtableInImage(factoryVT)
                    ? _hex(factoryVT.sub(mod.base).toUInt32()) : 'NOT-IN-IMAGE';
                const createRVA = _vtableInImage(createFn)
                    ? _hex(createFn.sub(mod.base).toUInt32()) : 'NOT-IN-IMAGE';
                logLine(ts() + tag + ' factory_vtable=' + factoryVT + ' (RVA +' + factoryVtRVA + ')' +
                        ' create_serializer=' + createFn + ' (RVA +' + createRVA + ')');

                if (!_vtableInImage(createFn)) {
                    logLine(ts() + tag + ' create_serializer not in image; aborting phase 2');
                    return;
                }

                const phase2 = Interceptor.attach(createFn, {
                    onLeave(retval) {
                        try {
                            const serializer = retval;
                            logLine(ts() + tag + ' phase2 create_serializer returned ' + serializer);
                            if (!_validatePtr(serializer)) {
                                logLine(ts() + tag + ' phase2 retval invalid; aborting phase 3');
                                return;
                            }
                            const serialVT = serializer.readPointer();
                            if (!_vtableInImage(serialVT)) {
                                logLine(ts() + tag + ' phase2 serializer vtable NOT in image: ' + serialVT);
                                return;
                            }
                            const serializeFn = serialVT.add(0x40).readPointer();
                            const serialVtRVA = _hex(serialVT.sub(mod.base).toUInt32());
                            const serializeRVA = _vtableInImage(serializeFn)
                                ? _hex(serializeFn.sub(mod.base).toUInt32()) : 'NOT-IN-IMAGE';
                            logLine(ts() + tag + ' phase2 serializer_vtable=' + serialVT +
                                    ' (RVA +' + serialVtRVA + ')' +
                                    ' serialize=' + serializeFn + ' (RVA +' + serializeRVA + ')');

                            if (!_vtableInImage(serializeFn)) return;

                            const phase3 = Interceptor.attach(serializeFn, {
                                onEnter(args3) {
                                    try {
                                        logLine(ts() + tag + ' phase3 serialize enter rcx=' +
                                                this.context.rcx + ' rdx=' + this.context.rdx);
                                        const bt = Thread.backtrace(this.context, Backtracer.ACCURATE)
                                            .slice(0, 8)
                                            .map(a => {
                                                const inImg = a.compare(mod.base) >= 0
                                                    && a.compare(mod.base.add(mod.size)) < 0;
                                                return a + (inImg
                                                    ? ' (img+' + _hex(a.sub(mod.base).toUInt32()) + ')'
                                                    : '');
                                            })
                                            .join(' | ');
                                        logLine(ts() + tag + ' phase3 backtrace: ' + bt);
                                    } catch (e) {
                                        logLine(ts() + tag + ' phase3 onEnter ERR ' + e.message);
                                    }
                                    phase3.detach();
                                }
                            });
                        } catch (e) {
                            logLine(ts() + tag + ' phase2 onLeave ERR ' + e.message);
                        }
                        phase2.detach();
                    }
                });
            } catch (e) {
                logLine(ts() + tag + ' onEnter ERR ' + e.message);
            }
        }
    });

    // ============================================================
    // SAVE-BUFFER STATE DIAGNOSTIC
    // See header §"SAVE-BUFFER STATE DIAGNOSTIC" for design and
    // §"USAGE PROTOCOL" for the 20-minute experiment recipe.
    // ============================================================

    // Convert a NativePointer to a "byte byte byte ..." pattern for Memory.scanSync.
    function _ptrToBytes(p) {
        const big = BigInt(p.toString());
        const out = [];
        for (let i = 0; i < 8; i++) {
            out.push(Number((big >> BigInt(i * 8)) & 0xffn).toString(16).padStart(2, '0'));
        }
        return out.join(' ');
    }

    // Read buffer state from an oCDtRootGs pointer. Returns null on read fail.
    function _readBufferState(ds) {
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
        } catch (e) {
            return null;
        }
    }

    function _formatBufferState(s) {
        return 'bufPtr=' + s.bufPtr +
               ' size=' + s.size +
               ' capacity=' + s.capacity +
               ' pend=' + s.pend + ' done=' + s.done +
               ' result=0x' + s.result.toString(16) +
               ' flag=' + s.flag;
    }

    // Heap-scan for the live oCDtRootGs. Mirrors tools/frida/save_now.js.
    // Phase 1: find every qword in image with value == image+0x1c6830 (the
    //   typedesc-getter that occupies vtable[0] of every oCDtRootGs class).
    //   Each match is a vtable address.
    // Phase 2: scan rw- ranges for any qword equal to one of those vtable
    //   addresses. Each match is a candidate instance. Validate via
    //   structural fields (saves-disabled flag, sequence invariants).
    globalThis.findSaveBuffer = function () {
        const tag = ' [findSaveBuffer]';
        const expectedFn = mod.base.add(DS_VTABLE0_RVA);
        logLine(ts() + tag + ' scanning image for vtable[0]=' + expectedFn);

        let vtblHits;
        try {
            vtblHits = Memory.scanSync(mod.base, mod.size, _ptrToBytes(expectedFn));
        } catch (e) {
            logLine(ts() + tag + ' image scan ERR ' + e.message);
            return null;
        }
        const vtables = vtblHits.filter(h => {
            const big = BigInt(h.address.toString());
            return Number(big & 7n) === 0;
        }).map(h => h.address);
        logLine(ts() + tag + ' vtable candidates: ' + vtables.length);
        if (vtables.length === 0) {
            logLine(ts() + tag + ' no vtables; engine state may be uninitialized');
            return null;
        }

        const ranges = Process.enumerateRanges({ protection: 'rw-', coalesce: false });
        logLine(ts() + tag + ' scanning ' + ranges.length + ' rw- ranges');
        const t0 = Date.now();
        const candidates = [];

        for (const r of ranges) {
            if (r.size < HEAP_SCAN_MIN_RANGE_SIZE) continue;
            let off = 0;
            while (off < r.size) {
                const sz = Math.min(HEAP_SCAN_CHUNK, r.size - off);
                const cbase = r.base.add(off);
                let bytes;
                try { bytes = cbase.readByteArray(sz); }
                catch (_) { off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP; continue; }
                if (!bytes || bytes.byteLength === 0) {
                    off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP; continue;
                }
                const view = new DataView(bytes);
                const limit = bytes.byteLength - 8;
                for (let p = 0; p < limit; p += 8) {
                    const lo = view.getUint32(p, true);
                    const hi = view.getUint32(p + 4, true);
                    for (const vt of vtables) {
                        const vbig = BigInt(vt.toString());
                        const vlo = Number(vbig & 0xffffffffn);
                        const vhi = Number(vbig >> 32n);
                        if (lo !== vlo || hi !== vhi) continue;
                        const addr = cbase.add(p);
                        const state = _readBufferState(addr);
                        if (state === null) break;  // unreadable past +0x1ef4 — not an oCDtRootGs
                        // Sanity: flag is 0/1, done<=pend, result is small or sentinel.
                        if (state.flag <= 1 && state.done <= state.pend &&
                            (state.result < 16 || state.result === 0xff)) {
                            candidates.push({ addr, vtbl: vt, state });
                        }
                        break;
                    }
                }
                if (sz === r.size - off) break;
                off += HEAP_SCAN_CHUNK - HEAP_SCAN_OVERLAP;
            }
        }
        const dt = Date.now() - t0;
        logLine(ts() + tag + ' scan complete in ' + dt + 'ms; ' +
                candidates.length + ' candidate(s)');
        for (const c of candidates) {
            logLine(ts() + tag + '   ' + c.addr + '  ' + _formatBufferState(c.state));
        }

        if (candidates.length === 0) {
            logLine(ts() + tag + ' no oCDtRootGs found — is a profile/run loaded?');
            return null;
        }
        if (candidates.length > 1) {
            logLine(ts() + tag + ' MULTIPLE candidates — refusing to auto-pick. ' +
                    'Inspect log and call cachedDataSource manually if needed.');
            return null;
        }
        cachedDataSource = candidates[0].addr;
        logLine(ts() + tag + ' cached data_source = ' + cachedDataSource);
        return cachedDataSource;
    };

    // Read the cached data_source's buffer state and log one labeled line.
    // Call at gameplay checkpoints: logSaveBuffer("chapter1-room1-clear"), etc.
    globalThis.logSaveBuffer = function (label) {
        if (!label || typeof label !== 'string') {
            logLine(ts() + ' [logSaveBuffer] usage: logSaveBuffer("label-string")');
            return;
        }
        if (cachedDataSource === null) {
            logLine(ts() + ' [BUFFER/' + label + '] no cached data_source — call findSaveBuffer() first');
            return;
        }
        const state = _readBufferState(cachedDataSource);
        if (state === null) {
            logLine(ts() + ' [BUFFER/' + label + '] cache=' + cachedDataSource +
                    ' — read FAIL (heap may have changed; re-run findSaveBuffer)');
            return;
        }
        logLine(ts() + ' [BUFFER/' + label + '] ds=' + cachedDataSource +
                ' ' + _formatBufferState(state));
    };

    // ============================================================
    // PROBE EXTENSION: walk the data_source list at probe entry,
    // auto-cache, and log buffer state. This gives one buffer
    // sample per Save-and-Quit fire automatically.
    // ============================================================
    function _walkAndCacheDataSource(session) {
        // session+0x8 is the head of the data_source linked list (each node's
        // +0x08 is the next pointer per session_finalize_and_save's loop).
        // We avoid calling vtable[0]() — instead match the function-pointer
        // literal at vtable[0] against image+0x1c6830 (the typedesc-getter).
        // Per save_now.js / save-subsystem.md, that pattern can match both
        // oCDtRootGs and a sibling class; discriminate via structural fields
        // (saves-disabled flag in {0,1}, done <= pend, result valid).
        const expectedFn = mod.base.add(DS_VTABLE0_RVA);
        try {
            let node = session.add(0x08).readPointer();
            for (let i = 0; i < 32 && _validatePtr(node); i++) {
                let vt = null;
                try { vt = node.readPointer(); } catch (_) {}
                if (vt && _vtableInImage(vt)) {
                    let slot0 = null;
                    try { slot0 = vt.readPointer(); } catch (_) {}
                    if (slot0 && slot0.equals(expectedFn)) {
                        // Structural validation — same discriminator as save_now.js.
                        const state = _readBufferState(node);
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

    // ============================================================
    // BOSS-TIMER TRIGGER
    // See header §"BOSS-TIMER TRIGGER" for design and
    // rw/findings/chapter-boss-portal-trigger.md for the field map.
    // ============================================================
    Interceptor.attach(mod.base.add(BOSS_TIMER_UPDATE_RVA), {
        onEnter(args) {
            // Capture (or refresh) the instance pointer on every entry.
            // Cheap assignment; tracks the live BossTimer across chapter
            // transitions in case the entity is recreated per-chapter.
            capturedBossTimer = args[0];
        }
    });
    logLine('[diag] hooked BossTimer_update @ ' +
            mod.base.add(BOSS_TIMER_UPDATE_RVA) +
            ' (rva 0x' + BOSS_TIMER_UPDATE_RVA.toString(16) + ')');

    // forceBossSpawn() — write elapsed = boss_time. On the next frame the
    // engine's own Update logic fires named event 0x17d8d901 ("Boss time
    // start" / "Triggered when boss awakens") and the subscribers spawn
    // boss content identically to natural progression.
    globalThis.forceBossSpawn = function () {
        if (capturedBossTimer === null) {
            console.log('[diag] BossTimer not captured yet — wait until in-game ' +
                        '(BossTimer_update must tick at least once)');
            return;
        }
        try {
            const t = capturedBossTimer;
            const bossTime = t.add(BT_BOSS_TIME_OFF).readFloat();
            const elapsedBefore = t.add(BT_ELAPSED_OFF).readFloat();
            const isAwaken = t.add(BT_IS_BOSS_AWAKEN_OFF).readU8();
            if (isAwaken !== 0) {
                logLine(ts() + ' === FORCE-BOSS-SPAWN: already awakened ' +
                        '(is_boss_awaken=' + isAwaken + '); no-op ===');
                return;
            }
            t.add(BT_ELAPSED_OFF).writeFloat(bossTime);
            logLine(ts() + ' === FORCE-BOSS-SPAWN: instance=' + t +
                    ' elapsed ' + elapsedBefore.toFixed(2) +
                    ' -> ' + bossTime.toFixed(2) +
                    ' (boss_time). Next frame fires 0x17d8d901. ===');
        } catch (e) {
            logLine(ts() + ' === FORCE-BOSS-SPAWN: write FAILED ' + e.message + ' ===');
        }
    };

    // bossTimerStatus() — read and log the BossTimer's runtime state.
    // Use to verify the harness sees a live timer before forcing.
    globalThis.bossTimerStatus = function () {
        if (capturedBossTimer === null) {
            console.log('[diag] BossTimer not captured yet — wait until in-game');
            return;
        }
        try {
            const t = capturedBossTimer;
            const elapsed     = t.add(BT_ELAPSED_OFF).readFloat();
            const bossTime    = t.add(BT_BOSS_TIME_OFF).readFloat();
            const warnOff     = t.add(BT_WARN_OFF).readFloat();
            const overtimeOff = t.add(BT_OVERTIME_OFF).readFloat();
            const dayDur      = t.add(BT_DAY_DURATION_OFF).readFloat();
            const nightDur    = t.add(BT_NIGHT_DURATION_OFF).readFloat();
            const speedMult   = t.add(BT_SPEED_MULT_OFF).readFloat();
            const phaseRem    = t.add(BT_PHASE_REMAINING_OFF).readFloat();
            const cycleCount  = t.add(BT_CYCLE_COUNT_OFF).readInt();
            const arrivalOn   = t.add(BT_ARRIVAL_ENABLED_OFF).readInt();
            const timerOn     = t.add(BT_TIMER_ENABLED_OFF).readU8();
            const isAwaken    = t.add(BT_IS_BOSS_AWAKEN_OFF).readU8();
            const isOvertime  = t.add(BT_IS_OVERTIME_OFF).readU8();
            const isDisabled  = t.add(BT_BOSS_DISABLED_OFF).readU8();
            const phase       = t.add(BT_PHASE_INDICATOR_OFF).readU8();
            const remaining   = bossTime - elapsed;
            logLine(ts() + ' [BOSS-TIMER] instance=' + t +
                    ' elapsed='      + elapsed.toFixed(2) +
                    ' boss_time='    + bossTime.toFixed(2) +
                    ' remaining='    + remaining.toFixed(2) + 's' +
                    ' speedMult='    + speedMult.toFixed(2) +
                    ' warnOff='      + warnOff.toFixed(2) +
                    ' overtimeOff='  + overtimeOff.toFixed(2));
            logLine(ts() + ' [BOSS-TIMER] phase=' + phase +
                    ' phaseRemaining=' + phaseRem.toFixed(2) +
                    ' cycleCount='     + cycleCount +
                    ' dayDur='         + dayDur.toFixed(2) +
                    ' nightDur='       + nightDur.toFixed(2) +
                    ' arrivalEnabled=' + arrivalOn +
                    ' timerEnabled='   + timerOn +
                    ' isAwaken='       + isAwaken +
                    ' isOvertime='     + isOvertime +
                    ' isDisabled='     + isDisabled);
        } catch (e) {
            logLine(ts() + ' [BOSS-TIMER] read FAIL ' + e.message);
        }
    };

    // bossTimerSetElapsed(seconds) — write any arbitrary elapsed value.
    // For testing intermediate thresholds (e.g., cross the warning offset
    // ~30s before boss_time to observe 0x17d8d900 fire without triggering
    // awakening). Capped check is upstream — caller's responsibility.
    globalThis.bossTimerSetElapsed = function (seconds) {
        if (typeof seconds !== 'number') {
            console.log('[diag] usage: bossTimerSetElapsed(seconds)');
            return;
        }
        if (capturedBossTimer === null) {
            console.log('[diag] BossTimer not captured yet — wait until in-game');
            return;
        }
        try {
            const t = capturedBossTimer;
            const before = t.add(BT_ELAPSED_OFF).readFloat();
            t.add(BT_ELAPSED_OFF).writeFloat(seconds);
            logLine(ts() + ' === BOSS-TIMER-SET-ELAPSED: ' +
                    before.toFixed(2) + ' -> ' + seconds.toFixed(2) + ' ===');
        } catch (e) {
            logLine(ts() + ' === BOSS-TIMER-SET-ELAPSED FAIL ' + e.message + ' ===');
        }
    };

    console.log('[diag] ready. REPL: force(seed) | forceFresh(seed) | unforce() | mark("label")');
    console.log('[diag]        dumpTalentSlotsNext() | dumpTalentPoolNext() | clearHeldTalentNext(idx?)');
    console.log('[diag]        pickerCount(n) | unpatchPickerCount()');
    console.log('[diag]        probeForBossKillSave()');
    console.log('[diag]        findSaveBuffer() | logSaveBuffer("label")');
    console.log('[diag]        forceBossSpawn() | bossTimerStatus() | bossTimerSetElapsed(s)');
}
