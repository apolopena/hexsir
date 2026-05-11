// Currency.js — global currency wallet writes.
//
// Bundles all global wallet currencies under one namespace as we map
// each. Today only Dream Shards is wired; Stars, Feathers, and Keys
// will get their own methods when their HC fields / save-file paths
// are mapped.
//
// REPL surface (after loadPower("Currency")):
//   Currency.addShards(n: number): void
//   Currency.hc: NativePointer | null   (captured HeroController pointer)

(function () {
    var version = "0.1.0";
    var mod = Process.findModuleByName("Ravenswatch.exe");
    if (!mod) { console.log("[Currency] FATAL: no Ravenswatch.exe"); return; }
    var imageBase = mod.base;

    // Used by the file-scope HC-capture hook below.
    var HC_CHANGE_DREAM_SHARDS_RVA = 0x38c2b0;

    if (!RW.Currency) RW.Currency = {};
    var Currency = RW.Currency;

    Currency.hc = Currency.hc || null;
    Currency._hook = Currency._hook || null;

    // Capture HC on every gain/loss event so we always have a live pointer
    // (refreshes across chapter transitions if HC is recreated). The hook
    // is hot path; the body is one assignment.
    if (Currency._hook) {
        try { Currency._hook.detach(); } catch (e) {}
        Currency._hook = null;
    }
    Currency._hook = Interceptor.attach(imageBase.add(HC_CHANGE_DREAM_SHARDS_RVA), {
        onEnter: function (args) {
            Currency.hc = args[0];
        }
    });

    /*
     * ----------------------------------------------------------------
     * Currency.addShards(n: number): void
     *
     * Add (or subtract, with negative n) Dream Shards on the local
     * player. Floors at zero. HUD updates immediately.
     *
     * Requirements:
     *   You are in-game and have earned/spent at least one shard since
     *   loading this power, so Currency.hc is captured. (Any shard event
     *   populates it via the entry hook.)
     *
     * Result:
     *   The local player's wallet changes by `n`. Logs the before/after.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Direct memory write to HC+0x1590 (held_dream_shards, float32).
     *   The HUD reads this field every frame so a raw write is enough
     *   to update the displayed count. The canonical gain/loss function
     *   HC_change_dream_shards (RVA 0x38c2b0) is the entry-hook source
     *   for capturing HC; we don't call it because its third arg
     *   (oCCustomFlagList*) needs to be a live instance captured from a
     *   natural event. See rw/findings/multiplayer-host-authority.md
     *   for the full architecture (HC+0x1590 raw write → per-frame
     *   watcher → replication propagation).
     *
     *   HC CAPTURE SOURCES — HACK ALERT. Currency.hc can come from two
     *   places, and the second one is a genuine kludge.
     *
     *   Primary: Currency's own hook on HC_change_dream_shards fires
     *   only when the player gains or spends a shard, so on a fresh
     *   load Currency.hc is null until the first natural shard event.
     *   That's real friction in interactive use.
     *
     *   Fallback (the kludge): we reach into ANOTHER POWER's state
     *   (RW.Teleport.hc), populated by Teleport's HC_per_frame_update
     *   hook, and copy its HC pointer over. It's the same HC pointer
     *   conceptually, captured cheaper, but Currency now silently
     *   depends on Teleport being loaded for the early-window case
     *   to work. The dependency is documented (see CODE_STANDARDS.md
     *   §Cross-power state sharing) and bounded (Currency only READS
     *   Teleport.hc, never writes), but it's a coupling we'd ideally
     *   eliminate by promoting HC capture to a shared utility
     *   (RW.hc) once a third power needs it. Until then: load
     *   Teleport before calling Currency.addShards, or earn a shard
     *   first; if neither path has captured, we report a clear
     *   message and bail.
     *
     *   P2P SIDE EFFECT — this affects only the player making the
     *   call (single-player effect; not propagated to peers in MP).
     *   It's a consequence of the peer-to-peer architecture: the
     *   write happens locally and isn't broadcast through the natural
     *   gain/loss event chain, so peers don't see it. The engine
     *   also tracks cumulative-earned (HC+0x1d48*) and cumulative-spent
     *   (HC+0x1d78*) separately, populated by the natural events.
     *   Bypassing the events leaves spent > earned on the local stats
     *   page — not an anti-cheat tripwire, just a natural artifact of
     *   the missing earn-event. Confirmed runtime 2026-05-04: HUD
     *   updates live.
     *
     *   Save-file note: the byte-packed save offset for the same field
     *   is at +0x1d (odd offset, byte-packed); see
     *   rw/findings/held-dream-shards.md.
     */
    Currency.addShards = function (n) {
        var HC_HELD_SHARDS_OFF = 0x1590;   // float32 — held_dream_shards

        if (typeof n !== 'number') {
            console.log("[Currency.addShards] usage: Currency.addShards(deltaInt)");
            return;
        }
        // Fallback: if our shard-event hook hasn't fired yet, borrow the HC
        // pointer from Teleport's per-frame capture. Same HC, captured cheaper.
        if (Currency.hc === null && RW.Teleport && RW.Teleport.hc) {
            Currency.hc = RW.Teleport.hc;
        }
        if (Currency.hc === null) {
            console.log("[Currency.addShards] HC not captured — load Teleport (auto-captures every frame) or earn/spend a shard");
            return;
        }
        try {
            var cur = Currency.hc.add(HC_HELD_SHARDS_OFF).readFloat();
            var next = Math.max(0, cur + n);
            Currency.hc.add(HC_HELD_SHARDS_OFF).writeFloat(next);
            console.log("[Currency.addShards] HC=" + Currency.hc +
                        " +0x1590 " + cur.toFixed(2) + " -> " + next.toFixed(2) +
                        " (delta=" + n + ")");
        } catch (e) {
            console.log("[Currency.addShards] write FAIL " + e.message);
        }
    };

    RW.registerMod("power:Currency", version);
    console.log("[Currency] " + version + " loaded. Try: Currency.addShards(100)");
})();

// Top-level alias for REPL convenience
var Currency = RW.Currency;
