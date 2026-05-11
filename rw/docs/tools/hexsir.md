[← Back to tools](README.md)

# hexsir — Binary Checksum Probe

## Overview

`hexsir` probes binary files for checksums and patterns. It includes checksum analysis (CRC32, Adler-32, sum32, XOR32), pattern searching, and file mutation utilities for reverse engineering binary formats.

Use cases:
- Reverse engineering binary file formats with embedded checksums
- Validating checksum locations in firmware or data files
- Scanning for checksum patterns when the format is unknown
- Searching for text keys or delimiters in binary data
- Creating test files with known checksums

## Prerequisites

```bash
cd tools/hexsir-src && uv venv && uv sync --group dev
```

## Command Groups

### checksum

Analyze files for common 4-byte checksums.

### probe

Search for patterns in binary files.

## Commands

### `hexsir checksum basic`

Check the whole file with no header offset. Tests whether a 4-byte checksum exists at the beginning or end of the file.

```bash
./tools/hexsir checksum basic firmware.bin
```

### `hexsir checksum header`

Check a single header offset. Skips the specified number of bytes, then checks for checksums at the beginning or end of the remaining data.

```bash
./tools/hexsir checksum header firmware.bin --offset 16
```

**Options:**
- `--offset BYTES` — skip this many bytes from the beginning (required)

### `hexsir checksum scan`

Scan multiple header offsets. Iterates through a range of offsets to find where a checksum might be located.

```bash
# Default: scan offsets 0, 4, 8, ... 64
./tools/hexsir checksum scan firmware.bin

# Custom range
./tools/hexsir checksum scan firmware.bin --start 0 --stop 128 --step 8
```

**Options:**
- `--start OFFSET` — starting offset (default: 0)
- `--stop OFFSET` — ending offset (default: 64)
- `--step BYTES` — increment between offsets (default: 4)

### `hexsir checksum verify`

Validate a suspected checksum location by mutation. Flips one byte in the body and confirms the checksum changes as expected. This proves the checksum actually covers that region.

```bash
./tools/hexsir checksum verify firmware.bin --offset 12
```

**Options:**
- `--offset BYTES` — byte offset where 4-byte checksum is located (default: 12)

### `hexsir probe key`

Search for a text key in a binary file. Tests both ASCII and UTF-16LE encodings.

```bash
./tools/hexsir probe key "password" --file firmware.bin
```

**Arguments:**
- `KEY` — text string to search for

**Options:**
- `--file FILE` — binary file to search (or set `HEXSIR_FILE` env var)

### `hexsir probe delimiter`

Find delimiter patterns at a specific offset. Useful for finding key-value separators after locating a key.

```bash
./tools/hexsir probe delimiter --file firmware.bin --after 0x100 --encoding ascii
```

**Options:**
- `--file FILE` — binary file to search (or set `HEXSIR_FILE` env var)
- `--after OFFSET` — offset to search after (required)
- `--encoding` — text encoding: `ascii` or `utf16le` (required)

### `hexsir mint`

Create a mutated copy of a file with a recalculated valid checksum. Flips one byte in the body, computes the new CRC32, and writes it. The resulting file will pass checksum validation despite being modified.

```bash
./tools/hexsir mint --file input.bin --checksum-offset 12
```

**Options:**
- `--file FILE` — input binary file (or set `HEXSIR_FILE` env var)
- `--output, -o FILE` — output file path (default: `<input>.mint.<ext>`)
- `--checksum-offset OFFSET` — byte offset of 4-byte CRC32 checksum (required)

**Output:**
```
✓ Minted file created.
=== Mint ===
mutated_byte: byte 16: 0x4A → 0x4B
checksum    : 0x0DE35DF2 → 0xFA5F7F91
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `HEXSIR_FILE` | Default file path when `--file` not provided |

## Algorithms

| Algorithm | Description |
|-----------|-------------|
| CRC32 | Standard CRC-32 (zlib) |
| Adler-32 | Adler-32 checksum (zlib) |
| sum32 | Simple byte sum, masked to 32 bits |
| XOR32 | XOR of all bytes, masked to 32 bits |

Each algorithm is tested against the suspected checksum bytes in both little-endian and big-endian byte order.

## Output

For each region analyzed, hexsir prints:
- The stored bytes at the suspected checksum location
- The stored value interpreted as little-endian and big-endian
- Each algorithm's computed value and whether it matches either endianness

Matches are highlighted with a success indicator. A summary at the end lists all matches found.

## Tests

```bash
just tool-test hexsir
```
