[← Back to workflow](README.md)

# Ghidra

Static decompilation discipline for Ravenswatch RE. The game's `Ravenswatch.exe` is loaded in a Ghidra project on the user's Windows side, exposed to Claude Code via the `mcp__ghidra__*` MCP tools. Setup (WSL networking, MCP install, port discovery) lives in [`../ghidra-windbg-mcp-for-wsl.md`](../ghidra-windbg-mcp-for-wsl.md); this chapter covers what to do once the project is reachable.

## What this is for

Ghidra is the static-analysis backbone. The save-subsystem mapping, the talent / item / hero record formats, the chapter-end save call topology — every confirmed finding in this repo started with somebody decompiling a function in Ghidra. The MCP tools let an agent decompile, rename symbols, define structs, and add equates from inside a working session, so the next time the same function shows up the call is more readable than `FUN_140291350(undefined8 param_1)`.

## Concepts

### Ask before digging

Decompile-on-demand is offered, not assumed. Some sessions are pure code work that doesn't need it; some are deep RE sessions where Ghidra is the right first step. Ask the user before initiating a Ghidra session, both because it affects the user's local Ghidra project state (annotations persist) and because it can be expensive in tool-call budget.

### Annotation-on-the-spot discipline

When you identify what something does — even partially — annotate it in Ghidra immediately. **Do not batch annotations at session end.** Each annotation makes future decompilation more readable for both you and the user, and prevents losing the identification when context drops. The bar is low: partial understanding is worth annotating. `unknown_serializer_at_this+0xc8` is more useful than `FUN_1403b3da0`.

### Symbol-level identity vs narrative context

Ghidra annotations are for **symbol-level identity** — names, types, structures. The "why" of a finding — the analysis chain, the experiments that led to the conclusion, the open questions — belongs in `rw/findings/*.md`, not in Ghidra plate or EOL comments. The two artifacts complement each other: Ghidra makes the next decompile readable, the finding tells the next reader what's been figured out and why.

### When to reach for Ghidra vs Frida vs WinDbg

- **Ghidra (static)** — first stop for "what does this function do?" questions, mapping call topology, identifying vtables and RTTI, recovering struct layouts. No live process needed; doesn't disturb game state.
- **Frida (live, non-intrusive)** — when you need runtime values, hooks for measurement, or to drive code paths from outside without a debugger. Doesn't pause the process.
- **WinDbg (live, intrusive)** — when you need to break on a specific instruction, single-step, watch a memory address with hardware breakpoints, or inspect the call stack at a specific instant. Pauses the process.

Most workflows start in Ghidra to identify candidate functions and addresses, then move to Frida or WinDbg to observe the candidates running.

## Recipes

### Annotation kinds and the tool to use

- **Functions** — rename via `mcp__ghidra__rename_symbol` (target_type=function) or `mcp__ghidra__batch_rename`. Convention: snake_case for free functions, `Class_method` or `Class::Method` for members, `Class_vftable` for vtables.
- **Data / globals** — rename via `mcp__ghidra__rename_symbol` (target_type=data). Used for vftables, RTTI, string tables, registries.
- **Function parameters and local variables** — rename via `mcp__ghidra__rename_symbol` (target_type=variable) inside a decoded function. Replace `param_1` with `this` / `stream` / `hero_state`, `local_88` with `count_delta`, `uVar3` with `ingredient_index`.
- **Struct definitions** — when a class layout is understood, define the struct via `mcp__ghidra__struct` (action=create). Once defined, accesses like `*(int *)(this + 0x08)` auto-render as `this->type_id` everywhere the type is applied.
- **Equates / enums** for magic constants — `0xAABB1111` → `MARK_START`, schema-version IDs, ingredient class IDs. Use `mcp__ghidra__types` (action=create_enum).

### A typical mapping pass

1. Decompile the candidate function with `mcp__ghidra__analyze_function` or `mcp__ghidra__get_code`.
2. As soon as you can guess the function's purpose, rename it via `mcp__ghidra__rename_symbol`. Don't wait until you understand it fully.
3. Replace `param_1` and any obvious locals with meaningful names — `this`, `stream`, `count_delta`, `record_off`. Each rename ripples through the decompile output.
4. If the function references a struct field by offset (`*(int*)(this + 0x40)`), and you understand that field, use `mcp__ghidra__struct` to define the struct so the access auto-renders.
5. If the function checks a magic constant (`0xAABB1111`, `0xAABB2222`), define an enum via `mcp__ghidra__types` so the constant renders by name.
6. Document the function's purpose in the relevant `rw/findings/<topic>.md`. The doc is the narrative; Ghidra is the symbol identity.

### Finding xrefs

`mcp__ghidra__xrefs` for any symbol — function, data, vtable. Indispensable for locating where a class is constructed, where a vftable address is stored, where a global is read.

### Searching for symbols and patterns

- `mcp__ghidra__search_functions_by_name` — locate by name fragment.
- `mcp__ghidra__search_strings` — find ASCII / UTF-16 string references in the image.
- `mcp__ghidra__search_bytes` — byte-pattern search across the image.
- `mcp__ghidra__get_strings` — list all strings in a region.

### When to define a struct

The bar: at least three accesses through different offsets of the same `this` are documented in findings or visible in decompile. At that point a struct definition makes every future decompile of any function that touches the type more readable. Below the bar, freeform comments suffice.

## Gotchas

### Annotations are local to the user's Ghidra project

The MCP tools mutate the user's local Ghidra project state. Renames persist across sessions for the user, but they don't propagate to other contributors automatically. In practice this is the whole codebase's RE state for this project — the user is sole maintainer — so persistence is a feature, not a problem. But it means: be careful with destructive renames, don't trample existing names without checking what they currently are.

### Vtable dispatches don't appear in xref graphs

Static xref searches won't find calls made through `vtable[N]` because Ghidra doesn't know which concrete class a `this` pointer belongs to at decompile time. If a hot call path goes through a vtable slot, finding all callers requires either dynamic instrumentation (Frida hook on the slot) or a hardware breakpoint (WinDbg). The recurring example is `oCMemoryBinaryStream::Write` — every chapter-end serializer dispatches through it, but the static graph shows zero direct callers.

### Decompile cost

Decompilation is not free. `mcp__ghidra__analyze_function` on a large function (thousands of lines of C output) consumes significant tool-call budget and context tokens. For broad surveys, prefer `get_function_signature` or `get_function_statistics` first; reserve full decompile for the small set of candidates that survive triage.

## Pointers

- **Setup:** [`../ghidra-windbg-mcp-for-wsl.md`](../ghidra-windbg-mcp-for-wsl.md) — WSL networking, MCP install, port routing.
- **Findings:** [`save-subsystem.md`](../../findings/save-subsystem.md) (call-topology master), [`save-flow-diagrams.md`](../../findings/save-flow-diagrams.md), [`save-binary-format.md`](../../findings/save-binary-format.md), [`decoder-work-2026-04-30.md`](../../findings/decoder-work-2026-04-30.md), [`ghidra-rule-c-investigation.md`](../../findings/ghidra-rule-c-investigation.md).
- **Sibling chapters:** [`frida.md`](frida.md), [`windbg.md`](windbg.md).
- **Vocabulary:** [`../terminology/README.md`](../terminology/README.md).
