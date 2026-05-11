[← Back to findings](README.md)

# Save-record GUID hash-tail reversal

**Status:** in-progress
**Created:** 2026-04-27

## Sources

- rw/findings/save-chapter-counter.md
- rw/findings/geppetto-save-analysis.md
- rw/ref/tree-ciphered.txt
- rw/scripts/mod_save.py
- tools/rerw-src/lib/save_edit.py
- tools/rerw-src/data/save-fields.yaml

## Confirmed Findings

### GUID B for chapter is structured: ASCII path-fragment + 4 trailing bytes

GUID `6661756c746465662e6f7426ba4519` (15 bytes) decomposes as:

- Bytes 0–10 (11 bytes): ASCII `faultdef.ot&` — the tail of the asset filename `All_Chapters.gamemodedefaultdef.ot.GameModeDefaultDefinition.gen` (verified via `rerw decipher` against the ciphered tree at `rw/ref/tree-ciphered.txt`).
- Bytes 11–14 (4 bytes): `26 ba 45 19` — opaque, structurally separate from the ASCII prefix.

The ASCII prefix and the 4 trailing bytes together are exactly 15 bytes — the GUID width used by every save-record key observed so far.

### Other known save-record GUIDs (15 bytes each)

These all behave like keys in the GUID + value record format used by the save body. From `rw/scripts/mod_save.py` and `rw/findings/save-chapter-counter.md`:

| Field | GUID (hex) | Trailing 4 bytes | Visible ASCII prefix? |
|-------|-----------|------------------|-----------------------|
| Level | `b5317efe6f4a95737325675793e600` | `5793e600` | No |
| (unknown — was "ProfileDreamShards") | `b43eeb58d162fa41acef99d128f2cb` | `d128f2cb` | No |
| Chapter Counter A | `13fa8e2c314d88babb71a8e3c4df01` | `e3c4df01` | No |
| Chapter Counter B | `6661756c746465662e6f7426ba4519` | `26ba4519` | Yes (`faultdef.ot&`) |

The "trailing bytes" column is the interpretation if the GUID is `[ASCII prefix][4-byte tail]`. For GUIDs without a visible ASCII prefix, the segmentation is unverified — they could be entirely opaque, or the prefix could be a different encoding (compressed string, hashed name, type-id + payload, etc.).

## Unresolved

### Are the trailing bytes a deterministic hash of the asset path?

The leading hypothesis. If true, reversing the hash function lets us mint arbitrary save-record GUIDs from any asset path in `rw/ref/tree-deciphered.txt` — which is the plausible path to programmatic editing of currently-unmoddable in-run state (dream shards, stars of fate as item-count, inventory items, talents, abilities — all flagged as "not findable as int32+GUID" in `rw/findings/geppetto-save-analysis.md`).

Hypothesis space (none tested yet):

| Variable | Candidates |
|----------|-----------|
| Hash function | CRC32 (zlib), CRC32C, FNV-1a (32/64-bit), MurmurHash3 (32/64-bit), xxHash, FxHash, custom Passtech |
| Input domain | full asset path, deciphered class name, raw ASCII basename, basename without extension, the visible ASCII prefix in the GUID itself |
| Byte order | LE or BE for the resulting hash |
| Tail width | 4 bytes (default reading), 3 bytes with a category/type byte preceding, or some other segmentation |

### Discriminating experiment

Cheap to run (single-session hash-trying):

1. Pick GUID B (`All_Chapters`) as the easiest case — visible ASCII prefix, deciphered asset path known.
2. For each (hash function × input domain × byte order) combination, compute the hash and check if it equals the trailing 4 bytes `26 ba 45 19`.
3. On hit, validate against the other three known GUIDs. Each needs the asset-path ↔ trailing-bytes pair: the unknown `b43eeb58...` field (formerly suspected ProfileDreamShards — identity disproven 2026-04-27, see `rw/findings/save-binary-format.md` § "Misidentified") needs an unknown asset-path candidate; Level keys on whatever the level-counter resource is named in the asset tree; Counter A keys on whatever pairs with Counter B in the chapter system (the asset tree may have a sibling file).
4. If no hit on any combination, the trailing bytes are likely not a hash. Move to the alternative track.

### Alternative track if reversal fails — interned/serial ID extraction

If the trailing bytes are an interned ID from a build-time registry (assigned when the asset was cooked, not derived from the path), the registry itself probably lives inside `Ravenswatch.exe` or a `.gen` artifact. Extraction would need:

- Static binary analysis (Ghidra / IDA / objdump on the EXE).
- Or runtime introspection: hook into the engine's resource-load path to capture the (asset-path → ID) mapping as resources stream in.

This is a different toolchain — out of scope for the hash-reversal track, but the right next step if reversal exhausts cleanly.

### GUIDs without ASCII prefixes

Three of the four known GUIDs (Level, the unknown `b43eeb58...`, Counter A) have no visible ASCII content. Possibilities:

- The full 15 bytes are a hash — different schema from GUID B.
- The full 15 bytes are an interned ID (different schema again).
- The "ASCII prefix" varies in width per GUID — short paths like `Level` (5 bytes) leave more room for hash, longer paths like `faultdef.ot&` leave less.
- The prefix uses a different encoding (e.g., the engine's filename cipher applied to a different domain) and isn't human-readable in raw hex.

The discriminating experiment above will narrow this if it lands a hit. If it doesn't, all three of these explanations remain in play.

### Width of the GUID record-key field

All four known GUIDs are exactly 15 bytes. Why 15 (an odd number for a binary protocol)? Hypotheses:

- The format is `[type tag: 1 byte][payload: 14 bytes]`. The hex prefixes (`b5`, `b4`, `13`, `66`) are wildly different so a single tag byte at position 0 isn't the answer. Could be at position 0–1 instead (16-bit type tag, 13-byte payload).
- The format is `[fixed prefix][asset reference][hash]` with variable widths.
- The 15-byte size is incidental — what matters is the type-registry segment at `0x00–0x700` of the save (per `rw/findings/geppetto-save-analysis.md`), which is undecoded but probably defines record schemas including key widths.

Decoding the type registry would resolve this and may be a prerequisite to confidently parsing GUIDs in general. The user has flagged that segment as "the schema you haven't decoded" — relevant to this triage's outcome regardless of whether the hash track lands.

## Notes

- The hash-track experiment is genuinely cheap. A few hours of trying combinations is the right scope for a single discriminating session — not a multi-session investment.
- A negative result (no hash function matches) is just as informative as a positive one. It rules out the leading hypothesis and points squarely at the registry-extraction track.
- The chapter-counter primitive in `rw/findings/save-chapter-counter.md` is unaffected by this triage either way — `data.find(guid)` is the runtime mechanism, and that works regardless of how the GUIDs were originally generated. The hash-tail question only matters when we want to *generate new GUIDs*, not when we want to *find and edit existing ones*.
- Cross-reference with `rw/findings/geppetto-save-analysis.md` § "Future Work": item 3 ("Reverse engineer the ability system") and item 5 ("Look for array structures (length + item GUIDs pattern)") both depend on this triage's outcome. If hashes reverse cleanly, those tracks become unblockable; if not, both tracks need the registry-extraction layer first.
