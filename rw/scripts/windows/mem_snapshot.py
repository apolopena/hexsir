r"""Memory snapshot capture and diff for Ravenswatch RE.

Captures full writable memory of a running process, auto-diffs each capture
against a baseline, and intersects diffs across multiple comparisons to isolate
signal from noise.

Requires:
    pip install pymem
    Windows. Run as administrator (OpenProcess needs debug privileges).

Workflow. The first `grab` in an empty directory becomes the baseline (tracked
via a `.baseline` marker file). Every subsequent `grab` captures and writes a
diff against that baseline.

    py mem_snapshot.py grab clean --out-dir C:\ravensmith\snaps
    # → clean.snap, marked baseline

    py mem_snapshot.py grab level5 --out-dir C:\ravensmith\snaps
    # → level5.snap + diff_level5.txt

    py mem_snapshot.py grab level8 --out-dir C:\ravensmith\snaps
    # → level8.snap + diff_level8.txt

    py mem_snapshot.py grab --out-dir C:\ravensmith\snaps
    # → grab001.snap + diff_grab001.txt   (no label = next sequential)

    py mem_snapshot.py intersect --out-dir C:\ravensmith\snaps
    # writes C:\ravensmith\snaps\intersect.txt — addresses that changed in
    # every diff, annotated with int32 / float32 values from the most-recent
    # snap.

To filter out background drift (allocator / timers / RNG), take one or more
noise readings with `grab-noisy`. Each writes a numbered `diff_noise_NNN.txt`.
`intersect` automatically detects them, intersects them into a noise floor,
and subtracts the floor from the main intersection:

    py mem_snapshot.py grab-noisy --out-dir C:\ravensmith\snaps
    # → diff_noise_001.txt (two captures back-to-back, snaps discarded)

Files are NEVER overwritten. To redo a capture, delete the .snap (and its
`diff_<label>.txt` if it exists) and run `grab` again with the same label.

Captures cover all committed, writable memory — heap (MEM_PRIVATE), writable
globals in EXE/DLLs (MEM_IMAGE), and writable mapped memory (MEM_MAPPED).
"""

import argparse
import ctypes
import re
import struct
import sys
from ctypes import wintypes
from pathlib import Path

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000
WRITABLE_MASK = 0x04 | 0x08 | 0x40 | 0x80  # RW, WC, ERW, EWC

TYPE_NAMES = {MEM_PRIVATE: "PRIVATE", MEM_MAPPED: "MAPPED", MEM_IMAGE: "IMAGE"}

DIFF_RE = re.compile(r"^diff_(.+)\.txt$")
NOISE_DIFF_RE = re.compile(r"^diff_noise_(\d+)\.txt$")
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
GRAB_PREFIX = "grab"
GRAB_PADDING = 3
GRAB_SEQ_RE = re.compile(rf"^{GRAB_PREFIX}(\d+)$")
NOISE_PADDING = 3
NOISE_TMP_A = ".noise_tmp_a.snap"
NOISE_TMP_B = ".noise_tmp_b.snap"
BASELINE_MARKER = ".baseline"
INTERSECT_NAME = "intersect.txt"
INTERSECT_NOISY_NAME = "intersect-noisy.txt"
RESERVED_LABELS = {"intersect"}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def enumerate_regions(handle):
    """Yield (base, size, mem_type) for committed writable regions."""
    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    while address < 0x7FFFFFFFFFFF:
        rc = ctypes.windll.kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(address),
            ctypes.byref(mbi), ctypes.sizeof(mbi),
        )
        if rc == 0:
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if mbi.State == MEM_COMMIT and (mbi.Protect & WRITABLE_MASK):
            yield base, size, mbi.Type
        address = base + size


def capture_to(out_path, process):
    """Snapshot the writable memory of process to out_path. Print stats."""
    import pymem
    pm = pymem.Pymem(process)
    regions = list(enumerate_regions(pm.process_handle))
    n = len(regions)
    print(f"Capturing {n} regions to {out_path} ...", flush=True)

    by_type = {}
    skipped = 0
    total = 0
    with out_path.open("wb") as f:
        f.write(struct.pack("<Q", n))
        for i, (base, size, mem_type) in enumerate(regions, 1):
            try:
                data = pm.read_bytes(base, size)
            except Exception:
                f.write(struct.pack("<QQ", base, 0))
                skipped += 1
                continue
            f.write(struct.pack("<QQ", base, size))
            f.write(data)
            total += size
            by_type[mem_type] = by_type.get(mem_type, 0) + size

            if i % 50 == 0 or i == n:
                pct = i * 100 // n
                sys.stdout.write(
                    f"\r  {i:>5}/{n} regions  {total:>15,} bytes  ({pct:>3}%) "
                )
                sys.stdout.flush()
    sys.stdout.write("\n")

    breakdown = " ".join(f"{TYPE_NAMES.get(t, hex(t))}={n_bytes:,}"
                         for t, n_bytes in sorted(by_type.items()))
    print(f"{out_path}: {n} regions, {total:,} bytes "
          f"({skipped} skipped) [{breakdown}]")


def load_snapshot(path, progress_label=None):
    """Yield (base, data) for each region. If progress_label, show a counter."""
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for i in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            data = f.read(size)
            if progress_label and (i % 50 == 0 or i == n - 1):
                sys.stdout.write(
                    f"\r  {progress_label}: {i+1:>5}/{n} regions "
                    f"({(i+1)*100//n:>3}%) "
                )
                sys.stdout.flush()
            yield base, data
        if progress_label:
            sys.stdout.write("\n")


def changed_addrs(a_path, b_path):
    """Return set of byte addresses whose value differs between a and b.

    Prints per-region progress for the two loads and the comparison.
    """
    addrs = set()
    print(f"  loading {a_path.name}", flush=True)
    a = dict(load_snapshot(a_path, progress_label=a_path.name))
    print(f"  loading {b_path.name}", flush=True)
    b = dict(load_snapshot(b_path, progress_label=b_path.name))

    common = sorted(set(a) & set(b))
    total = len(common)
    print(f"  comparing {total} regions", flush=True)
    for i, base in enumerate(common, 1):
        da, db = a[base], b[base]
        if len(da) == len(db):
            for j in range(len(da)):
                if da[j] != db[j]:
                    addrs.add(base + j)
        if i % 50 == 0 or i == total:
            sys.stdout.write(
                f"\r  comparing: {i:>5}/{total} regions "
                f"({i*100//total:>3}%) "
            )
            sys.stdout.flush()
    sys.stdout.write("\n")
    return addrs


def next_grab_label(out_dir):
    """Find the next free `grabNNN` label by scanning existing snaps."""
    used = set()
    for p in out_dir.glob("*.snap"):
        m = GRAB_SEQ_RE.match(p.stem)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"{GRAB_PREFIX}{n:0{GRAB_PADDING}d}"


def next_noise_diff_path(out_dir):
    """Find the next free `diff_noise_NNN.txt` path."""
    used = set()
    for p in out_dir.glob("diff_noise_*.txt"):
        m = NOISE_DIFF_RE.match(p.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return out_dir / f"diff_noise_{n:0{NOISE_PADDING}d}.txt"


def validate_label(label):
    if not LABEL_RE.match(label):
        raise ValueError(f"Invalid label: {label!r}. "
                         "Use letters, digits, '_' or '-'.")
    if label in RESERVED_LABELS:
        raise ValueError(f"Label {label!r} is reserved.")
    if label.startswith("noise"):
        raise ValueError(f"Label {label!r} is reserved (use grab-noisy "
                         "for noise capture).")
    return label


def write_addrs(path, addrs):
    with path.open("w") as f:
        for a in sorted(addrs):
            f.write(f"{a:#018x}\n")


def read_addrs(path, progress=False):
    """Load the address set from a diff file. Shows byte-pct progress when
    progress=True (useful for the multi-hundred-MB noise diffs)."""
    out = set()
    size = path.stat().st_size if progress else 0
    bytes_read = 0
    with path.open() as f:
        for i, line in enumerate(f):
            bytes_read += len(line)
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.add(int(stripped, 16))
            if progress and size and (i & 0x3FFFF) == 0:  # every ~262k lines
                pct = (bytes_read * 100) // size
                sys.stdout.write(
                    f"\r  reading {path.name}: {pct:>3}% "
                )
                sys.stdout.flush()
    if progress:
        sys.stdout.write(
            f"\r  reading {path.name}: 100% ({len(out):,} addrs) \n"
        )
        sys.stdout.flush()
    return out


def values_at(snap_path, addrs, progress=False):
    """For each addr in the set, look up the 4 bytes starting there in snap.
    Shows per-region progress when progress=True."""
    targets = set(addrs)
    out = {}
    with open(snap_path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for i in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            data = f.read(size)
            if not size:
                continue
            end = base + size
            for a in targets:
                if base <= a and a + 4 <= end:
                    out[a] = data[a - base:a - base + 4]
            if progress and (i % 50 == 0 or i == n - 1):
                sys.stdout.write(
                    f"\r  reading values from {snap_path.name}: "
                    f"{i+1:>5}/{n} regions ({(i+1)*100//n:>3}%) "
                )
                sys.stdout.flush()
        if progress:
            sys.stdout.write("\n")
    return out


def cmd_grab(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.label is None:
        label = next_grab_label(out_dir)
    else:
        try:
            label = validate_label(args.label)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    snap_path = out_dir / f"{label}.snap"
    if snap_path.exists():
        print(f"{snap_path} already exists — refusing to overwrite. "
              f"Delete it first to redo.", file=sys.stderr)
        sys.exit(1)

    capture_to(snap_path, args.process)

    baseline_marker = out_dir / BASELINE_MARKER
    if not baseline_marker.exists():
        baseline_marker.write_text(snap_path.name)
        print(f"  baseline set: {snap_path.name}")
        return

    baseline_name = baseline_marker.read_text().strip()
    baseline_snap = out_dir / baseline_name
    if not baseline_snap.exists():
        print(f"Baseline snap missing: {baseline_snap}. "
              f"Delete {BASELINE_MARKER} to start over.", file=sys.stderr)
        sys.exit(1)

    addrs = changed_addrs(baseline_snap, snap_path)
    diff_path = out_dir / f"diff_{label}.txt"
    write_addrs(diff_path, addrs)
    print(f"{diff_path}: {len(addrs):,} bytes differ from {baseline_name}")


def _main_diffs(out_dir):
    """List main (non-noise) diff files in out_dir, sorted."""
    return sorted(
        p for p in out_dir.iterdir()
        if DIFF_RE.match(p.name) and not NOISE_DIFF_RE.match(p.name)
    )


def _noise_diffs(out_dir):
    """List noise diff files in out_dir, sorted."""
    return sorted(p for p in out_dir.iterdir() if NOISE_DIFF_RE.match(p.name))


def _last_non_baseline_snap(out_dir):
    """Return the most-recently-modified snap that isn't the baseline."""
    baseline_marker = out_dir / BASELINE_MARKER
    baseline_name = (
        baseline_marker.read_text().strip() if baseline_marker.exists() else ""
    )
    snaps = [p for p in out_dir.glob("*.snap") if p.name != baseline_name]
    snaps.sort(key=lambda p: p.stat().st_mtime)
    return snaps[-1] if snaps else None


def _write_intersect(out_path, addrs, value_snap, header_summary):
    """Write the intersect output file with int32 / float32 / hex value cols."""
    if value_snap and value_snap.exists():
        print(f"Reading values from {value_snap.name}...", flush=True)
        vals = values_at(value_snap, addrs, progress=True)
    else:
        vals = {}
    print(f"Writing {out_path.name}...", flush=True)
    with out_path.open("w") as f:
        f.write(f"# {header_summary}\n")
        if value_snap:
            f.write(f"# values from {value_snap.name}; addr  int32_le  float32  hex\n")
        else:
            f.write("# no snap available for value display\n")
        prev = None
        for a in sorted(addrs):
            run_marker = " " if (prev is not None and a == prev + 1) else "*"
            v = vals.get(a)
            if v:
                i32 = struct.unpack("<i", v)[0]
                f32 = struct.unpack("<f", v)[0]
                f.write(f"{run_marker} {a:#018x}  {i32:>11d}  {f32: .4e}  {v.hex()}\n")
            else:
                f.write(f"{run_marker} {a:#018x}  (no value — out of captured regions)\n")
            prev = a


def cmd_intersect(args):
    out_dir = Path(args.out_dir)
    diffs = _main_diffs(out_dir)
    if len(diffs) < 2:
        print(f"Need at least 2 main diff files in {out_dir} (found {len(diffs)}).",
              file=sys.stderr)
        sys.exit(1)

    intersect_out = out_dir / (args.out or INTERSECT_NAME)
    if intersect_out.exists():
        print(f"{intersect_out} already exists — refusing to overwrite. "
              f"Pass --out <name> or delete the file.", file=sys.stderr)
        sys.exit(1)

    log = []
    print(f"Reading {len(diffs)} main diffs...", flush=True)
    inter = None
    for d in diffs:
        s = read_addrs(d, progress=True)
        inter = s if inter is None else (inter & s)
        log.append(f"{d.name}: {len(s):,} addrs")
    summary = f"intersection: {len(inter):,} addrs across {len(diffs)} diffs"
    print(summary)
    log.append(summary)

    last_snap = _last_non_baseline_snap(out_dir)
    _write_intersect(
        intersect_out, inter, last_snap,
        f"{len(inter)} addresses changed in all {len(diffs)} diffs",
    )
    console_out = intersect_out.with_name(intersect_out.stem + "_console.txt")
    console_out.write_text("\n".join(log) + "\n")
    print(f"wrote {intersect_out}  (lines starting with * are run starts)")
    print(f"wrote {console_out}")


def cmd_grab_noisy(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    diff_path = next_noise_diff_path(out_dir)
    tmp_a = out_dir / NOISE_TMP_A
    tmp_b = out_dir / NOISE_TMP_B

    # Pre-clean any leftover temp files from a previous interrupted run.
    for tmp in (tmp_a, tmp_b):
        if tmp.exists():
            tmp.unlink()

    try:
        print(f"Noise sample 1/2 → {tmp_a.name}", flush=True)
        capture_to(tmp_a, args.process)
        print(f"Noise sample 2/2 → {tmp_b.name}", flush=True)
        capture_to(tmp_b, args.process)

        print("Computing noise diff...", flush=True)
        addrs = changed_addrs(tmp_a, tmp_b)
        print(f"  writing {len(addrs):,} addresses to {diff_path.name}...",
              flush=True)
        write_addrs(diff_path, addrs)
        print(f"{diff_path}: {len(addrs):,} addrs (noise sample)")
    finally:
        for tmp in (tmp_a, tmp_b):
            if tmp.exists():
                size_mb = tmp.stat().st_size // (1024 * 1024)
                print(f"  cleaning up {tmp.name} ({size_mb:,} MB)...",
                      flush=True)
                tmp.unlink()


def cmd_modules(args):
    """List loaded modules of a running process, optionally locating an addr."""
    import pymem
    pm = pymem.Pymem(args.process)
    target = int(args.contains, 0) if args.contains else None

    rows = []
    for mod in pm.list_modules():
        base = mod.lpBaseOfDll
        size = mod.SizeOfImage
        end = base + size
        rows.append((base, end, size, mod.name))
    rows.sort(key=lambda r: r[0])

    print(f"{'base':<18}  {'end':<18}  {'size':>10}  module")
    for base, end, size, name in rows:
        marker = "  <-- CONTAINS" if target is not None and base <= target < end else ""
        print(f"{base:#018x}  {end:#018x}  {size:>10,}  {name}{marker}")

    if target is not None:
        owner = next(
            ((b, e, s, n) for b, e, s, n in rows if b <= target < e), None
        )
        if owner:
            b, e, s, n = owner
            rva = target - b
            print(f"\n{target:#018x} is in {n}")
            print(f"  module base: {b:#018x}")
            print(f"  RVA:         {rva:#018x}  ({rva:,} bytes from base)")
        else:
            print(f"\n{target:#018x} is NOT in any loaded module.", file=sys.stderr)
            sys.exit(1)


def bytes_at_sorted(snap_path, sorted_addrs, progress=False):
    """For each addr in sorted_addrs (ascending), return {addr: byte} efficiently.

    Single sequential pass through the snap regions; no per-region linear scan
    of all targets. Suitable for millions of addresses.
    """
    result = {}
    n_addrs = len(sorted_addrs)
    if n_addrs == 0:
        return result
    with open(snap_path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        i = 0
        for region_idx in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            if not size:
                continue
            data = f.read(size)
            end = base + size
            while i < n_addrs and sorted_addrs[i] < base:
                i += 1
            while i < n_addrs and sorted_addrs[i] < end:
                a = sorted_addrs[i]
                result[a] = data[a - base]
                i += 1
            if progress and (region_idx % 50 == 0 or region_idx == n - 1):
                pct = (region_idx + 1) * 100 // n
                sys.stdout.write(
                    f"\r  {snap_path.name}: {region_idx+1:>5}/{n} regions "
                    f"({pct:>3}%)  matched {len(result):,} addrs "
                )
                sys.stdout.flush()
            if i >= n_addrs:
                break
        if progress:
            sys.stdout.write("\n")
    return result


def cmd_find_progression(args):
    snap_dir = Path(args.snap_dir)

    if args.snap:
        snaps = []
        for ref in args.snap:
            p = snap_dir / f"{ref}.snap"
            if not p.exists():
                p = snap_dir / ref
            if not p.exists():
                p = Path(ref)
            if not p.exists():
                print(f"Snap not found: {ref}", file=sys.stderr)
                sys.exit(1)
            snaps.append(p)
    else:
        snaps = sorted(snap_dir.glob("*.snap"))
        if not snaps:
            print(f"No .snap files in {snap_dir}", file=sys.stderr)
            sys.exit(1)

    progression = [int(x.strip(), 0) for x in args.progression.split(",")]
    if len(snaps) != len(progression):
        print(f"Have {len(snaps)} snaps but {len(progression)} progression "
              f"values. Counts must match (or pass --snap to select a subset).",
              file=sys.stderr)
        sys.exit(1)

    print("Snaps -> expected byte:")
    for s, v in zip(snaps, progression):
        print(f"  {s.name:<35} 0x{v:02x} ({v})")

    if args.snap:
        baseline_marker = snap_dir / BASELINE_MARKER
        baseline_label = (
            baseline_marker.read_text().strip().rsplit(".snap", 1)[0]
            if baseline_marker.exists() else None
        )
        diffs = []
        missing = []
        for snap in snaps:
            if snap.stem == baseline_label:
                continue
            d = snap_dir / f"diff_{snap.stem}.txt"
            if d.exists():
                diffs.append(d)
            else:
                missing.append(d.name)
        if missing:
            print(f"Missing diffs for selected snaps: {missing}", file=sys.stderr)
            sys.exit(1)
        diffs.sort()
    else:
        diffs = _main_diffs(snap_dir)

    if len(diffs) < 2:
        print(f"Need at least 2 diff files (have {len(diffs)}).",
              file=sys.stderr)
        sys.exit(1)
    print(f"\nUsing {len(diffs)} diff files:")
    for d in diffs:
        print(f"  {d.name}")

    print(f"\nReading {len(diffs)} main diffs...", flush=True)
    inter = None
    for d in diffs:
        s = read_addrs(d, progress=True)
        inter = s if inter is None else (inter & s)
        print(f"  {d.name}: {len(s):,} addrs")
    print(f"intersection: {len(inter):,} addrs")

    print("\nSorting intersection...", flush=True)
    sorted_addrs = sorted(inter)
    del inter

    snap_bytes = []
    for snap_path in snaps:
        print(f"\nReading bytes from {snap_path.name}...", flush=True)
        b = bytes_at_sorted(snap_path, sorted_addrs, progress=True)
        snap_bytes.append(b)

    print(f"\nFiltering for progression {progression}...", flush=True)
    candidates = []
    for addr in sorted_addrs:
        seq = [d.get(addr) for d in snap_bytes]
        if all(s == e for s, e in zip(seq, progression)):
            candidates.append((addr, seq))

    print(f"\n=== {len(candidates)} candidates ===")
    for addr, seq in candidates:
        bs = " ".join(f"0x{b:02x}" for b in seq)
        print(f"  {addr:#018x}  bytes: {bs}")

    if args.out:
        out_path = snap_dir / args.out
        with out_path.open("w") as f:
            f.write(f"# find-progression {progression}\n")
            f.write(f"# {len(candidates)} candidates\n")
            for addr, seq in candidates:
                bs = " ".join(f"0x{b:02x}" for b in seq)
                f.write(f"{addr:#018x}  {bs}\n")
        print(f"\nwrote {out_path}")


def read_bytes_at(snap_path, addr, length):
    """Read `length` bytes starting at `addr` from snap. None if not captured."""
    with open(snap_path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            if not size:
                continue
            if base <= addr and addr + length <= base + size:
                f.seek(addr - base, 1)
                return f.read(length)
            f.seek(size, 1)
    return None


def cmd_read(args):
    snap_dir = Path(args.snap_dir)

    if args.snap:
        snap_paths = []
        for ref in args.snap:
            p = snap_dir / f"{ref}.snap"
            if not p.exists():
                p = snap_dir / ref
            if not p.exists():
                p = Path(ref)
            if not p.exists():
                print(f"Snap not found: {ref}", file=sys.stderr)
                sys.exit(1)
            snap_paths.append(p)
    else:
        snap_paths = sorted(snap_dir.glob("*.snap"))
        if not snap_paths:
            print(f"No .snap files in {snap_dir}", file=sys.stderr)
            sys.exit(1)

    addr = int(args.addr, 0)
    n = args.length

    print(f"addr: {addr:#018x}  len: {n}")
    header = f"{'snap':<28}  hex"
    if n >= 4:
        header += f"{'':<{max(0, n*2-1)}}  {'i32_le':>11}  {'u32_le':>11}  {'f32':>12}  byte"
    elif n >= 2:
        header += f"{'':<{max(0, n*2-1)}}  {'u16_le':>6}  byte"
    else:
        header += f"{'':<{max(0, n*2-1)}}  byte"
    print(header)
    print("-" * len(header))

    for snap_path in snap_paths:
        data = read_bytes_at(snap_path, addr, n)
        if data is None:
            print(f"{snap_path.name:<28}  (not in any captured region)")
            continue
        hex_str = data.hex()
        line = f"{snap_path.name:<28}  {hex_str:<{max(8, n*2)}}"
        if n >= 4:
            i32 = struct.unpack('<i', data[:4])[0]
            u32 = struct.unpack('<I', data[:4])[0]
            f32 = struct.unpack('<f', data[:4])[0]
            line += f"  {i32:>11d}  {u32:>11d}  {f32: .4e}  0x{data[0]:02x}"
        elif n >= 2:
            u16 = struct.unpack('<H', data[:2])[0]
            line += f"  {u16:>6d}  0x{data[0]:02x}"
        else:
            line += f"  0x{data[0]:02x} ({data[0]})"
        print(line)


def cmd_intersect_noisy(args):
    out_dir = Path(args.out_dir)
    diffs = _main_diffs(out_dir)
    noise = _noise_diffs(out_dir)

    if len(diffs) < 2:
        print(f"Need at least 2 main diff files in {out_dir} (found {len(diffs)}).",
              file=sys.stderr)
        sys.exit(1)
    if len(noise) < 2:
        print(f"Need at least 2 noise diff files in {out_dir} "
              f"(found {len(noise)}). Run `grab-noisy` more times.",
              file=sys.stderr)
        sys.exit(1)

    intersect_out = out_dir / (args.out or INTERSECT_NOISY_NAME)
    if intersect_out.exists():
        print(f"{intersect_out} already exists — refusing to overwrite. "
              f"Pass --out <name> or delete the file.", file=sys.stderr)
        sys.exit(1)

    log = []
    # Main intersection
    print(f"Reading {len(diffs)} main diffs...", flush=True)
    log.append("Main diffs:")
    inter = None
    for d in diffs:
        s = read_addrs(d, progress=True)
        inter = s if inter is None else (inter & s)
        log.append(f"  {d.name}: {len(s):,} addrs")
    main_summary = f"main intersection: {len(inter):,} addrs across {len(diffs)} diffs"
    print(main_summary)
    log.append(main_summary)

    # Noise floor
    print(f"\nReading {len(noise)} noise samples...", flush=True)
    log.append("")
    log.append("Noise samples:")
    floor = None
    for d in noise:
        s = read_addrs(d, progress=True)
        floor = s if floor is None else (floor & s)
        log.append(f"  {d.name}: {len(s):,} addrs")
    floor_summary = f"noise floor: {len(floor):,} addrs across {len(noise)} samples"
    print(floor_summary)
    log.append(floor_summary)

    # Subtract
    before = len(inter)
    cleaned = inter - floor
    removed = before - len(cleaned)
    final = (
        f"after noise subtraction: {len(cleaned):,} addrs (removed {removed:,})"
    )
    print(f"\n{final}")
    log.append("")
    log.append(final)

    last_snap = _last_non_baseline_snap(out_dir)
    _write_intersect(
        intersect_out, cleaned, last_snap,
        f"{len(cleaned)} addresses across {len(diffs)} diffs minus "
        f"noise floor of {len(floor)} (from {len(noise)} samples)",
    )
    console_out = intersect_out.with_name(intersect_out.stem + "_console.txt")
    console_out.write_text("\n".join(log) + "\n")
    print(f"wrote {intersect_out}  (lines starting with * are run starts)")
    print(f"wrote {console_out}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    grab = sub.add_parser(
        "grab",
        help="Capture a snapshot. First grab is the baseline; rest auto-diff."
    )
    grab.add_argument(
        "label",
        nargs="?",
        default=None,
        help="Optional label (letters / digits / _ / -). "
             "Default: next sequential grabNNN.",
    )
    grab.add_argument("--process", default="Ravenswatch.exe")
    grab.add_argument("--out-dir", default=".",
                      help="Where to write snaps and diff files (default: CWD).")
    grab.set_defaults(func=cmd_grab)

    inter = sub.add_parser(
        "intersect",
        help="Intersect main diff_<label>.txt files; write intersect.txt"
    )
    inter.add_argument("--out-dir", default=".",
                       help="Where to read diffs and write the output (default: CWD)")
    inter.add_argument("--out", default=None,
                       help=f"Output filename (default: {INTERSECT_NAME}). "
                            "Refuses to overwrite an existing file.")
    inter.set_defaults(func=cmd_intersect)

    gn = sub.add_parser(
        "grab-noisy",
        help="Capture two snaps back-to-back to measure background drift; "
             "writes diff_noise_NNN.txt and discards the snaps."
    )
    gn.add_argument("--process", default="Ravenswatch.exe")
    gn.add_argument("--out-dir", default=".",
                    help="Where to write diff_noise_NNN.txt (default: CWD).")
    gn.set_defaults(func=cmd_grab_noisy)

    inn = sub.add_parser(
        "intersect-noisy",
        help="Intersect main diffs, subtract noise floor (from diff_noise_*.txt); "
             "fails if fewer than 2 noise samples are present."
    )
    inn.add_argument("--out-dir", default=".",
                     help="Where to read diffs and write the output (default: CWD)")
    inn.add_argument("--out", default=None,
                     help=f"Output filename (default: {INTERSECT_NOISY_NAME}). "
                          "Refuses to overwrite an existing file.")
    inn.set_defaults(func=cmd_intersect_noisy)

    rd = sub.add_parser(
        "read",
        help="Read bytes at an address across one or more snaps. "
             "Useful for verifying a candidate value progression."
    )
    rd.add_argument("addr", help="Address (hex 0x... or decimal).")
    rd.add_argument("--snap", action="append", default=None,
                    help="Snap label or path. Repeatable. "
                         "If omitted, reads from all *.snap in --snap-dir.")
    rd.add_argument("--len", type=int, default=4, dest="length",
                    help="Number of bytes to read (default: 4).")
    rd.add_argument("--snap-dir", default=".",
                    help="Where to find snaps (default: CWD).")
    rd.set_defaults(func=cmd_read)

    fp = sub.add_parser(
        "find-progression",
        help="Intersect diffs and filter to addresses whose byte progresses "
             "across snaps in a specified sequence (e.g., 1,2,3,4,5)."
    )
    fp.add_argument("--progression", required=True,
                    help="Comma-separated expected byte values per snap, in "
                         "snap order (alphabetical or as given by --snap).")
    fp.add_argument("--snap", action="append", default=None,
                    help="Snap label or path; repeatable. Defines order. "
                         "If omitted, uses all *.snap in --snap-dir, sorted.")
    fp.add_argument("--snap-dir", default=".",
                    help="Where to find snaps and diffs (default: CWD).")
    fp.add_argument("--out", default=None,
                    help="Optional output file for candidates "
                         "(written under --snap-dir).")
    fp.set_defaults(func=cmd_find_progression)

    md = sub.add_parser(
        "modules",
        help="List loaded modules of the running process; optionally locate "
             "which module owns a given address."
    )
    md.add_argument("--process", default="Ravenswatch.exe")
    md.add_argument("--contains", default=None,
                    help="Address (hex 0x... or decimal) to locate.")
    md.set_defaults(func=cmd_modules)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
