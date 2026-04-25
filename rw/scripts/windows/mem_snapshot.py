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
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
GRAB_PREFIX = "grab"
GRAB_PADDING = 3
GRAB_SEQ_RE = re.compile(rf"^{GRAB_PREFIX}(\d+)$")
BASELINE_MARKER = ".baseline"
INTERSECT_NAME = "intersect.txt"
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


def load_snapshot(path):
    """Yield (base, data) for each region."""
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            data = f.read(size)
            yield base, data


def changed_addrs(a_path, b_path):
    """Return set of byte addresses whose value differs between a and b."""
    addrs = set()
    a = dict(load_snapshot(a_path))
    b = dict(load_snapshot(b_path))
    for base in set(a) & set(b):
        da, db = a[base], b[base]
        if len(da) != len(db):
            continue
        for i in range(len(da)):
            if da[i] != db[i]:
                addrs.add(base + i)
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


def validate_label(label):
    if not LABEL_RE.match(label):
        raise ValueError(f"Invalid label: {label!r}. "
                         "Use letters, digits, '_' or '-'.")
    if label in RESERVED_LABELS:
        raise ValueError(f"Label {label!r} is reserved.")
    return label


def write_addrs(path, addrs):
    with path.open("w") as f:
        for a in sorted(addrs):
            f.write(f"{a:#018x}\n")


def read_addrs(path):
    out = set()
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.add(int(line, 16))
    return out


def values_at(snap_path, addrs):
    """For each addr in the set, look up the 4 bytes starting there in snap."""
    targets = set(addrs)
    out = {}
    with open(snap_path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        for _ in range(n):
            base, size = struct.unpack("<QQ", f.read(16))
            data = f.read(size)
            if not size:
                continue
            end = base + size
            for a in targets:
                if base <= a and a + 4 <= end:
                    out[a] = data[a - base:a - base + 4]
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


def cmd_intersect(args):
    out_dir = Path(args.out_dir)
    diffs = sorted(p for p in out_dir.iterdir() if DIFF_RE.match(p.name))
    if len(diffs) < 2:
        print(f"Need at least 2 diff files in {out_dir} (found {len(diffs)}).",
              file=sys.stderr)
        sys.exit(1)

    inter = None
    for d in diffs:
        s = read_addrs(d)
        inter = s if inter is None else (inter & s)
        print(f"{d.name}: {len(s):,} addrs")
    print(f"intersection: {len(inter):,} addrs across {len(diffs)} diffs")

    # Pick the most recent non-baseline snap for value display.
    baseline_marker = out_dir / BASELINE_MARKER
    baseline_name = (
        baseline_marker.read_text().strip() if baseline_marker.exists() else ""
    )
    snaps = [p for p in out_dir.glob("*.snap") if p.name != baseline_name]
    snaps.sort(key=lambda p: p.stat().st_mtime)
    last_snap = snaps[-1] if snaps else None

    vals = values_at(last_snap, inter) if last_snap and last_snap.exists() else {}
    intersect_out = out_dir / INTERSECT_NAME

    with intersect_out.open("w") as f:
        f.write(f"# {len(inter)} addresses changed in all {len(diffs)} diffs\n")
        if last_snap:
            f.write(f"# values from {last_snap.name}; addr  int32_le  float32  hex\n")
        else:
            f.write("# no snap available for value display\n")
        prev = None
        for a in sorted(inter):
            run_marker = " " if (prev is not None and a == prev + 1) else "*"
            v = vals.get(a)
            if v:
                i32 = struct.unpack("<i", v)[0]
                f32 = struct.unpack("<f", v)[0]
                f.write(f"{run_marker} {a:#018x}  {i32:>11d}  {f32: .4e}  {v.hex()}\n")
            else:
                f.write(f"{run_marker} {a:#018x}  (no value — out of captured regions)\n")
            prev = a
    print(f"wrote {intersect_out}  (lines starting with * are run starts)")


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

    inter = sub.add_parser("intersect",
                           help="Intersect all diff_*.txt; write intersect.txt")
    inter.add_argument("--out-dir", default=".",
                       help="Where to read diff_*.txt and write intersect.txt (default: CWD)")
    inter.set_defaults(func=cmd_intersect)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
