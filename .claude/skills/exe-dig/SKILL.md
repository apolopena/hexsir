---
name: exe-dig
description: Use when the user says "fire up Ghidra", "hack the exe", "get digging", "boot Ghidra", "exe-dig", or otherwise asks to start a Ravensmith RE session. Verifies Ghidra is running with the Ravensmith project before the Claude session began (so `mcp__ghidra__*` tools auto-registered), and primes the RE-mode rules from CLAUDE.md.
---

# exe-dig

Confirms the GhidraMCP HTTP server is live and the native `mcp__ghidra__*` tools are usable in this Claude session, then primes RE-mode rules. **Does not launch Ghidra.** Tool discovery happens once at Claude session startup; if Ghidra wasn't running then, the native tools won't be registered, and HTTP JSON-RPC fallbacks are too slow to be worth using.

## Prerequisites

Before invoking this skill, the user must have:

1. **Ghidra running with the Ravensmith project loaded in CodeBrowser** (program: `Ravensmith.exe`). The GhidraMCP plugin must be enabled — verify by `curl http://127.0.0.1:8080/mcp` returning any HTTP code.
2. **A Claude Code session that was started AFTER Ghidra came up.** Tool discovery is one-shot at session init. If Ghidra came up after the session started, the `mcp__ghidra__*` tools won't be registered and can't be reached efficiently.

## Procedure

1. **Probe MCP.**

   ```bash
   curl -sS -m 3 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/mcp
   ```

   - HTTP code present (e.g. `400`) → MCP up. Proceed to step 2.
   - `curl` exits non-zero with "Could not connect" → MCP down. Skip to **"Recovery: MCP not running"** below.

2. **Confirm `mcp__ghidra__*` tools are reachable.** Schemas may load lazily via ToolSearch — that's expected. You don't need to pre-fetch all of them; load on first use.

   - If ToolSearch returns matches → tools auto-registered at session init. Native calls will work. Proceed to step 3.
   - If ToolSearch returns no matches → MCP is up *now* but wasn't up at session start, so Claude didn't discover the tools. Skip to **"Recovery: tools not registered"** below.

3. **Prime RE-mode rules.** Briefly tell the user the session is hot and state the rules you'll follow. From CLAUDE.md:

   - **Annotate findings on the spot.** When a function / struct / global's purpose becomes clear (even partially), name/type/comment it in Ghidra immediately via `mcp__ghidra__*`. Do not batch at session end.
   - **Symbol identity vs narrative split.** Names, types, struct definitions, enums → Ghidra. Context, hypotheses, repro steps, dead-end notes → `rw/findings/*.md`.
   - **Findings flow.** New decode work goes into `rw/findings/<slug>.md` with `**Status:** in-progress`; promote to `confirmed` only after independent verification.
   - **Quit Ghidra by closing the Project Manager window.** Leave CodeBrowser open at exit. Ghidra saves running-tool state on this clean shutdown path; that's what the next launch restores.

## Recovery: MCP not running

Ghidra isn't up yet, or the GhidraMCP plugin isn't bound. Tell the user:

> Start Ghidra with the Ravensmith project loaded in CodeBrowser, then either start a fresh Claude Code session or use `/mcp` in this session to refresh server discovery, then re-run `/exe-dig`. I won't launch Ghidra from inside the skill — tool discovery only happens once at session startup, and an MCP server that comes up afterward can only be reached via slow HTTP JSON-RPC fallbacks.

Then stop. Do not attempt to launch Ghidra programmatically. Do not fall back to HTTP JSON-RPC.

If the user reports CodeBrowser doesn't auto-load the program when Ghidra opens (only Project Manager appears), the previous session's tool state wasn't saved cleanly. Tell them: open `Ravensmith.exe` manually inside Ghidra to launch CodeBrowser, then close Ghidra by closing the Project Manager window. After that one clean cycle, subsequent launches will auto-load.

## Recovery: tools not registered

MCP is reachable but `mcp__ghidra__*` tools aren't surfaced via ToolSearch. This means Ghidra came up *after* the Claude Code session started. Tell the user:

> The Ghidra MCP server is running but Claude didn't discover its tools at session start. Either run `/mcp` to refresh server discovery, or start a fresh Claude Code session, then re-run `/exe-dig`. I'd rather not use the HTTP JSON-RPC fallback — it works but every tool call is a slow curl with manual session-ID management; native MCP tools are far faster.

Then stop.

## Constraints

- Do NOT launch Ghidra programmatically (no `os.startfile`, no `cmd.exe /c start`, no `Start-Process`). The user must launch it externally before the Claude session starts.
- Do NOT force-kill Ghidra (no `Stop-Process -Force`, no `taskkill /F`). Force-quits skip the state-save and break auto-load for the next session — the user then has to do a manual one-clean-cycle recovery before this skill works again. If Ghidra appears stuck, ask the user to close it via Project Manager.
- Do NOT also start the WinDbg MCP. CLAUDE.md requires asking the user before initiating a live debugging session.
- Do NOT touch savefiles, run mints, or modify game state as part of this skill. RE-only.
- Do NOT fall back to HTTP JSON-RPC against the MCP server when native tools aren't registered. Instruct the user to refresh MCP discovery (or restart the Claude session) instead — efficient native tools are worth the restart.
