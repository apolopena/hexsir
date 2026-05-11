// SmokeTest.js — end-to-end exercise of the lab's powers.
//
// Auto-loads Currency, Teleport, ChapterBoss (idempotent), waits for
// their live captures, then walks through three actions with terse
// help output and 1-second countdowns:
//
//   1. Currency.addShards(101)             — instant
//   2. Teleport round-trip (delayTo + to)  — 5s outbound, 3s pause, 1s back
//   3. ChapterBoss.delaySpawn(5)           — 5s engine-tick delay
//
// Round-trip pattern for the teleport demo: capture the player's CURRENT
// position, teleport to (origin + 30 X), pause, snap back. Origin is
// definitionally on-map; +30 X may overshoot near map edges, but the
// snap-back recovers cleanly. No hardcoded coords.
//
// Status: experimental — exercises the API surface, not exhaustive.
// Failure cases (game paused, in lobby, no in-game frame to capture
// pointers) report a clear message and abort early.
//
// REPL surface (after loadPower("SmokeTest")):
//   SmokeTest.run(): void

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[SmokeTest] FATAL: no Ravenswatch.exe"); return; }

    var SHARDS_AMOUNT     = 11;
    var TELEPORT_DELTA_X  = 30;
    var DELAY_SECONDS     = 5;
    var DESTINATION_PAUSE_MS = 3000;
    var CAPTURE_TIMEOUT_MS   = 3000;
    var CAPTURE_POLL_MS      =  100;

    if (!RW.SmokeTest) RW.SmokeTest = {};
    var SmokeTest = RW.SmokeTest;

    function ts(t0) {
        return '[T+' + ((Date.now() - t0) / 1000).toFixed(2) + 's]';
    }

    function header(t0, line) {
        console.log('\n' + ts(t0) + ' ' + line);
    }

    // Poll a predicate until true or timeout. Calls onResult(true|false).
    function waitFor(predicate, label, t0, onResult) {
        var elapsed = 0;
        function tick() {
            if (predicate()) { onResult(true); return; }
            if (elapsed >= CAPTURE_TIMEOUT_MS) {
                console.log(ts(t0) + ' [pre-flight] timeout waiting for ' + label +
                            ' — is the game in-game and unpaused?');
                onResult(false); return;
            }
            elapsed += CAPTURE_POLL_MS;
            setTimeout(tick, CAPTURE_POLL_MS);
        }
        tick();
    }

    function countdown(seconds, prefix, onFire) {
        var n = seconds;
        function tick() {
            if (n <= 0) { onFire(); return; }
            console.log(prefix + ' T-' + n + '...');
            n--;
            setTimeout(tick, 1000);
        }
        tick();
    }

    function preflight(t0, onReady) {
        header(t0, '[pre-flight] auto-loading powers');
        try {
            if (!RW.Currency)    RW.loadPower("Currency");
            if (!RW.Teleport)    RW.loadPower("Teleport");
            if (!RW.ChapterBoss) RW.loadPower("ChapterBoss");
        } catch (e) {
            console.log(ts(t0) + ' [pre-flight] loadPower failed: ' + e.message);
            onReady(false); return;
        }

        console.log(ts(t0) + ' [pre-flight] arming Teleport.refresh()');
        RW.Teleport.refresh();

        waitFor(function () { return RW.Teleport.player !== null; },
                'Teleport.player', t0, function (ok) {
            if (!ok) { onReady(false); return; }
            console.log(ts(t0) + ' [pre-flight] Teleport.player captured');
            waitFor(function () { return RW.ChapterBoss.timer !== null; },
                    'ChapterBoss.timer', t0, function (ok2) {
                if (!ok2) { onReady(false); return; }
                console.log(ts(t0) + ' [pre-flight] ChapterBoss.timer captured');
                onReady(true);
            });
        });
    }

    function runCurrency(t0, onDone) {
        header(t0, '=== action 1/3: Currency.addShards(' + SHARDS_AMOUNT + ') ===');
        RW.help("Currency.addShards");
        console.log(ts(t0) + ' [SmokeTest] gaining ' + SHARDS_AMOUNT + ' shards...');
        try {
            RW.Currency.addShards(SHARDS_AMOUNT);
            onDone(true);
        } catch (e) {
            console.log(ts(t0) + ' [SmokeTest] addShards FAIL: ' + e.message);
            onDone(false);
        }
    }

    function runTeleport(t0, onDone) {
        header(t0, '=== action 2/3: Teleport round-trip ===');
        RW.help("Teleport.delayTo");

        var origin = RW.Teleport.position();
        if (!origin) {
            console.log(ts(t0) + ' [SmokeTest] could not read origin — abort teleport action');
            onDone(false); return;
        }
        var target = [origin[0] + TELEPORT_DELTA_X, origin[1], origin[2]];
        console.log(ts(t0) + ' [SmokeTest] origin=(' + origin[0].toFixed(2) + ',' +
                    origin[1].toFixed(2) + ',' + origin[2].toFixed(2) + ')' +
                    '  target=(' + target[0].toFixed(2) + ',' +
                    target[1].toFixed(2) + ',' + target[2].toFixed(2) + ')');

        countdown(DELAY_SECONDS, ts(t0) + ' [SmokeTest]', function () {
            RW.Teleport.to(target[0], target[1], target[2]);
            console.log(ts(t0) + ' [SmokeTest] (' + (DESTINATION_PAUSE_MS / 1000) + 's pause at destination)');
            setTimeout(function () {
                console.log(ts(t0) + ' [SmokeTest] returning to origin');
                try {
                    RW.Teleport.to(origin[0], origin[1], origin[2]);
                    onDone(true);
                } catch (e) {
                    console.log(ts(t0) + ' [SmokeTest] return-teleport FAIL: ' + e.message);
                    onDone(false);
                }
            }, DESTINATION_PAUSE_MS);
        });
    }

    function runChapterBoss(t0, onDone) {
        header(t0, '=== action 3/3: ChapterBoss.delaySpawn(' + DELAY_SECONDS + ') ===');
        RW.help("ChapterBoss.delaySpawn");
        countdown(DELAY_SECONDS, ts(t0) + ' [SmokeTest]', function () {
            try {
                RW.ChapterBoss.delaySpawn(DELAY_SECONDS);
                onDone(true);
            } catch (e) {
                console.log(ts(t0) + ' [SmokeTest] delaySpawn FAIL: ' + e.message);
                onDone(false);
            }
        });
    }

    function summary(t0, results) {
        var passed = 0, failed = 0;
        for (var i = 0; i < results.length; i++) {
            if (results[i]) passed++; else failed++;
        }
        var dt = ((Date.now() - t0) / 1000).toFixed(2);
        header(t0, '[SmokeTest] complete in ' + dt + 's — passed=' + passed +
               '  failed=' + failed + '  (of ' + results.length + ')');
    }

    /*
     * ----------------------------------------------------------------
     * SmokeTest.run(): void
     *
     * Walk through the Currency / Teleport / ChapterBoss powers as a
     * live-fire end-to-end exercise. Auto-loads any missing powers,
     * waits up to 3s for live captures, then runs three actions in
     * sequence with 5-second countdowns and per-step help.
     *
     * Requirements:
     *   You are in-game and unpaused (frames must tick so Teleport's
     *   capture hook and ChapterBoss's update hook can fire).
     *
     * Result:
     *   Adds 101 Dream Shards; teleports +30 X then snaps back to
     *   origin; forces the chapter boss to arrive 5 game-seconds
     *   later. Logs a pass/fail summary at the end.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Pre-flight calls loadPower for Currency / Teleport / ChapterBoss
     *   (idempotent — re-load is a no-op for already-loaded powers).
     *   Calls Teleport.refresh() to arm capture, then polls
     *   RW.Teleport.player and RW.ChapterBoss.timer until populated.
     *   Each action calls help() (terse), announces, fires a 1-second
     *   tick countdown, and invokes the corresponding power method.
     *   The Teleport demo is a round-trip: captures the player's live
     *   position, teleports +30 X via delayTo + the absolute coord,
     *   pauses 3s at the destination, then snaps back to origin via
     *   Teleport.to. ChapterBoss.delaySpawn is engine-tick (not
     *   wall-clock) — the 1-second countdown is for output cadence;
     *   actual fire timing scales with timer.speedMult.
     */
    SmokeTest.run = function () {
        var t0 = Date.now();
        var results = [];
        console.log('\n[SmokeTest] starting at ' + new Date().toISOString());

        preflight(t0, function (ready) {
            if (!ready) {
                console.log(ts(t0) + ' [SmokeTest] pre-flight failed — aborting');
                return;
            }
            runCurrency(t0, function (r1) {
                results.push(r1);
                runTeleport(t0, function (r2) {
                    results.push(r2);
                    runChapterBoss(t0, function (r3) {
                        results.push(r3);
                        summary(t0, results);
                    });
                });
            });
        });
    };

    RW.registerMod("power:SmokeTest", version);
    console.log("[SmokeTest] " + version + " loaded. Try: SmokeTest.run()");
})();

// Top-level alias for REPL convenience
var SmokeTest = RW.SmokeTest;
