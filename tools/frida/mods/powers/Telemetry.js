// Telemetry.js — block / inspect outbound telemetry calls at the WinHTTP layer.
//
// Hooks winhttp!WinHttpSendRequest with a host-suffix filter. Matched hosts
// (passtechgames.com, nacon-os.com, submit.backtrace.io, *.run.app) can be
// blocked (return BOOL FALSE without making the call) and/or logged
// (cleartext request body printed to stdout before WinHTTP encrypts).
//
// Companion to tools/telemetry-warden/. The warden blocks at the network
// layer (hosts file → 127.0.0.1 listener); this power kills the call inside
// the process before WinHTTP even starts. With Telemetry.disable() active,
// no socket opens, so the warden has nothing to log either — the dt-live
// retry storm goes silent.
//
// REPL surface (after loadPower("Telemetry")):
//   Telemetry.disable(): void                     install hook + block matched calls
//   Telemetry.enable(): void                      stop blocking; matched calls pass through
//   Telemetry.log(on?: boolean | number): void    toggle cleartext-body stdout printing;
//                                                 pass a positive integer N to print the
//                                                 next N complete non-empty bodies then
//                                                 auto-disable
//   Telemetry.stats(): {matched,blocked,logged}
//
// Notes:
//   - Hook is installed once on loadPower; disable/enable/log just flip
//     internal flags the hook reads each call.
//   - log() works in both states. With disable + log, the body is observed
//     and then the call is blocked.
//   - Per-call block visibility: blocking by itself is silent (only the
//     blocked counter increments). For one line per blocked call, combine
//     Telemetry.disable() with Telemetry.log(true) — the hook prints
//     "<url> body(N): ..." or "<url> (no body)" BEFORE returning FALSE.
//     Caveat: streaming-body sends are NOT printed in this combination
//     (streaming registration is skipped when disabled, since the failed
//     SendRequest never produces WriteData calls). For empty-body
//     endpoints like the dt-live heartbeat that's fine — they print as
//     "(no body)" via the inline path.
//   - Output goes to stdout only — nothing is ever written to disk.
//   - Body decoding assumes UTF-8 (true for JSON analytics POSTs);
//     binary auth blobs may print as gibberish but the byte length is
//     accurate.
//   - Streaming POSTs (lpOptional=NULL, body delivered via WinHttpWriteData
//     after SendRequest returns — what passtechgames dt-live does) are
//     captured chunk-by-chunk in memory and printed as one line on
//     completion: "<url> body(N): <bytes>". No per-chunk noise.
//   - log(N) captures the next N complete non-empty bodies (inline or
//     streaming) and auto-disables logging — useful when dt-live fires at
//     1 Hz and you only want a finite sample. Empty-body matches (e.g.
//     GET handshakes like _federation) don't consume the budget; only
//     bodies with actual bytes count toward N.
//   - Per rw/findings/telemetry-surface-and-warden.md.

(function () {
    var version = "0.6.0";

    if (typeof RW !== "object") {
        console.log("[Telemetry] FATAL: RW missing — load rw_lab.js first");
        return;
    }

    var winhttpMod = Process.findModuleByName("winhttp.dll");
    if (!winhttpMod) {
        console.log("[Telemetry] FATAL: winhttp.dll not loaded yet (game not initialized HTTP?)");
        return;
    }
    var winhttp = winhttpMod.findExportByName("WinHttpSendRequest");
    var queryOptionAddr = winhttpMod.findExportByName("WinHttpQueryOption");
    var writeDataAddr = winhttpMod.findExportByName("WinHttpWriteData");
    var closeHandleAddr = winhttpMod.findExportByName("WinHttpCloseHandle");
    if (!winhttp || !queryOptionAddr || !writeDataAddr || !closeHandleAddr) {
        console.log("[Telemetry] FATAL: required winhttp.dll exports missing " +
                    "(SendRequest/QueryOption/WriteData/CloseHandle)");
        return;
    }

    // Host-suffix patterns. A request URL whose host CONTAINS any of these
    // strings is filtered. Kept intentionally broad to catch new subdomains
    // (e.g. dt-live-N, nacon-os-rec-vN).
    var HOST_PATTERNS = [
        "passtechgames.com",
        "nacon-os.com",
        "nacon-os-rec",
        "submit.backtrace.io",
        ".a.run.app"
    ];

    // WinHttpQueryOption flag: returns the full request URL as a wide string.
    var WINHTTP_OPTION_URL = 34;

    if (!RW.Telemetry) RW.Telemetry = {};
    var Telemetry = RW.Telemetry;

    // Persistent state across reloads.
    Telemetry._disabled = Telemetry._disabled || false;
    Telemetry._logging = Telemetry._logging || false;
    Telemetry._installed = Telemetry._installed || false;
    Telemetry._stats = Telemetry._stats || { matched: 0, blocked: 0, logged: 0 };
    // hRequest.toString() → { url, totalLen, captured } for in-flight streaming sends.
    Telemetry._streaming = {};

    // Re-load safety: revert prior replacement + detach prior listeners before re-installing.
    if (Telemetry._installed) {
        try { Interceptor.revert(winhttp); } catch (e) {}
        if (Telemetry._listeners) {
            for (var li = 0; li < Telemetry._listeners.length; li++) {
                try { Telemetry._listeners[li].detach(); } catch (e) {}
            }
        }
        Telemetry._installed = false;
    }
    Telemetry._listeners = [];

    // BOOL WinHttpQueryOption(HINTERNET, DWORD, LPVOID, LPDWORD)
    var WinHttpQueryOption = new NativeFunction(queryOptionAddr, "int",
        ["pointer", "uint32", "pointer", "pointer"]);

    function getRequestUrl(hRequest) {
        try {
            var bufBytes = 4096;
            var buf = Memory.alloc(bufBytes);
            var lenPtr = Memory.alloc(4);
            lenPtr.writeU32(bufBytes);
            var ok = WinHttpQueryOption(hRequest, WINHTTP_OPTION_URL, buf, lenPtr);
            if (!ok) return null;
            return buf.readUtf16String();
        } catch (e) {
            return null;
        }
    }

    function urlHost(url) {
        if (!url) return null;
        var m = url.match(/^https?:\/\/([^\/:?]+)/i);
        return m ? m[1].toLowerCase() : null;
    }

    function hostMatches(host) {
        if (!host) return false;
        for (var i = 0; i < HOST_PATTERNS.length; i++) {
            if (host.indexOf(HOST_PATTERNS[i]) >= 0) return true;
        }
        return false;
    }

    // Single-line print on body completion (inline at SendRequest, or last
    // WriteData chunk for streaming sends). Re-checks _logging at print time
    // so budget mode that already exhausted earlier silently drops later
    // completions, and empty bodies don't consume the budget.
    function emitComplete(url, body, bytes) {
        if (!Telemetry._logging) return;
        var inBudgetMode = (typeof Telemetry._logging === "number");
        if (bytes === 0 && inBudgetMode) return; // skip empty matches; keep budget intact
        if (bytes === 0) {
            console.log("[Telemetry.log] " + url + " (no body)");
        } else {
            console.log("[Telemetry.log] " + url + " body(" + bytes + "): " + body);
        }
        Telemetry._stats.logged++;
        if (inBudgetMode) {
            Telemetry._logging--;
            if (Telemetry._logging <= 0) {
                Telemetry._logging = false;
                console.log("[Telemetry] logging budget exhausted → off");
            }
        }
    }

    // BOOL WinHttpSendRequest(HINTERNET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, DWORD_PTR)
    var winhttpArgTypes = ["pointer", "pointer", "uint32", "pointer", "uint32", "uint32", "pointer"];
    var origSendRequest = new NativeFunction(winhttp, "int", winhttpArgTypes);

    Interceptor.replace(winhttp, new NativeCallback(
        function (hRequest, lpszHeaders, dwHeadersLength, lpOptional,
                  dwOptionalLength, dwTotalLength, dwContext) {
            try {
                var url = getRequestUrl(hRequest);
                var host = urlHost(url);

                if (hostMatches(host)) {
                    Telemetry._stats.matched++;

                    if (Telemetry._logging) {
                        var bodyLen = dwOptionalLength | 0;
                        var totalLen = dwTotalLength | 0;
                        var inlineBody = "";
                        if (bodyLen > 0 && !lpOptional.isNull()) {
                            try {
                                inlineBody = lpOptional.readUtf8String(bodyLen);
                            } catch (e) {
                                inlineBody = "<read fail: " + e.message + ">";
                            }
                        }

                        if (totalLen <= bodyLen) {
                            // Body delivered in full at SendRequest time (or no body at all).
                            emitComplete(url, inlineBody, bodyLen);
                        } else if (!Telemetry._disabled) {
                            // Streaming: caller will deliver the rest via WinHttpWriteData.
                            // Register the handle so the WriteData hook can pick up chunks.
                            // Skip when disable() will short-circuit the send below — no
                            // WriteData calls will follow on a failed request.
                            Telemetry._streaming[hRequest.toString()] = {
                                url: url,
                                totalLen: totalLen,
                                captured: inlineBody,
                                capturedBytes: bodyLen
                            };
                        }
                    }

                    if (Telemetry._disabled) {
                        Telemetry._stats.blocked++;
                        return 0; // BOOL FALSE — caller treats as failed send
                    }
                }
            } catch (e) {
                console.log("[Telemetry] hook error: " + e.message);
            }

            return origSendRequest(hRequest, lpszHeaders, dwHeadersLength,
                                   lpOptional, dwOptionalLength, dwTotalLength, dwContext);
        },
        "int", winhttpArgTypes
    ));
    Telemetry._installed = true;

    // BOOL WinHttpWriteData(HINTERNET, LPCVOID, DWORD, LPDWORD)
    // Picks up streamed bodies for matched requests registered by the SendRequest hook.
    Telemetry._listeners.push(Interceptor.attach(writeDataAddr, {
        onEnter: function (args) {
            try {
                var key = args[0].toString();
                var entry = Telemetry._streaming[key];
                if (!entry) return;
                var len = args[2].toUInt32();
                var buf = args[1];
                var chunk = "";
                if (len > 0 && !buf.isNull()) {
                    try {
                        chunk = buf.readUtf8String(len);
                    } catch (e) {
                        chunk = "<read fail: " + e.message + ">";
                    }
                }
                entry.captured += chunk;
                entry.capturedBytes += len;
                if (entry.capturedBytes >= entry.totalLen) {
                    emitComplete(entry.url, entry.captured, entry.totalLen);
                    delete Telemetry._streaming[key];
                }
            } catch (e) {
                console.log("[Telemetry] WriteData hook error: " + e.message);
            }
        }
    }));

    // BOOL WinHttpCloseHandle(HINTERNET) — evict stale streaming entries on aborted/closed sends.
    Telemetry._listeners.push(Interceptor.attach(closeHandleAddr, {
        onEnter: function (args) {
            var key = args[0].toString();
            if (Telemetry._streaming[key]) delete Telemetry._streaming[key];
        }
    }));

    /*
     * ----------------------------------------------------------------
     * Telemetry.disable(): void
     *
     * Block all matched outbound telemetry calls inside the process.
     * Matched hosts are passtechgames.com, nacon-os.com, *.run.app
     * (Cloud Run), and submit.backtrace.io (crash reports). With
     * disable() in effect, WinHttpSendRequest returns FALSE for matches
     * without doing any I/O — no socket, no DNS, no TLS handshake.
     * The warden goes silent for these hosts.
     *
     * Pairs with Telemetry.enable() to restore default behavior.
     *
     * Result:
     *   Logs "[Telemetry] disabled (N matched so far)". Subsequent
     *   matched calls return BOOL FALSE.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   The Interceptor.replace hook is installed once at loadPower
     *   time. disable()/enable() flip Telemetry._disabled which the
     *   hook reads on every WinHttpSendRequest invocation. Toggling
     *   never re-attaches — that would race with in-flight calls.
     */
    Telemetry.disable = function () {
        Telemetry._disabled = true;
        console.log("[Telemetry] disabled (matched " + Telemetry._stats.matched + " so far)");
    };

    /*
     * ----------------------------------------------------------------
     * Telemetry.enable(): void
     *
     * Restore default behavior: matched WinHttpSendRequest calls pass
     * through to WinHTTP normally. If the warden is running it will
     * resume blocking them at the network layer (and you'll see the
     * dt-live retry storm in its log again).
     *
     * Result:
     *   Logs "[Telemetry] enabled". Matched calls resume going out.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   Sets Telemetry._disabled = false. Hook stays installed.
     */
    Telemetry.enable = function () {
        Telemetry._disabled = false;
        console.log("[Telemetry] enabled");
    };

    /*
     * ----------------------------------------------------------------
     * Telemetry.log(on?: boolean): void
     *
     * Toggle (or explicitly set) cleartext-body stdout printing. One
     * line per matched request, printed at body completion:
     *   [Telemetry.log] <url> body(N): <bytes>
     *   [Telemetry.log] <url> (no body)
     * Nothing is written to disk; redirect REPL stdout yourself if you
     * want persistence.
     *
     * Usage:
     *   Telemetry.log()         toggle on/off
     *   Telemetry.log(true)     force on (forever)
     *   Telemetry.log(false)    force off
     *   Telemetry.log(N)        positive integer — print the next N
     *                           complete non-empty bodies (inline or
     *                           streaming) then auto-disable. Calling
     *                           log(N) again while in budget mode adds
     *                           to the remaining budget.
     *
     * Empty-body matches (e.g. GET handshakes like _federation that
     * print as "(no body)") do NOT consume budget — only bodies with
     * actual bytes count toward N.
     *
     * Logging works regardless of disable()/enable() state. Combined
     * with disable(): see the body, then block the send.
     *
     * Result:
     *   Logs "[Telemetry] logging on/off" or "logging next N complete
     *   bodies — ...". Matched calls thereafter print their cleartext
     *   body once complete; in budget mode each printed body decrements
     *   N and logging flips off when N hits zero.
     * ----------------------------------------------------------------
     * MECHANISM:
     *   WinHttpSendRequest's lpOptional/dwOptionalLength are the
     *   cleartext request body — TLS encryption happens inside WinHTTP
     *   *after* this function returns. We read len bytes from lpOptional
     *   as UTF-8 (correct for JSON analytics POSTs; binary auth blobs
     *   render as gibberish but byte count is accurate).
     *   When dwTotalLength > dwOptionalLength the caller will stream the
     *   remainder via WinHttpWriteData after SendRequest returns. The
     *   hRequest is parked in Telemetry._streaming and chunks are
     *   accumulated silently; emitComplete fires the single print line
     *   when capturedBytes >= totalLen. WinHttpCloseHandle evicts entries
     *   on aborted/closed sends — those produce no output.
     *   Budget mode (log(N)) stores the remaining count in _logging
     *   itself — false / true / positive integer is a tri-state read by
     *   emitComplete at print time. Decrement happens on print only, so
     *   aborts (CloseHandle on a tracked but incomplete entry) cost
     *   nothing: the budget waits for the next request that completes.
     *   Late streaming completions after budget hits zero re-check
     *   _logging at print time and drop silently — no noise.
     */
    Telemetry.log = function (on) {
        if (typeof on === "number") {
            if (!(on > 0) || !Number.isInteger(on)) {
                console.log("[Telemetry] log(N) requires a positive integer (got " + on + ")");
                return;
            }
            // Add to existing budget if already in count mode; else set fresh.
            var prev = (typeof Telemetry._logging === "number") ? Telemetry._logging : 0;
            Telemetry._logging = prev + on;
            console.log("[Telemetry] logging next " + Telemetry._logging +
                        " complete bodies — will auto-disable after");
            return;
        }
        Telemetry._logging = (typeof on === 'boolean') ? on : !Telemetry._logging;
        console.log("[Telemetry] logging " + (Telemetry._logging ? "on" : "off"));
    };

    /*
     * ----------------------------------------------------------------
     * Telemetry.stats(): {matched: number, blocked: number, logged: number}
     *
     * Read-only counts since power was loaded.
     *   matched — total filter hits (host suffix matched)
     *   blocked — subset where disable() was active at the time
     *   logged  — subset where log() was on at the time
     *
     * Result:
     *   Returns the counter object. Does not log.
     * ----------------------------------------------------------------
     */
    Telemetry.stats = function () {
        return {
            matched: Telemetry._stats.matched,
            blocked: Telemetry._stats.blocked,
            logged: Telemetry._stats.logged
        };
    };

    RW.registerMod("power:Telemetry", version);
    var logState = (typeof Telemetry._logging === "number")
        ? "next " + Telemetry._logging + " bodies"
        : (Telemetry._logging ? "on" : "off");
    console.log("[Telemetry] " + version + " loaded — hook armed, default state: " +
                (Telemetry._disabled ? "disabled" : "enabled") +
                ", logging " + logState +
                ". Try: Telemetry.disable()");
})();

// Top-level alias for REPL convenience
var Telemetry = RW.Telemetry;
