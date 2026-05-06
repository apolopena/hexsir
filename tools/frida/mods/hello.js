// POC test mod — proves cross-file scope works against rw_lab.js's globals.
// Edit `version`, save, run `loadMod("hello")` again at the REPL.

(function () {
    var version = "hello-3";
    console.log("[hello] " + version + " loaded");
    if (typeof RW !== "object" || typeof loadPower !== "function") {
        console.log("[hello] WARN: rw_lab.js globals not in scope — was it loaded first?");
        return;
    }
    RW.registerMod("hello", version);
    console.log("[hello] rw_lab globals reachable: " +
                "loadMod=" + typeof loadMod +
                ", loadPower=" + typeof loadPower +
                ", help=" + typeof help +
                ", RW.after=" + typeof (RW && RW.after));
    RW.helloLoadCount = (RW.helloLoadCount || 0) + 1;
    console.log("[hello] reload count = " + RW.helloLoadCount);
})();
