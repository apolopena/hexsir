[← Back to workflow](README.md)

# WinDbg

Live-process debugging of the running game. WinDbg attaches to `Ravenswatch.exe` Windows-side via a WinDbg MCP server registered in `.mcp.json`; when running, tools appear under `mcp__windbg__*`. Setup (server install, port discovery, WSL networking) lives in [`../ghidra-windbg-mcp-for-wsl.md`](../ghidra-windbg-mcp-for-wsl.md); this chapter covers what to do once it's attached.

## What this is for

WinDbg is the heavyweight live debugger. Hardware data breakpoints on writes to a single qword. Single-stepping into a virtual call to discover the concrete callee. Inspecting the full call stack at a specific instant. The classic use case in this project is **finding the writer of a field that nothing in the static graph appears to write** — the chapter-end serializer doesn't reach `*(data_source + 0x1958)` through any visible static path because the writes are vtable-dispatched. A hardware breakpoint on `[data_source+0x1958]` catches the first writer red-handed during a real chapter-end run.

## Concepts

### Ask before attaching

Like Ghidra, WinDbg is offered, not assumed. Attaching pauses the running game; missteps can crash it. The tools also aren't always loaded — if `mcp__windbg__*` doesn't appear, the server isn't up. Ask the user to start the server (or confirm authorization to attach) before initiating a debugging session.

### Hardware vs software breakpoints

- **Software breakpoints** rewrite an instruction byte to `0xCC`. Fine for break-on-execute. They cost an instruction-stream patch and can interact poorly with code that checksums itself.
- **Hardware data breakpoints** use the CPU's `DR0`-`DR3` debug registers to break on memory access (read, write, or read/write) at a specific address. There are only four of them, but they're invisible to the running code and are the only way to catch a write that comes through an unknown dispatch path.

In this project, hardware data breakpoints are the workhorse. Attach, set the breakpoint, let the game run; the debugger pops when the address is touched, and the call stack tells you what wrote it.

### Live process state vs static state

The image base is ASLR-randomized per launch. RVAs from Ghidra (e.g. `+0x6797b0` for `save_request_sync`) only resolve once you've identified the live image base. WinDbg's `lm` (list modules) gives the base; everything from there is `image_base + RVA`.

## Recipes

### Attach after boss-kill

The single most important recipe in this chapter.

1. Begin a chapter-2 (or later) run in-game. Reach the boss arena.
2. Kill the boss. **Do not yet click "save and exit."** The post-kill animation window is roughly 5-15 seconds.
3. During the animation, attach WinDbg to `Ravenswatch.exe` from the Windows side.
4. Set hardware data breakpoint on the field of interest (e.g. `ba w8 <addr>` for an 8-byte write).
5. Resume execution. Click through the save dialog in-game.
6. WinDbg breaks on the write. Inspect call stack with `kb`.

The "attach after boss-kill" timing is non-negotiable — see [Gotchas → boss-spawn / boss-kill anti-debug tripwire](#boss-spawn--boss-kill-anti-debug-tripwire).

### Set a hardware data breakpoint on a heap field

Heap addresses are per-launch. Use Frida to discover the live address first (e.g. `globalThis.find()` in `save_now.js` returns the `oCDtRootGs` instance pointer), then in WinDbg:

```
ba w8 <runtime_addr>      :: break on 8-byte write to that address
g                         :: continue
:: <breakpoint hits>
kb                        :: print call stack with first 3 args
.frame <N>                :: switch to frame N
dv                        :: dump locals at that frame
```

`ba w4` for a 4-byte write, `ba r1` for a single-byte read, etc.

### Find the chapter-end save buffer writer

The chapter-end serialization calls `oCMemoryBinaryStream::Write` (image+0x5257d0) many times to fill the save buffer. The buffer pointer at `data_source+0x1958` (= `job+0x30`) is NULL at construction and gets its first non-NULL value on the first Write. Catching that first write reveals the chapter-end SerializeArchive entry point.

```
:: 1) attach AFTER boss-kill (see "Attach after boss-kill")
:: 2) find data_source via Frida globalThis.find() before attaching
:: 3) set breakpoint on the buffer pointer:
ba w8 <data_source+0x1958>
g
:: <breaks on first Write>
kb 30
```

The call stack tells you which function called Write and from where. Walk up the stack to find the chapter-end serialization entry point.

### Inspect a struct in memory

```
dq <addr> L8        :: 8 qwords starting at addr
dd <addr> L10       :: 16 dwords
db <addr> L40       :: 64 bytes (hex + ASCII)
dt <type> <addr>    :: dump as named type (if symbols available)
```

### Single-step into a virtual call

When a function dispatches `(*(code **)(*plVar7 + 0x40))(plVar7, ...)` and you want the concrete callee:

```
bp <call_site>      :: break at the call instruction
g                   :: run until break
t                   :: step into; lands in the concrete method
```

Once in the concrete method, the call-stack frame is now the resolved class — the answer Ghidra static analysis can't give you.

## Gotchas

### Boss-spawn / boss-kill anti-debug tripwire

Empirically confirmed 2026-04-29: WinDbg attached at boss-spawn or boss-kill triggers a process self-termination (anti-debug check). Frida is unaffected. WinDbg-based capture for the chapter-end chain only works when **attached AFTER boss-kill**, during the post-boss-die animation window. If you need to break on boss-spawn or boss-kill itself, use Frida hooks instead.

This is not optional advice — attaching during the wrong window kills the process and you lose the run.

### Image base is per-launch

Every static address you cite in this project is an RVA. When using WinDbg, find the live image base with `lm m Ravenswatch` and add it to the RVA before setting any address-based breakpoint. Old breakpoint addresses from a previous session won't work after a relaunch.

### Hardware breakpoint slots are scarce

Four debug registers. If multiple hardware breakpoints are set and the next one fails, you've hit the limit. `bl` lists active breakpoints; `bc *` clears all.

### Process state is fragile during attach

Breaking on a hot function (one that fires during normal idle) can leave the game in a state it doesn't recover from when you `g` resume — UI animations skip, audio glitches, or worse. Prefer breakpoints on cold or once-per-event paths. For hot paths, prefer Frida.

### Call-stack symbols may be partial

Without PDB symbols, WinDbg shows raw addresses for most frames — `kb` gives `Ravenswatch+0x4f2d45` rather than function names. Resolve the offsets manually against the Ghidra project: `Ravenswatch+0x4f2d45` is `image_base + 0x4f2d45`, look up that RVA in Ghidra to get the function name.

## Pointers

- **Setup:** [`../ghidra-windbg-mcp-for-wsl.md`](../ghidra-windbg-mcp-for-wsl.md) — WinDbg MCP install, WSL routing, port discovery.
- **Findings:** [`save-subsystem.md`](../../findings/save-subsystem.md) "Empirical: WinDbg anti-debug behavior" section, [`frida-pipeline-hardware-breakpoint.md`](../../findings/frida-pipeline-hardware-breakpoint.md) (the open hardware-breakpoint task on `data_source+0x1958`).
- **Sibling chapters:** [`ghidra.md`](ghidra.md), [`frida.md`](frida.md).
- **Vocabulary:** [`../terminology/README.md`](../terminology/README.md).
