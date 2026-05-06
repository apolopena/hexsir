// ChapterBoss.js — force the current chapter's boss to arrive on demand.
//
// Mechanism: the engine gates boss arrival on a single float comparison in
// BossTimer_update at image+0x1e9d50:
//
//     if (this->elapsed (+0x12c) >= this->boss_time (+0x144)) {
//         this->is_boss_awaken = 1;
//         fire_named_event(scene, 0x17d8d901);   // "Boss time start"
//     }
//
// Writing elapsed past boss_time forces the comparison to fire on the next
// engine frame; the engine's existing event subscribers handle the arrival
// cinematic + arena spawn identically to natural progression.
//
// Naming note: the "BossTimer" class is actually
// oe::dt::DayNightCycleSceneContext (RTTI-confirmed). Behavior is accurate;
// the class-name is misleading. Field map lives in
// rw/findings/chapter-boss-portal-trigger.md.
//
// REPL surface (after loadPower("ChapterBoss")):
//   ChapterBoss.spawn(): void
//   ChapterBoss.delaySpawn(seconds: number): void
//   ChapterBoss.status(): void
//   ChapterBoss.timer: NativePointer | null

(function () {
    var version = "0.2.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[ChapterBoss] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    // BossTimer (oe::dt::DayNightCycleSceneContext) — domain vocabulary
    // for this file. Verified runtime; see
    // rw/findings/chapter-boss-portal-trigger.md for the field map.
    // Kept at file scope because every offset describes one entity (the
    // BossTimer field block) and any future ChapterBoss function added
    // here will likely need them.
    var BOSS_TIMER_UPDATE_RVA   = 0x1e9d50;
    var BT_DAY_DURATION_OFF     = 0xac;
    var BT_NIGHT_DURATION_OFF   = 0xb0;
    var BT_ARRIVAL_ENABLED_OFF  = 0xb8;
    var BT_WARN_OFF             = 0xbc;
    var BT_OVERTIME_OFF         = 0xc0;
    var BT_TIMER_ENABLED_OFF    = 0x129;
    var BT_ELAPSED_OFF          = 0x12c;
    var BT_SPEED_MULT_OFF       = 0x130;
    var BT_PHASE_INDICATOR_OFF  = 0x134;
    var BT_CYCLE_COUNT_OFF      = 0x138;
    var BT_PHASE_REMAINING_OFF  = 0x13c;
    var BT_BOSS_TIME_OFF        = 0x144;
    var BT_IS_BOSS_AWAKEN_OFF   = 0x148;
    var BT_IS_OVERTIME_OFF      = 0x149;
    var BT_BOSS_DISABLED_OFF    = 0x14b;

    if (!RW.ChapterBoss) RW.ChapterBoss = {};
    var ChapterBoss = RW.ChapterBoss;

    ChapterBoss.timer = ChapterBoss.timer || null;   // NativePointer | null
    ChapterBoss._hook = ChapterBoss._hook || null;

    // Detach any prior hook (re-load safety) and arm a fresh one. The hook
    // is hot path — captures the live timer pointer on every Update call so
    // we always track the current chapter's instance across transitions.
    if (ChapterBoss._hook) {
        try { ChapterBoss._hook.detach(); } catch (e) {}
        ChapterBoss._hook = null;
    }
    ChapterBoss._hook = Interceptor.attach(imageBase.add(BOSS_TIMER_UPDATE_RVA), {
        onEnter: function (args) {
            ChapterBoss.timer = args[0];
        }
    });

    /*
     * ----------------------------------------------------------------
     * ChapterBoss.spawn(): void
     *
     * Force the current chapter's boss to arrive on the next frame.
     * No-op if the boss has already awakened in this chapter.
     *
     * Requirements:
     *   You are in-game (BossTimer_update must have ticked at least once
     *   after this power loaded, so ChapterBoss.timer is populated).
     *
     * Result:
     *   The chapter's normal boss-arrival sequence plays starting on the
     *   next frame: portal, cinematic, arena. Defeating the boss emits
     *   the standard chapter-end save event.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   We don't spawn the boss; we push the chapter's day/night clock
     *   past its arrival threshold so the engine spawns it on the next
     *   frame, identical to natural chapter progression.
     *   Chain:
     *     1. Write BossTimer.elapsed (+0x12c) = BossTimer.boss_time (+0x144).
     *     2. Next engine frame: BossTimer_update (image+0x1e9d50) ticks.
     *     3. The comparison `elapsed >= boss_time` evaluates true.
     *     4. Engine sets is_boss_awaken (+0x148) = 1.
     *     5. Engine fires named event 0x17d8d901 ("Boss time start").
     *     6. Existing subscribers run: portal spawn, cinematic, arena spawn.
     *     7. Killing the boss emits the normal chapter-end save event.
     *   Single-chapter only — other chapters' boss content isn't loaded,
     *   so even if the comparison fires there's nothing to spawn.
     */
    ChapterBoss.spawn = function () {
        if (ChapterBoss.timer === null) {
            console.log("[ChapterBoss] timer not captured yet — wait until in-game " +
                        "(BossTimer_update must tick at least once)");
            return;
        }
        try {
            var t = ChapterBoss.timer;
            var bossTime = t.add(BT_BOSS_TIME_OFF).readFloat();
            var elapsedBefore = t.add(BT_ELAPSED_OFF).readFloat();
            var isAwaken = t.add(BT_IS_BOSS_AWAKEN_OFF).readU8();
            if (isAwaken !== 0) {
                console.log("[ChapterBoss] already awakened (is_boss_awaken=" +
                            isAwaken + "); no-op");
                return;
            }
            t.add(BT_ELAPSED_OFF).writeFloat(bossTime);
            console.log("[ChapterBoss] timer=" + t +
                        " elapsed " + elapsedBefore.toFixed(2) +
                        " -> " + bossTime.toFixed(2) +
                        " (boss_time). Next frame fires 0x17d8d901.");
        } catch (e) {
            console.log("[ChapterBoss] spawn write FAILED " + e.message);
        }
    };

    /*
     * ----------------------------------------------------------------
     * ChapterBoss.delaySpawn(seconds: number): void
     *
     * Engine-tick delay variant of ChapterBoss.spawn — see
     * CODE_STANDARDS.md §Delays. Schedules arrival `seconds` of GAME
     * TIME from now; pauses with the game and scales with the timer's
     * speedMult.
     *
     * Edge cases:
     *   - seconds <= 0 → fires next frame, equivalent to spawn().
     *   - seconds > current_remaining → rewinds the timer; the engine
     *     simply ticks back up and fires later.
     *   - is_boss_awaken already set → no-op (boss already arrived).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Writes BossTimer.elapsed = boss_time - seconds. The engine's
     *   natural BossTimer_update tick advances elapsed each frame
     *   (scaled by speedMult); when elapsed >= boss_time the comparison
     *   fires and the standard arrival event chain runs. See spawn()
     *   MECHANISM for the rest of the chain.
     */
    ChapterBoss.delaySpawn = function (seconds) {
        if (typeof seconds !== 'number') {
            console.log("[ChapterBoss.delaySpawn] usage: ChapterBoss.delaySpawn(seconds)");
            return;
        }
        if (ChapterBoss.timer === null) {
            console.log("[ChapterBoss.delaySpawn] timer not captured yet — wait until in-game");
            return;
        }
        try {
            var t = ChapterBoss.timer;
            var bossTime = t.add(BT_BOSS_TIME_OFF).readFloat();
            var elapsedBefore = t.add(BT_ELAPSED_OFF).readFloat();
            var isAwaken = t.add(BT_IS_BOSS_AWAKEN_OFF).readU8();
            if (isAwaken !== 0) {
                console.log("[ChapterBoss.delaySpawn] already awakened; no-op");
                return;
            }
            var target = bossTime - seconds;
            t.add(BT_ELAPSED_OFF).writeFloat(target);
            console.log("[ChapterBoss.delaySpawn] elapsed " + elapsedBefore.toFixed(2) +
                        " -> " + target.toFixed(2) +
                        " (boss_time " + bossTime.toFixed(2) +
                        " - " + seconds.toFixed(2) + "s)");
        } catch (e) {
            console.log("[ChapterBoss.delaySpawn] write FAILED " + e.message);
        }
    };

    /*
     * ----------------------------------------------------------------
     * ChapterBoss.status(): void
     *
     * Dump the BossTimer's runtime state. Pure diagnostic — no game
     * state changes. Use to verify the power sees a live timer before
     * calling spawn() / delaySpawn(), or to inspect threshold values
     * for delay experiments.
     *
     * Result:
     *   Logs two lines covering every documented BossTimer field —
     *   elapsed, boss_time, remaining seconds, speed multiplier, warn /
     *   overtime offsets, day/night durations, phase + cycle counters,
     *   and the boolean state (arrival-enabled, timer-enabled, awakening,
     *   overtime, disabled).
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Reads the BossTimer field block at +0xac..+0x14b documented at
     *   the top of this file. Field map cross-references
     *   rw/findings/chapter-boss-portal-trigger.md.
     */
    ChapterBoss.status = function () {
        if (ChapterBoss.timer === null) {
            console.log("[ChapterBoss.status] timer not captured yet — wait until in-game");
            return;
        }
        try {
            var t = ChapterBoss.timer;
            var elapsed     = t.add(BT_ELAPSED_OFF).readFloat();
            var bossTime    = t.add(BT_BOSS_TIME_OFF).readFloat();
            var warnOff     = t.add(BT_WARN_OFF).readFloat();
            var overtimeOff = t.add(BT_OVERTIME_OFF).readFloat();
            var dayDur      = t.add(BT_DAY_DURATION_OFF).readFloat();
            var nightDur    = t.add(BT_NIGHT_DURATION_OFF).readFloat();
            var speedMult   = t.add(BT_SPEED_MULT_OFF).readFloat();
            var phaseRem    = t.add(BT_PHASE_REMAINING_OFF).readFloat();
            var cycleCount  = t.add(BT_CYCLE_COUNT_OFF).readInt();
            var arrivalOn   = t.add(BT_ARRIVAL_ENABLED_OFF).readInt();
            var timerOn     = t.add(BT_TIMER_ENABLED_OFF).readU8();
            var isAwaken    = t.add(BT_IS_BOSS_AWAKEN_OFF).readU8();
            var isOvertime  = t.add(BT_IS_OVERTIME_OFF).readU8();
            var isDisabled  = t.add(BT_BOSS_DISABLED_OFF).readU8();
            var phase       = t.add(BT_PHASE_INDICATOR_OFF).readU8();
            var remaining   = bossTime - elapsed;
            console.log("[ChapterBoss.status] timer=" + t +
                        " elapsed="     + elapsed.toFixed(2) +
                        " boss_time="   + bossTime.toFixed(2) +
                        " remaining="   + remaining.toFixed(2) + "s" +
                        " speedMult="   + speedMult.toFixed(2) +
                        " warnOff="     + warnOff.toFixed(2) +
                        " overtimeOff=" + overtimeOff.toFixed(2));
            console.log("[ChapterBoss.status] phase=" + phase +
                        " phaseRemaining=" + phaseRem.toFixed(2) +
                        " cycleCount="     + cycleCount +
                        " dayDur="         + dayDur.toFixed(2) +
                        " nightDur="       + nightDur.toFixed(2) +
                        " arrivalEnabled=" + arrivalOn +
                        " timerEnabled="   + timerOn +
                        " isAwaken="       + isAwaken +
                        " isOvertime="     + isOvertime +
                        " isDisabled="     + isDisabled);
        } catch (e) {
            console.log("[ChapterBoss.status] read FAIL " + e.message);
        }
    };

    RW.registerMod("power:ChapterBoss", version);
    console.log("[ChapterBoss] " + version + " loaded. Try: ChapterBoss.status(); ChapterBoss.spawn()");
})();

// Top-level alias for REPL convenience
var ChapterBoss = RW.ChapterBoss;
