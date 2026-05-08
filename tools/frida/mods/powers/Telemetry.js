// Telemetry.js — block outbound telemetry calls at the WinHTTP layer.
//
// Hooks winhttp!WinHttpSendRequest with a host-suffix filter. Matched hosts
// (passtechgames.com, nacon-os.com, submit.backtrace.io, *.run.app) return
// BOOL FALSE without making the call: no socket, no DNS, no TLS handshake.
//
// Companion to tools/telemetry-warden/. The warden blocks at the network
// layer (hosts file → 127.0.0.1 listener); this power kills the call inside
// the process before WinHTTP even starts. With Telemetry.disable() active,
// the warden has nothing to log either — the dt-live retry storm goes silent.
//
// REPL surface (after loadPower("Telemetry")):
//   Telemetry.disable(): void              install hook + block matched calls
//   Telemetry.enable(): void               stop blocking; matched calls pass through
//   Telemetry.stats(): {matched, blocked}  read-only counters since load
//
// Per rw/findings/telemetry-surface-and-warden.md.

(function () {
    var version = "0.2.0";

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
    if (!winhttp || !queryOptionAddr) {
        console.log("[Telemetry] FATAL: WinHttpSendRequest / WinHttpQueryOption not exported by winhttp.dll");
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
    Telemetry._installed = Telemetry._installed || false;
    Telemetry._stats = Telemetry._stats || { matched: 0, blocked: 0 };

    // Re-load safety: revert prior replacement before re-installing.
    if (Telemetry._installed) {
        try { Interceptor.revert(winhttp); } catch (e) {}
        Telemetry._installed = false;
    }

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

    // BOOL WinHttpSendRequest(HINTERNET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, DWORD_PTR)
    var winhttpArgTypes = ["pointer", "pointer", "uint32", "pointer", "uint32", "uint32", "pointer"];
    var origSendRequest = new NativeFunction(winhttp, "int", winhttpArgTypes);

    Interceptor.replace(winhttp, new NativeCallback(
        function (hRequest, lpszHeaders, dwHeadersLength, lpOptional,
                  dwOptionalLength, dwTotalLength, dwContext) {
            try {
                var host = urlHost(getRequestUrl(hRequest));
                if (hostMatches(host)) {
                    Telemetry._stats.matched++;
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
     * Telemetry.stats(): {matched: number, blocked: number}
     *
     * Read-only counts since power was loaded.
     *   matched — total filter hits (host suffix matched)
     *   blocked — subset where disable() was active at the time
     *
     * Result:
     *   Returns the counter object. Does not log.
     * ----------------------------------------------------------------
     */
    Telemetry.stats = function () {
        return {
            matched: Telemetry._stats.matched,
            blocked: Telemetry._stats.blocked
        };
    };

    RW.registerMod("power:Telemetry", version);
    console.log("[Telemetry] " + version + " loaded — hook armed, default state: " +
                (Telemetry._disabled ? "disabled" : "enabled") +
                ". Try: Telemetry.disable()");
})();

// Top-level alias for REPL convenience
var Telemetry = RW.Telemetry;
