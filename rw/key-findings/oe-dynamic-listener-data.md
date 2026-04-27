# OEngine: `oe::DynamicCpntValueListenerData<T>`

OEngine (Passtech Games' game engine; namespace `oe::`) wraps observable game
state values in a templated class `oe::DynamicCpntValueListenerData<T>`. Each
instance holds a current value of type `T` plus listener-callback infrastructure.
Multiple instances of the same specialization may exist concurrently.

Inheritance: `oe::DynamicCpntValueListenerData<T>` <- `oe::IDynamicValueListenerData<T>`.

## Status: pinned listeners are NOT live source-of-truth — identity otherwise uncertain

**Live verification (2026-04-26)** revised the original "source-of-truth"
framing. What was *verified* about the listener instances pinned in this
document:

| Test | Pin | Trigger | Pin response |
|------|-----|---------|--------------|
| HP-current read | `0x27cdcfe8848` (+8) | took damage in-game | stayed at 129.0 (5 polls over 1.5 s) |
| Level write-poke | `0x27cdcfe8668` (+8) | wrote 6, then 10 | HUD ignored; pin held the value, then restored cleanly |
| Level event-driven | `0x27cdcfe8668` (+8) | leveled up 5→6 in-game | stayed at 5 |
| XP current event-driven | `0x27cdcfefaf8` (+8) | leveled up 5→6 | stayed at 4583 |
| XP threshold event-driven | `0x27cdcfef378` (+8) | leveled up 5→6 (HUD threshold changed) | stayed at 5000 |
| Dream shards listener | `0x27cdcfdcd68` (+8) | spent 50 (HUD 91 → 41), regained 50 (41 → 91) | stayed at 91 throughout |
| Stars of Fate plain int32 | `0x27cdcfe87f8` | spent 1 (HUD 4 → 3) | stayed at 4 |

Bidirectional decoupling: live game events do not propagate into pins, AND
external writes to pins do not propagate to the live game.

### What this proves vs. what is interpretation

**Proven:** the pinned addresses are not the live source-of-truth for
their associated stats.

**Not proven:** what they *are*. Earlier writeups in this doc labeled them
"save-side mirrors" or "save-buffers" — that framing is one hypothesis
consistent with the observations, but multiple other hypotheses fit
equally well (allocation-time defaults that never refresh, dead-code
subsystem buffers, debug fields, etc.). The save-buffer hypothesis is
plausible but unverified. See `rw/triage/pin-identity-uncertain.md` for
the full hypothesis list and discriminating tests.

### Why the snap-progression methodology selected for these

The mining workflow filtered for listener instances whose values matched the
L1..L5 HUD progression *across all five level-up snaps*. "Stable across snap
moments" is consistent with values committed at a sparse-event tempo and
held in between. A live-updating listener holding mid-combat or mid-XP-tick
values would not have matched the progression. **The live source-of-truth
was systematically excluded by the filter.**

This much is supported by the observation. What that "sparse-event tempo"
actually corresponds to (save events, allocation events, level transitions
specifically, etc.) is not pinned down by the data we have.

### Implications

- **Save editor (status uncertain, untested):** *if* the pinned listeners
  are save-buffers in the "serializer reads from them" sense, writing to
  one before a chapter-end save *may* persist the modification to disk. *If*
  they are save-buffers in the "engine refreshes them at save event then
  serializes" sense, modifications would be overwritten by the refresh.
  *If* they are something else entirely (defaults, dead code, etc.), the
  question is moot. The round-trip test (write → finish chapter → save →
  reload → read) would discriminate the first two cases. As of session
  end the test is unrun and not currently planned — see triage.
- **Live trainer (not useful):** these pins do not surface real-time HP,
  Level, XP, etc. Reading them gives stale values; writing has no in-game
  effect. This finding is robust regardless of pin identity.

### Where the live state actually lives (resolved by domain knowledge)

Most stats are NOT stored as a single live value at all. The Ravenswatch
engine computes them per frame from `base + Σ(modifiers)`. Verified
2026-04-26 against armor: a `−5 → 1` transition (from a +6 consumable)
produced **zero** addresses anywhere in the player heap region that flipped
from `−5.0` to `1.0` as float32. Pre-scan returned 9 candidates within the
2 MB player struct region; all 9 still held `−5.0` after the HUD change. A
heap-wide intersection scan was attempted but the float32 `1.0` post-scan
returns enough matches to time out the shim — confirming `1.0` is too common
in heap to narrow further with this technique.

Conclusion: **the displayed total has no single storage location.** The
`base` and individual `modifiers` *are* stored, but as separate values
distributed through equipment / talent / character structs. Pinning a single
"live armor" address is structurally impossible.

#### Stored vs. computed — domain rule

Per gameplay knowledge (player-confirmed):

- **Stored** (single value, can be pinned and read live): **XP**, **Stars of
  Fate**, **Keys**, and their sibling counters. These are progression /
  currency counters that the engine increments directly rather than
  computing from inputs.
- **Computed-on-demand** (no stable single storage; reconstructed per frame):
  essentially every other stat — HP, armor, vitality, crit chance, crit
  damage, move speed, damage, attack speed, etc. The original doc identified
  damage as computed; the rule is much broader.

##### Base values for computed stats

Even within the computed-on-demand bucket, computation shape varies:

- **Armor: base = 0.** The displayed armor value is purely
  `Σ(modifiers)`. There is no "armor base" register — every component is a
  modifier. Verified 2026-04-26: scanning for the displayed value `−5.0`
  returned 15943 heap-wide matches and 9 player-region matches, but writing
  `−999.0` to all 9 player-region candidates simultaneously left the HUD
  unchanged at 1. Confirms the `−5` was already a computed total, not a
  stored base.
- **Damage: base = 0.** Same shape as armor — only modifiers.
- **HP: base ≠ 0** (per-character). HP base is the character's starting
  max-HP value (e.g., Geppetto's class default). Modifiers (vitality
  bonuses, item bonuses, level-up bonuses) sum on top. The base IS stored
  somewhere and is therefore findable via direct value scan IF you know
  the character's class default.

##### Implications for live trainer hunts

| Stat | Live trainer technique | Difficulty |
|------|------------------------|-----------|
| XP / Stars of Fate / Keys | The known pin at `0x27cdcfe87f8` is not the live source-of-truth (verified 2026-04-26: HUD spent 4→3, pin stayed at 4). Pin identity beyond "not live" is uncertain (see `rw/triage/pin-identity-uncertain.md`). Live source is upstream of the mirror cascade we observed for dream shards. | Hard (canonical source not yet located) |
| HP | Scan for character's HP base value, write to it; total updates as `base + Σ(modifiers)` | Moderate (need character base value) |
| Armor / Damage | Must find specific modifiers in the modifier list, OR hook the computation function | Hard (modifier list discovery) |
| Other stats with non-zero base (move speed, attack speed, etc.) | Same as HP — find class default base, write | Moderate |

Bases are stored as plain values (not listener-wrapped) and therefore
respond to writes instantly. Modifier lists are dynamic-allocated structures
whose layout we haven't reverse-engineered yet.

#### Mirror cascade — even stored stats hide their canonical source

**Verified 2026-04-26 against dream shards (with extension to Stars of
Fate).** Even in the "stored" bucket, value-progression scanning surfaces
a *cascade of mirrors*, not the canonical source. Tested against a
controlled 91 → 41 → 91 transition (50 shards spent on a consumable, then
50+ regained):

| Tier | Refresh cadence | Count | Test outcome |
|------|-----------------|------:|--------------|
| Listener pin (identity uncertain — see triage) | Apparently sparse / event-driven only | 1 (the documented pin at `0x27cdcfdcd60` +8) | Stayed at `91` through 91→41→91 — fully decoupled from live state |
| Passive event-mirrors | Once per state-change event | 22 | Tracked 91→41→91 perfectly; sentinel writes (`−999`) persisted indefinitely until next event |
| Active high-frequency mirrors | <50 ms refresh from upstream | 6 | Tracked 91→41→91; sentinel writes overwritten within ~25–50 ms |
| Canonical source | (unknown) | ?  | Not in any of the 28 mirrors above; HUD reads from here |

Discrimination test: writing `−999` to all 28 mirrors simultaneously did
not affect the HUD's displayed shards count. Within those 28, a follow-up
write to only the slowest of the 6 active mirrors did NOT propagate to the
other 5 — ruling out a tier-2 → tier-3 propagation chain inside the 28.
The canonical source is therefore upstream of *every* address we found via
value-progression scanning.

##### Why value-progression scanning misses the canonical source

The canonical source is most likely one of:

- A different data type (`int64`, packed struct, `__m128i`, etc.) — wouldn't
  match a `int32 == 91` needle.
- A computed value (e.g., `total_earned − total_spent`) where neither
  component equals `91` directly. Both components would update on shard
  events, but neither holds the displayed value.
- Stored in a memory region the int32 scan didn't reach (uncommitted at
  scan time, in a different allocator's heap, etc.).

##### Implications for memory-only modding

Direct write-to-memory cannot affect HUD-displayed live values without
locating the canonical source. Mirror writes are reverted within ms (active
mirrors) or persist but are ignored by the read path (passive mirrors).

Stars of Fate (a plain `int32`, not listener-wrapped) was tested directly
on 2026-04-26 — the pin at `0x27cdcfe87f8` did not move when the HUD
deducted a star. So the original hypothesis that "plain int32 fields are
live and listener fields are mirrors" is refuted. **All known pinned
addresses, regardless of whether they are listener-wrapped or plain, are
not the live source-of-truth.** Their further identity (save-buffers, dead
code, allocation defaults, etc.) remains undetermined — see
`rw/triage/pin-identity-uncertain.md`.

Memory-only modding likely requires code-side techniques to locate any
canonical source: function hooking on writes to known mirrors to identify
the upstream caller, or breakpoints on HUD-read code paths to identify
the source-of-truth address. Memory-only value-progression scanning, as
demonstrated this session, surfaces only mirrors.

This rule explains every negative result so far:

- HP-current pin doesn't move on damage events: HP is computed; the listener
  isn't on the live read/write path for HP. (Whether the listener is a
  save-buffer, allocation-time default, or something else is undetermined —
  see `rw/triage/pin-identity-uncertain.md`.)
- Level/XP pins don't move on level-up: same — pins are decoupled from the
  live update path.
- Armor live-hunt produced no flipping address: armor is computed.

#### Implications for the trainer

For live monitoring/manipulation:

- The only **direct** live targets are the few stored counters (XP, Stars of
  Fate, Keys). These are likely all plain `int32` fields in the player struct
  region (Stars of Fate confirmed plain `int32` at `0x27cdcfe87f8`).
- For computed stats, three options remain — none of them are simple:
  1. Patch base values and modifier lists (many addresses; modifier lists
     are dynamic-sized vectors).
  2. Hook the computation functions in `Ravenswatch.exe` code (real RE,
     function-level patching, not memory editing).
  3. Patch the UI display (purely cosmetic; doesn't affect gameplay).

For the save editor: the pinned listeners *might* be useful targets *if*
they are save-buffers in a "serializer reads them as-is" sense. Player has
flagged a competing hypothesis: the engine likely refreshes pins from
canonical at save-event start, then serializes — making external pre-save
modifications inert. Round-trip persistence test (write → save → reload →
read) still pending and unscheduled at session close. See
`rw/triage/pin-identity-uncertain.md`.

### Notes column corrections (apply to the tables below)

The "source-of-truth instances" claim in the `<float>` section is wrong.
Inside-heap-range and outside-heap-range listeners behave identically — both
are decoupled from the live read/write path. The heap-range heuristic is
not informative about liveness or about pin identity.

## Object layout (all `<T>` specializations)

    +0    vtable*       (specialization-specific)
    +8    T value       (the observed value)
    +16+  heap ptrs     (listener / binding internals)

The value field at `+8` is the practical anchor for memory analysis — read or
write it to interact with the observed state.

## Specializations found in `Ravenswatch.exe` (build of 2026-02-18)

All located via mangled-name search in `.data` and COL-walk in `.rdata`. Vtable
RVAs are stable across launches; runtime addresses shift per ASLR.

| `T` | Decoded | Vtable RVA |
|-----|---------|-----------|
| `H` | `int` | **`0xef4ad0`** |
| `M` | `float` | `0xef4cb0` |
| `_N` | `bool` | `0xefb1c0` |
| `VoCVec3` | `oCVec3` (3D vector) | `0xef9890` |
| `VoCVec2` | `oCVec2` (2D vector) | `0xefd270` |
| `V?$oCTStr@D` | `oCTStr<char>` (engine string) | `0xefb0e8` |
| `VoCColor` | `oCColor` | `0xefeb60` |
| `VoCTypedPtr` | `oCTypedPtr` | `0xefec98` |
| `AEBV?$oCTResourcePtr@VoCMaterial` | `const oCTResourcePtr<oCMaterial>&` | `0xefd260` |
| `AEBV?$oCTResourcePtr@VoCTexture` | `const oCTResourcePtr<oCTexture>&` | `0xeff1c8` |

### `<int>` specialization — observed bindings (Geppetto, session 1)

Population census across L1..L5 in-process snaps (14,121 instances stable
across all 5 snaps in the heap):

| Pattern | Count | Notes |
|---------|------:|-------|
| Strictly +1 per level (Level mirrors) | 5 | observe `Level` |
| Strictly increasing, other rates | 5 | XP threshold (1) + counter pairs |
| Constant across all 5 snaps | 11,186 | caps / config / base stats |
| Nonzero, non-monotonic changes | 2,925 | dynamic combat / inventory state |

Confirmed bindings (HUD-progression match against L1..L5 values):

| Stat | Listener address(es) | Notes |
|------|---------------------|-------|
| Level | `0x27cdcfe8660` + 4 mirrors | progression (1,2,3,4,5) |
| XP threshold (next level) | `0x27cdcfef370` | progression (400, 1100, 1800, 2500, 5000) |
| XP current | `0x27cdcfefaf0` | adjacent to threshold |
| Dream shards | `0x27cdcfdcd60` + 5 mirrors | tight cluster |

Counters observed but not yet identified: paired mirrors with progression
`(0,3,10,14,20)` and `(0,1,5,7,8)` — possibly skill / talent counters.

### `<float>` specialization — observed bindings

`<float>` listener total: ~140K stable instances (10× more than `<int>` —
floats dominate game-state storage because most stats participate in
arithmetic). 37,129 are all-zero (matches stats genuinely zero this run, e.g.,
vitality, armor).

Confirmed bindings:

| Stat | Listener address(es) | Notes |
|------|---------------------|-------|
| Health current | `0x27cdcfe8840` | unique match; progression (80,108,97,106,117) |
| Health max | `0x27cdcfe8890` (+27 in others) | 50 bytes after health_current; same struct |
| Crit chance | `0x27cdcfd91b0` + 4 mirrors | percent (5.0/9.0), NOT fraction (0.05/0.09) |

The "player main stat block" lives in heap range `~0x27cdcfd0000–0x27cdcffffff`
(~2 MB region). Listener addresses inside this range cluster near other
player-state fields (Stars of Fate at `0x27cdcfe87f8` is in this region as a
plain `int32`).

**Correction (verified 2026-04-26):** the earlier claim that inside-range
listeners are source-of-truth and outside-range are mirrors is **wrong**.
Both inside-range and outside-range listeners are not the live
source-of-truth — neither holds the value the HUD reads at runtime. Their
further identity (save-buffers, allocation defaults, dead-code subsystem
fields, etc.) is undetermined. See the *Status* section at the top of
this doc and `rw/triage/pin-identity-uncertain.md` for the open
hypotheses.

Stats not findable as a listener instance:
- **Damage / armor / HP / most stats** — not stored as a single stable value
  anywhere in heap with the expected progression. Computed at display time
  as `base + Σ(item_modifiers)`. The original RE pass found this for damage
  via raw heap scan; the live verification pass (2026-04-26) extended the
  rule to armor by failing to find any address that flipped from `−5.0` to
  `1.0` after a +6 armor consumable. Per domain knowledge, the rule is
  general: only the progression / currency counters (XP, Stars of Fate,
  Keys, sibling counters) have stable single-value storage; everything else
  is reconstructed per frame.
- **Stars of fate** — found as a **plain int32** in the player struct at
  `0x27cdcfe87f8`, NOT wrapped in a listener. Originally hypothesized to be
  the live source-of-truth on the assumption that "plain field = live."
  **Verified 2026-04-26 to also not be live:** HUD spent 4 → 3, the pin
  stayed at 4. The "plain int32" / "listener-wrapped" distinction does not
  predict liveness — both kinds of pin are decoupled from the live read
  path. What the plain `int32` pin actually *is* (save-buffer, allocation
  default, etc.) is the same open question as for the listener pins; see
  `rw/triage/pin-identity-uncertain.md`. Player has confirmed similar
  behaviour for other "static" stats like Raven's Feathers, suggesting
  this decoupling pattern is general across all stored counters, not just
  listener-wrapped ones.

## Locating an instance at runtime

ASLR changes runtime addresses every launch — the RVAs above are stable, the
absolute addresses are not. To find a stat's current address in a fresh
session:

1. Get the EXE module's runtime base (e.g., via `mem_snapshot.py modules`).
2. Compute `vtable_runtime = module_base + vtable_RVA` for the desired `T`.
3. Scan heap regions of the snap for 8-byte LE values equal to
   `vtable_runtime`. Each match is the start of an instance.
4. Read the value at instance + 8 (size depends on `T` — int is 4 bytes, vec3
   is 12 bytes, etc.).
5. To pin which instance binds to which stat: either filter by
   value-progression across multiple snaps (level-up, take damage, etc.) or
   use struct-relative offsets from another known anchor.

Full per-session workflow & rationale (what survives a restart, what
doesn't): `rw/docs/oe-listener-mining.md`.

## Method to recover this map

- MSVC RTTI is intact in the binary (not stripped).
- Type descriptor names (mangled, with prefix `.?AV?$DynamicCpntValueListenerData@`)
  live in `.data`. Each `TypeDescriptor` struct is `[vtable* (8)] [spare (8)]
  [name (null-term)]`, so the name string starts 16 bytes into the struct.
- For each type descriptor, search `.rdata` for a Complete Object Locator
  (COL) whose `pTypeDescriptor` field (offset 12, 4-byte RVA) matches —
  validate by checking signature == 1 and self-pointing `pSelf` field.
- Each COL's address (as image-base + RVA, 8 bytes LE) appears as the value
  immediately before its associated vtable. So search `.rdata` for that
  8-byte value to find the vtable's location.

## Sources

- rw/triage/level-runtime-address.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_level_analysis.md
- rw/saves/edits/golden/geppetto/chapter2/laser-lenses_1/session1_struct_probe.txt
