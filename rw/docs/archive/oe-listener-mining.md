> **ARCHIVED 2026-04-27** — the trainer-edit use case for live-memory work is
> tabled. This doc is preserved as a methodology playbook (heap-scan technique,
> RTTI walk, mirror-cascade analysis, listener-instance pinning) for the future
> read-only monitoring track when per-session ASLR re-discovery is built.
> For current canonical save-format state and the live-memory tabled-status
> summary, see [`rw/key-findings/save-binary-format.md`](../../key-findings/save-binary-format.md).

# OEngine listener-data mining — techniques

The Ravenswatch / OEngine binary stores observable game-state values as
instances of `oe::DynamicCpntValueListenerData<T>` (one instance per consumer:
UI, save serializer, replication). Mining a stat means: identify which
instances bind to the stat you care about, and read or modify the value at
offset `+8` from the instance base.

This doc is the working playbook for that work. Cross-reference:
- `rw/key-findings/archive/oe-dynamic-listener-data.md` — vtable map for all `<T>` specializations
- `rw/triage/level-runtime-address.md` — first end-to-end walk-through of these techniques
- `rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_analysis.md` — session 1 results
- `rw/docs/tools/mem-snapshot.md` — `mem_snapshot.py` command reference

## What survives a restart, what doesn't

Critical to understand before reading specific addresses anywhere in this
project: **specific runtime addresses are ephemeral**. Each Ravenswatch launch
loads the EXE at a different ASLR slide, and heap allocations land at
different VAs. The address `0x27cdcfe8660` (Level mirror in session 1) will
be a different number tomorrow.

What stays stable across launches:

| Stable | Source |
|--------|--------|
| Vtable RVAs (file-relative offsets) | `Ravenswatch.exe` PE layout — see RVA table in `key-findings/archive/oe-dynamic-listener-data.md` |
| Class identity & layout (vtable at +0, value at +8) | RTTI in the binary |
| Architecture pattern (which stats are listeners, which are plain fields, which are computed) | Same — engine design |
| Relative offsets within the player stat block (e.g., HP current is 0x1E0 bytes after Level) | EXE structure — stable until the binary changes |

What changes every launch:

- Module load addresses (Ravenswatch.exe base + every DLL).
- Therefore: runtime vtable addresses (`base + RVA`).
- Therefore: every heap address recorded in this project's session docs.

Stable across game updates only as long as the source code doesn't change.
Major patches will likely shift RVAs and may add / remove fields. The
architecture pattern (listener wrappers + plain fields + computed values)
should remain.

## Per-session workflow (find a known stat in a fresh launch)

For any stat we've already pinned (e.g., Level, HP, dream shards), recovering
its current address is mechanical — no re-investigation:

1. **Get the module base.** With Ravenswatch running:

       mem_snapshot.py modules

   Read off the `base` for `Ravenswatch.exe`.

2. **Compute the runtime vtable address.** From the RVA table in
   `key-findings/archive/oe-dynamic-listener-data.md`, pick the `<T>` for the stat
   (e.g., `<int>` RVA `0xef4ad0` for Level). Runtime addr = `module_base + RVA`.

3. **Take 1–2 snaps and scan for vtable instances.** Use the listener instance
   heap-scan technique (technique 10 below). Each match is a candidate
   listener with the value at `+8`.

4. **Pin the specific stat among the candidates.**
   - If the stat changes by a known delta (level-up, etc.), capture two snaps
     across the change and filter by progression.
   - If the stat doesn't change easily, use struct-relative offset from
     another known anchor (e.g., Level's address) — these offsets are stable
     across launches.

This is ~5 minutes per session once tooled, not a re-investigation. The
end-to-end multi-snap pipeline (techniques 1–4 below) is the *first-time*
discovery flow; the workflow above is the *re-locate-in-a-fresh-session*
flow.

## What this work enables

- **Trainer development.** Attach to a live process, run the per-session
  workflow, poke values. The pipeline is now a known recipe.
- **Save-format ↔ runtime correlation.** Save offsets (documented in
  `triage/geppetto-save-analysis.md` and elsewhere) can now be matched to
  runtime listeners — useful for predicting which save edits take effect
  and which UI displays come from listener vs. computed.
- **Cross-character generalization.** Vtables are global; only heap
  addresses differ per character/run. Same recipe applies to Aurora,
  Ratbo, etc.
- **Cross-game generalization.** Other OEngine titles (other Passtech games)
  likely use the same listener pattern. RVAs differ per binary; the
  architecture transfers.

## Pipeline overview

```
in-process snaps  →  diff  →  intersect  →  byte-progression filter  →  candidates
                                                                          │
                                                                          ▼
                                            chapter-transition verification
                                                                          │
                                                                          ▼
                                              vtable identification (RTTI walk)
                                                                          │
                                                                          ▼
                                            full listener census (vtable scan)
                                                                          │
                                                                          ▼
                                             stat-pin via HUD progression match
```

Each stage filters / disambiguates the previous one. Together they go from a
raw 5 GB heap dump to a small list of listener addresses pinned to specific
game stats.

## Techniques in use

### 1. Within-process snap capture (sidesteps ASLR)

**Problem:** Ravenswatch requires a process restart between save loads. Every
launch has a different ASLR slide, so two `.snap` files from different
launches cannot be cross-referenced by virtual address — the same heap object
will be at different VAs in each.

**Solution:** capture all snaps inside ONE running process. In-game state
changes (e.g., level-ups via XP) trigger the value updates we want to observe;
no restart needed.

**Implementation:** `mem_snapshot.py grab <label>` per snap. First `grab` is
auto-marked baseline; later grabs auto-diff against it.

### 2. Auto-diff against fixed baseline

Each `grab` after the baseline writes `diff_<label>.txt` listing every byte
address that differs from the baseline. Diffs share an address space (same
process), so they can be intersected as raw sets without ASLR adjustment.

### 3. `find-progression` byte-filter

`mem_snapshot.py find-progression --progression a,b,c,d,e` does:
1. Read all selected diff files (or all `diff_*.txt` if no `--snap` filter).
2. Compute the set intersection — addresses that changed in EVERY diff.
3. For each intersection address, read one byte from each snap (sequential
   region walk; no quadratic loop).
4. Keep only addresses where the byte progression matches `a,b,c,d,e`.

For a Level test from L1 to L5 the target is `1,2,3,4,5`. The byte filter is
robust to int8 / int16 / int32 storage of small integers (low byte = value).

This typically narrows millions of intersect addresses to ~10 candidates.

### 4. Chapter-transition verification

A `grab` taken after a chapter load (without further levelling) gives a
"same-value, different memory layout" data point. Reading each candidate
against this snap with `mem_snapshot.py read <addr> --snap <ch2-snap>`
classifies them:

- Same value as before chapter load → keep (real listener, persists).
- Different value → drop (coincidental match, in churning memory).
- Address unmapped → drop (region freed at chapter load).

Useful because chapter loads reshuffle ~50% of memory regions in this engine.

### 5. Struct context probe

For a candidate listener instance, read N bytes around it (`bytes_at_sorted`
helper) and tile-interpret as int32 / float32 / int64 / pointer. Reveals:
- The vtable pointer at offset 0 (object identity).
- The held value at offset 8.
- Adjacent listener instances if any (e.g., other stats in the same allocation).

Pointer classification helps: addresses in `0x7ff6_xxxxxxxx` range are EXE /
DLL pointers (likely vtables); addresses in `0x000001_xxxx_xxxx` to
`0x000003_xxxx_xxxx` are heap pointers.

### 6. PE header parsing

For static analysis of the EXE we parse the PE / COFF / Optional headers
manually (no `pefile` dependency):

- DOS header at file offset `0x3C` → 4-byte LE PE pointer.
- COFF header at `pe_off + 4`: `Machine (H), NumSections (H), TimeDate (I),
  SymPtr (I), NumSyms (I), OptHdrSize (H), Chars (H)`.
- Optional header (PE32+): `ImageBase` at `opt_off + 24` (8 bytes),
  `SizeOfImage` at `opt_off + 56` (4 bytes).
- Section table immediately follows the optional header. Each entry: 8-byte
  name, then `VSize (I), VAddr (I), RawSize (I), RawOff (I), …`.

### 7. Vtable runtime → file offset mapping

Given a runtime vtable address (e.g., from a snap):
1. Get the running module's load base via
   `mem_snapshot.py modules --contains <addr>` (uses pymem to enumerate the
   process's loaded modules).
2. Compute `RVA = runtime_addr − module_base`.
3. Find the section containing that RVA (typically `.rdata` for vtables).
4. Compute file offset: `section.RawOff + (RVA − section.VAddr)`.

Function pointers stored in vtables on disk are `0x140000000 + func_RVA` (the
preferred ImageBase). The runtime fixes them up via the relocation table.

### 8. MSVC RTTI walk (vtable → class name)

MSVC-compiled binaries with RTTI emit a Complete Object Locator pointer at
`vtable - 8`. From there:

- COL fields (4-byte each, as RVAs): `signature, offset, cdOffset,
  pTypeDescriptor, pClassDescriptor, pSelf`.
- `pTypeDescriptor` → TypeDescriptor: `vtable* (8), spare* (8), name (null-term
  ASCII)`. The mangled name string starts at `td_file + 16`.
- `pClassDescriptor` → ClassHierarchyDescriptor → array of BaseClassDescriptors.
  Each BCD's `pTypeDescriptor` resolves the same way; gives the inheritance
  chain.

MSVC mangled names start with `.?A` followed by type-kind code (`V` for class,
`U` for struct), template-class marker `?$` if templated, the class name,
`@` separator, template arguments (each prefixed by `@`), and `@@` terminator.
Common template arg codes: `H`=int, `M`=float, `_N`=bool, `D`=char, `I`=uint,
`N`=double, `J`=long, `K`=ulong, `V…@@`=class type.

### 9. Template specialization enumeration

For a templated class like `oe::DynamicCpntValueListenerData<T>`, find all `T`
specializations:

1. Search the EXE for the byte pattern of the mangled-name prefix
   (`.?AV?$DynamicCpntValueListenerData@`). Each occurrence is a TypeDescriptor's
   name field.
2. For each match, the TypeDescriptor starts 16 bytes earlier; parse its name
   string to get the `T` arg.
3. Walk forward to find each TypeDescriptor's COL: search `.rdata` for any
   4-byte value equal to the TD's RVA at the COL `pTypeDescriptor` offset
   (col_start + 12). Validate by checking `signature == 1` and self-pointing
   `pSelf` field.
4. From each COL, find the corresponding vtable: search `.rdata` for the 8-byte
   `0x140000000 + COL_RVA` pattern; the byte 8 after each match is the start
   of the vtable that uses this COL.

This recovered all 10 `<T>` specializations in `Ravenswatch.exe`.

### 10. Listener instance heap scan

For a known specialization vtable, scan a snap for instances:
- Pack the runtime vtable address as 8 bytes LE.
- Walk every region in the snap; use `bytes.find()` to locate every occurrence
  of those 8 bytes.
- Each match is the start of an instance (the vtable pointer at object offset
  0). Read the value at `+8` to get the observed `T` value.

A typical run yields 14K–140K instances per vtable.

### 11. Per-instance progression classification

Run technique 10 against each of N captured snaps. Build per-snap
`{addr: value}` dicts; intersect addresses common to all snaps; for each
common address build the N-tuple of values. Classify each tuple:
- Constant (caps / config / base stats)
- Strictly +1 per step (Level mirrors)
- Strictly increasing, other rates (XP threshold etc.)
- Non-monotonic (combat / inventory / RNG)

### 12. Stat-pin via HUD progression match

For a stat with known L1..LN values from the HUD, filter the per-instance
progression dict for tuples matching the exact target sequence. Typically
returns 1–10 matches; the "primary" instance is the one inside the player's
main stat-listener cluster (the heap range where Level mirrors live).

## Methodology correction (verified 2026-04-26)

**Live verification revised the assumption that any listener instance is
the live source-of-truth.** Testing confirmed that the listener instances
pinned via this workflow are not live game state — they don't update when
gameplay events change the HUD value, and external writes to them don't
propagate to the live game. What they ARE beyond "not live" is undetermined
(save-buffers, allocation-time defaults, dead-code subsystem fields, etc.
are all consistent with the observations); see
`rw/triage/pin-identity-uncertain.md` for the open hypothesis list and
`rw/key-findings/archive/oe-dynamic-listener-data.md` (Status section) for the
full test record.

This invalidates the "source-of-truth" framing throughout this doc. The
specific consequences for the techniques below are noted inline.

The methodology blind spot is **stable-across-snaps filtering**: the
workflow selects for listeners whose values match the L1..L5 progression
at every snap moment, which is consistent with values committed at a
sparse-event tempo and held in between. A live-updating listener holding
mid-combat values at any non-checkpoint sampling moment would never match
the progression. The filter systematically excludes the live source-of-truth.

Additional finding from the same session: value-progression scanning for
*live* mirrors (i.e., addresses that DO track HUD changes) finds many
mirror copies of the canonical value, not the canonical itself. Writes to
the mirrors are either silently overwritten by the engine (active
high-frequency mirrors) or persisted-but-ignored by the read path (passive
event-mirrors). The canonical source for any stat we tested has not been
located via memory-only techniques. See
`rw/triage/live-state-mirror-cascade.md` for the cascade observations and
the failed canonical-source hunts.

## Techniques planned (next steps)

### Cluster-range filtering for multi-match stats

Many stats have common values (e.g., crit damage = 50% has 70 matches; "all
zero" has 37K). Narrow by accepting only candidates inside the player's main
stat-listener cluster (e.g., `~0x27cdcfd0000–0x27cdcffffff` in session 1).

**Note (2026-04-26):** the resulting "primary" candidate is a *save-side
mirror*, not the source-of-truth. The cluster filter is still useful for
disambiguating among listener instances tied to one stat, but live state
lives elsewhere.

### Other listener vtables for missing stats

Stats not findable in `<int>` or `<float>` listeners can live elsewhere:
- **Plain struct fields** (not wrapped in a listener) — found stars-of-fate
  this way at `0x27cdcfe87f8`. Use technique 13 (raw heap progression) to
  pin them.
- **Computed-on-demand** (no storage at all) — damage falls in this bucket;
  computed each frame as `base + Σ(item_modifiers)`. Confirmed via raw heap
  scan returning zero matches for the displayed progression.
- **Other listener vtables** (`<oCColor>`, `<oCTypedPtr>`, etc.) — repeat
  techniques 10–12 for each. Less likely for primitive stats.

### 13. Raw heap progression scan (non-listener)

For stats with a known HUD progression that aren't wrapped in any listener:

1. Pick the snap with the rarest target value (largest absolute nonzero;
   zero last). This is critical for memory safety — scanning for `int32==0`
   can yield tens of millions of matches.
2. Scan that snap for all 4-byte-aligned positions where `int32` (or
   `float32`) equals the target. Returns a list (not a set) of candidate
   addresses.
3. For each remaining snap (any order, but cheapest snaps with high-value
   targets first), use a sorted region walk (`int32s_at_sorted` /
   `float32s_at_sorted`) to read the value at each candidate address;
   filter to those matching the target for that snap.
4. Final survivors are stable plain-int / plain-float fields with the exact
   progression. The "primary" candidate is the one inside the player main
   stat block; others are typically copies or coincidences.

Memory cost: bounded by the size of the initial candidate list (~10K-200K
entries × 8 bytes/entry). Speed: ~30-60s per snap walk for verification.

### Source-of-truth identification (INVALIDATED for these listeners)

> **Status (2026-04-26):** this technique was tested against the pinned Level
> listener (`0x27cdcfe8668` +8) using `rs write`. Writing 6 and then 10 had
> no in-game effect — the HUD continued to show Level 5 throughout. The
> technique presupposes that some listener instance is the source-of-truth
> whose writes propagate to UI / other mirrors. That presupposition is
> false for these pinned listeners — they're decoupled from the live
> read path. (Their further identity is undetermined; see
> `rw/triage/pin-identity-uncertain.md`.)
>
> The valid version of this technique would be: write to a candidate, then
> watch the *out-of-band live HUD value* (or a verified-live listener if
> one is found via value-progression scanning) and check for propagation.
> The mirror-to-mirror propagation check has no signal because none of the
> pinned listeners are live consumers.

Original (kept for context): for a stat with multiple listener mirrors, write
a non-canonical value into one and observe (a) whether the in-game UI
updates, (b) which other mirrors update or stay. The mirror that updates
the others is the source.

Requires runtime memory write — now available via `rs write` (one-shot CLI
against the rs-shim). The earlier `mem_snapshot.py poke` extension is
unnecessary.

### Cross-character generalization

Vtables (RVAs) are stable across launches and characters; addresses are not.
For each new character/run, re-acquire the module base, compute runtime
vtable addresses, and re-scan. The stat-listener cluster will be at a
different absolute address but should match the same offset-from-vtable
pattern.

### Vtable function disassembly

For deeper class introspection (e.g., to find which method is the constructor
vs. destructor vs. getter / setter), disassemble the vtable's function entries.
Currently we read only the first function's bytes and scan for LEA RIP-rel
references to identify string usage. A proper disassembler (capstone, distorm,
or shipping a one-off binary distil step with `objdump -d`) would be more
robust.

### Save-format ↔ runtime binding

Several save fields have known offsets and GUIDs (see `rw/triage/geppetto-save-analysis.md`).
For runtime values now identified (Level, XP threshold, etc.), we can correlate:
- Save offset → save value
- Runtime listener → runtime value

Once correlated, we can predict which save edits will and won't take effect at
runtime, and identify which UI display values are computed-from-save vs.
held-in-listener.

## Tooling status

`mem_snapshot.py` subcommands as of this writing:
- `grab` — capture process memory
- `intersect` — intersect diffs (legacy, slow on within-process scale)
- `find-progression` — efficient byte-progression filter
- `read` — single-address read across one or more snaps
- `modules` — list loaded modules / locate an address
- `grab-noisy`, `intersect-noisy` — noise-floor handling (unused for the
  in-process flow but kept)

Not yet in the tool, used as one-shot Python via `bytes_at_sorted` helper:
- Listener vtable scan (technique 10)
- Per-instance progression classification (technique 11)
- Stat-pin filter (technique 12)

These should be promoted to subcommands when the patterns stabilize. Likely
names:
- `scan-vtable --vtable <addr> --type {int,float,bool,...} --snap-dir <dir>`
- `progression --vtable <addr> --type ... --snap-dir <dir>` (multi-snap)
- `pin --progression a,b,c,d,e --vtable <addr> --type ... --snap-dir <dir>`
