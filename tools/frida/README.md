# Frida save tools

Frida scripts that drive Ravenswatch's save subsystem from outside the game. No build step — Python + JavaScript only.

## What's here

| Script | Purpose |
|---|---|
| `find_data_source.js` | Verify-only. Finds the heap-allocated `oCDtRootGs` instance and prints its address + key field values. Does NOT trigger a save. Use to confirm the scan works before committing to a save. |
| `save_now.js` | Finds `oCDtRootGs`, calls `save_request_sync(NULL, data_source + 0x1928)`, blocks until save completes, prints status. Updates `Profile_1.ob` on disk. |
| `rw_lab.js` | Live-patch lab. Hub for runtime patches and diagnostics. Currently: talent-picker seed forcing (`force(seed)`, `forceFresh(seed)`), picker count override (`pickerCount(n)`), pool/slot dumps, held-talent clearing. See header comment for the full REPL command list. |

`save_now.js` and `find_data_source.js` implement the recipe documented in `rw/findings/save-subsystem.md`.

## Setup (one-time, on Windows)

Frida runs on the Windows side (where Ravenswatch.exe lives).

### Prerequisites

You need Python 3.8+ on Windows. Check by running in PowerShell:

```powershell
python --version
```

If that prints `Python 3.x.x`, you're good. If not, install from [python.org](https://www.python.org/downloads/) with "Add Python to PATH" checked.

### Install Frida

Use this form — it works whether or not `pip` is in your PATH:

```powershell
python -m pip install frida-tools
```

If you get a permissions error, add `--user`:

```powershell
python -m pip install --user frida-tools
```

### Add Frida's Scripts directory to PATH

The `frida-tools` install lands `frida.exe` (and `frida-ps.exe`, etc.) in your Python user `Scripts` directory, which is **not on PATH by default**. You'll see this warning during install:

```
WARNING: The scripts frida-apk.exe, ..., frida.exe are installed in
'C:\Users\<USERNAME>\AppData\Local\Python\pythoncore-3.X-64\Scripts'
which is not on PATH.
```

That exact path is your Frida-Scripts directory — copy it from your install warning, or compute it from your Python version. The rest of this doc assumes `frida` is callable from any PowerShell window. Pick one of the three options below to make that true.

**Option A — Permanent user PATH (recommended).** Adds the Scripts directory to your User PATH for all future PowerShell windows. Run once, then close and re-open PowerShell:

```powershell
$scriptsDir = "C:\Users\<USERNAME>\AppData\Local\Python\pythoncore-3.X-64\Scripts"
[Environment]::SetEnvironmentVariable(
    "Path",
    $scriptsDir + ";" + [Environment]::GetEnvironmentVariable("Path", "User"),
    "User"
)
```

**Option B — Session-only PATH.** Adds the Scripts directory only for the current PowerShell window. Useful if you don't want to modify your User profile:

```powershell
$env:Path = "C:\Users\<USERNAME>\AppData\Local\Python\pythoncore-3.X-64\Scripts;" + $env:Path
```

**Option C — No PATH change, call by full path.** Always invoke `frida.exe` with its absolute path:

```powershell
C:\Users\<USERNAME>\AppData\Local\Python\pythoncore-3.X-64\Scripts\frida.exe ...
```

Verbose but works without modifying anything.

### Verify Frida is callable

After completing one of the options above:

```powershell
frida --version
```

Should print a version string like `17.9.3`. If it does, you're set.

> The rest of this doc assumes `frida` is on PATH. If you went with option C, substitute the full path each time `frida` appears below.

### Invoking from WSL instead of PowerShell

`frida.exe` is a Windows binary, but WSL interop lets you call it directly from a Linux shell via the `/mnt/c/` mount. No PATH change needed — point at the absolute Windows path.

Set a variable once per shell (or in `~/.bashrc` / `~/.zshrc`):

```bash
# Replace <USERNAME> and <PYVER> (e.g. 3.14) with your values.
export FRIDA="/mnt/c/Users/<USERNAME>/AppData/Local/Python/pythoncore-<PYVER>-64/Scripts/frida.exe"
```

Verify:

```bash
"$FRIDA" --version
```

Then invoke with WSL paths to the scripts — modern WSL auto-translates `/home/...` arguments when passed to a Windows binary:

```bash
"$FRIDA" -n Ravenswatch.exe -l /home/<USER>/repos/work/ravensmith/tools/frida/rw_lab.js
```

If a script path doesn't get picked up (older WSL, or the argument isn't recognized as a path), convert it explicitly with `wslpath -w`:

```bash
"$FRIDA" -n Ravenswatch.exe -l "$(wslpath -w /home/<USER>/repos/work/ravensmith/tools/frida/rw_lab.js)"
```

That produces a `\\wsl.localhost\<DISTRO>\home\...` path frida.exe can open unambiguously.

Caveats:

- Ravenswatch and frida.exe must be running on the Windows side. WSL is just driving the CLI.
- WSL must be alive for `\\wsl.localhost\` paths to resolve. After a reboot, run any `wsl` command (or just stay in your WSL shell) to keep it up.
- Stdin piping for the REPL works the same as PowerShell: `echo 'go()' | "$FRIDA" -n Ravenswatch.exe -l ...`.

### Where to find the scripts

The scripts live in this repo at `tools/frida/`. From a Windows shell, reference them via the WSL path:

```
\\wsl.localhost\<DISTRO>\home\<USER>\repos\work\ravensmith\tools\frida\<script>.js
```

Replace `<DISTRO>` with your WSL distro name (e.g. `Ubuntu`, `Debian`, `Void`) and `<USER>` with your Linux username. To find your distro name:

```powershell
wsl -l -v
```

The `\\wsl.localhost\` mount only resolves while WSL is running. WSL doesn't auto-start after a reboot — wake it up with:

```powershell
wsl ls /
```

(Run any `wsl` command; that's enough to spin it up. After that the UNC path works for the rest of the session.)

If the WSL path is awkward in your shell, copy the two `.js` files to a Windows folder of your choice and reference them from there:

```powershell
mkdir C:\rerw-frida -Force
copy \\wsl.localhost\<DISTRO>\home\<USER>\repos\work\ravensmith\tools\frida\*.js C:\rerw-frida\
```

Then use `C:\rerw-frida\<script>.js` in place of the WSL path. You'll need to re-copy if the scripts change.

## Usage

### Trigger a save

```powershell
echo 'go()' | frida -n Ravenswatch.exe -l \\wsl.localhost\<DISTRO>\home\<USER>\repos\work\ravensmith\tools\frida\save_now.js
```

(Type `exit` at the REPL prompt afterwards, or pipe both: `printf 'go()`n exit`n' | ...`.)

The script defines `go()` at load time (instant), then `go()` performs the scan and save (the scan takes ~60-90 seconds, the save takes <1 second). The function-call approach avoids Frida's 30-second script-load timeout.

Expected output:

```
[+] image_base = 0x...
[+] expected vtable[0] = 0x...
[+] save_request_sync   = 0x...
[+] finding vtable addresses in image...
[+]   2 aligned vtable address(es) found
[+]     vtable: 0x...
[+]     vtable: 0x...
[+] scanning heap for instances...
[+]   N rw- ranges to scan
[+]   found: 0x...  (NNN ms)
[+] selected: 0x...
[+] triggering save: save_request_sync(NULL, 0x...)
[+]   before: pend=N done=N
[+]   after:  pend=N+1 done=N+1 result=0 (took ~50-200 ms)
[+] SAVE COMPLETE.
```

After the script exits, check `Profile_1.ob` in `_Save\`:

```bash
ls -la /mnt/d/steam-storage/steamapps/common/Ravenswatch/_Save/Profile_1.ob
```

The mtime should be the current time and the size may have changed.

## When to run

The data source (`oCDtRootGs`) is heap-allocated when a profile loads. Run these scripts:

- ✅ While at the main menu after loading a profile (the data source should exist).
- ✅ During a run (in-game).
- ✅ At the end-of-chapter screen.
- ❌ NOT before the title screen finishes initializing — the type descriptor will be NULL and the scan will report "engine not yet initialized".

## What the scripts do not do

- They do not write the save file directly. They invoke the game's own `save_request_sync` function, which goes through the normal save subsystem (queue → worker thread → atomic write). The save bytes are exactly what the game would have written via the natural chapter-end trigger.
- They do not modify game state. Only reads (during scan) and one function call.
- They do not bypass any account/auth checks. There aren't any in the game's save path on PC — see `save-account-binding.md`.

## Troubleshooting

**"frida: error: process not found"**
- Ravenswatch isn't running, or the executable name differs (rare). Try `frida-ps` to list processes and find the actual name.

**"typedesc is null — engine not yet initialized"**
- You attached too early. Wait until the main menu has fully loaded, then re-run.

**"no oCDtRootGs instance found in heap"**
- No profile is loaded yet. Click "Continue" or load a save, then re-run.

**Scan takes more than 5 seconds**
- This shouldn't happen on a typical run. The heap is usually under 200MB and the scan completes in under 500ms. If it's much slower, the game may be in an unusual state — try re-running.

**Game crashes during scan**
- Extremely unlikely with the current filters (vtable must point inside the image, and vtable[0] is called inside try/catch). If it happens, capture the call stack and we can tighten the filters further. Report it as a triage entry in `rw/findings/`.

## Implementation notes

The signature scan keys off `g_oCDtRootGs_typedesc` (statically located at `image_base + 0x14475a0`). Every `oCDtRootGs` instance has `vtable[0]() → typedesc`. We scan committed read-write memory regions, filter candidates whose first qword points inside `Ravenswatch.exe`, and call `vtable[0](candidate)` to confirm the match.

Cross-session behavior: ASLR randomizes the image base, but RVAs from Ghidra are stable. The static offsets used (`0x14475a0`, `0x6797b0`, `0x1928`) work for the current Ravenswatch build. They may change with game patches — re-decode if a patch lands.
