"""Decoder for the oEngine 'Cooked' binary serialization format.

Used by every `.gen` file in `_Cooking/` (entity defs, hero defs, item defs,
etc.) and — with a 16-byte header variant — by `Profile_1.ob` save files.

Format reference: rw/findings/save-subsystem.md
  ("Modal_Save_Or_Quit.entity.ot decoded" section)

Magic markers (from FUN_1404e9350 / serialize_object_with_name):
  - 0xAABB1111 = section start
  - 0xAABB2222 = section end

Save file (.ob) header carries a CRC32 (zlib polynomial) over the body bytes
from offset 0x10 to end of file. Verified empirically: the stored hash at
offset 0x0C equals `zlib.crc32(data[0x10:])` for clean Profile_1.ob files,
and FUN_14064aa50 in Ravenswatch.exe contains explicit verification logic
calling FUN_140505cc0 (standard table-driven CRC32). When re-encoding a save
file, the CRC must be recomputed.
"""

from __future__ import annotations

import struct
import uuid
import zlib
from dataclasses import dataclass, field
from typing import BinaryIO, Optional

MARK_START = 0xAABB1111
MARK_END = 0xAABB2222
COOKED_MAGIC = b"Cooked"


@dataclass
class ClassEntry:
    """Class registry entry.

    Layout (after u32 name length + name bytes):
      u32 m_uId            -- class identifier (FNV hash of name, observed)
      u16 m_uVersionMaj
      u16 m_uVersionMin
      u32 ???              -- often 0 for top class, varies otherwise
      u32 m_uParentId      -- 0 for top class
    """

    name: str
    uid: int
    version_major: int
    version_minor: int
    schema_version: int
    parent_id: int


@dataclass
class Header:
    hdr_size: int
    field1: int
    field2: int  # for .gen: string length (=6); for .ob: 1
    magic_or_hash: bytes  # for .gen: b"Cooked"; for .ob: 4-byte hash
    is_cooked: bool  # True if magic spelled "Cooked"
    trailer: bytes  # bytes between magic/hash and first 0xAABB1111 marker


@dataclass
class CookedFile:
    header: Header
    classes: list[ClassEntry] = field(default_factory=list)
    object_section: bytes = b""  # raw bytes from first marker after registry to last 0xAABB2222
    raw_size: int = 0  # original file size (for round-trip verification)


@dataclass
class ObjectBlock:
    """One framed object in the cooked object section."""

    start: int  # offset within CookedFile.object_section, at 0xAABB1111
    end: int  # offset just after this object's 0xAABB2222
    class_index: int
    body: bytes  # bytes between class_index and this object's end marker


@dataclass
class TreeNode:
    """One node in the recursive object-tree.

    Top-level instances (listed in the leading instance index table) are the
    root nodes; nested sub-objects (embedded inside a parent's body via inline
    0xAABB1111/2222 sub-markers) are children.
    """

    start: int  # offset in object_section at the 0xAABB1111 marker
    end: int  # offset just past the matching 0xAABB2222
    class_index: int  # u32 immediately after the start marker
    children: list["TreeNode"] = field(default_factory=list)

    @property
    def body_start(self) -> int:
        return self.start + 8

    @property
    def body_end(self) -> int:
        return self.end - 4


@dataclass
class Annotation:
    """Best-effort interpretation of a byte range inside an ObjectBlock body."""

    offset: int
    size: int
    kind: str
    value: str
    guess: bool = False


# ---------------------------------------------------------------------------
# low-level read helpers


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def u8(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        (v,) = struct.unpack_from("<H", self.data, self.pos)
        self.pos += 2
        return v

    def u32(self) -> int:
        (v,) = struct.unpack_from("<I", self.data, self.pos)
        self.pos += 4
        return v

    def take(self, n: int) -> bytes:
        v = self.data[self.pos : self.pos + n]
        self.pos += n
        return v

    def lookahead_u32(self, off: int = 0) -> int:
        (v,) = struct.unpack_from("<I", self.data, self.pos + off)
        return v


# ---------------------------------------------------------------------------
# parser


def parse_header(r: _Reader) -> Header:
    """Parse the 16+ byte header.

    .gen layout (Modal_Save_Or_Quit example):
      0x00: u32 hdr_size = 16
      0x04: u32 = 1
      0x08: u32 strlen  = 6
      0x0C: 6 bytes 'Cooked'
      0x12: trailer bytes until 0xAABB1111

    .ob layout (Profile_1.ob example):
      0x00: u32 hdr_size = 16
      0x04: u32 = 0
      0x08: u32 = 1
      0x0C: 4 bytes hash/checksum
      0x10: 0xAABB1111 (no trailer)
    """
    hdr_size = r.u32()
    field1 = r.u32()
    field2 = r.u32()

    # determine variant by checking what's at +0xC
    # for .gen: field2 is the string length and the next bytes are that string
    # for .ob: field2 = 1 and the next 4 bytes are an opaque hash
    is_cooked = False
    magic_or_hash: bytes
    if field2 == len(COOKED_MAGIC) and r.data[r.pos : r.pos + len(COOKED_MAGIC)] == COOKED_MAGIC:
        magic_or_hash = r.take(len(COOKED_MAGIC))
        is_cooked = True
    else:
        # save-file variant: 4-byte hash
        magic_or_hash = r.take(4)

    # consume trailer bytes until 0xAABB1111 marker
    trailer_start = r.pos
    while r.lookahead_u32() != MARK_START:
        r.u8()
        if r.pos > trailer_start + 64:
            raise ValueError(
                f"no 0xAABB1111 marker within 64 bytes of header end "
                f"(trailer_start=0x{trailer_start:x})"
            )
    trailer = r.data[trailer_start : r.pos]
    return Header(hdr_size, field1, field2, magic_or_hash, is_cooked, trailer)


def parse_class_registry(r: _Reader) -> list[ClassEntry]:
    """Parse the class registry section.

    Layout: 0xAABB1111 [u32 count] N×ClassEntry [0xAABB2222]
    """
    mark = r.u32()
    if mark != MARK_START:
        raise ValueError(f"expected 0xAABB1111, got 0x{mark:08x} at pos 0x{r.pos - 4:x}")
    count = r.u32()
    classes = []
    for i in range(count):
        name_len = r.u32()
        name_bytes = r.take(name_len)
        name = name_bytes.decode("utf-8", errors="replace")
        uid = r.u32()
        vmaj = r.u16()
        vmin = r.u16()
        schema_version = r.u32()
        parent_id = r.u32()
        classes.append(ClassEntry(name, uid, vmaj, vmin, schema_version, parent_id))

    end = r.u32()
    if end != MARK_END:
        raise ValueError(
            f"expected 0xAABB2222 after class registry, got 0x{end:08x} at pos 0x{r.pos - 4:x}"
        )
    return classes


def parse_file(data: bytes) -> CookedFile:
    """Parse a .gen or Profile_1.ob file into structured form."""
    r = _Reader(data)
    header = parse_header(r)
    classes = parse_class_registry(r)
    # everything from here to end of file is the object section (multiple
    # 0xAABB1111/0xAABB2222 chunks). For now we keep it raw.
    object_section = data[r.pos :]
    return CookedFile(header=header, classes=classes, object_section=object_section, raw_size=len(data))


# ---------------------------------------------------------------------------
# object-section annotation


def parse_object_section(cf: CookedFile) -> list[ObjectBlock]:
    """Split the cooked object section into framed object blocks.

    Offsets are relative to ``cf.object_section``. Nested frames are returned
    as their own blocks as well as remaining inside the parent block body.
    """
    data = cf.object_section
    stack: list[tuple[int, int]] = []
    blocks: list[ObjectBlock] = []
    pos = 0

    while pos + 4 <= len(data):
        (mark,) = struct.unpack_from("<I", data, pos)
        if mark == MARK_START:
            if pos + 8 <= len(data):
                (class_index,) = struct.unpack_from("<I", data, pos + 4)
                stack.append((pos, class_index))
                pos += 8
                continue
        elif mark == MARK_END and stack:
            start, class_index = stack.pop()
            body_start = start + 8
            blocks.append(
                ObjectBlock(
                    start=start,
                    end=pos + 4,
                    class_index=class_index,
                    body=data[body_start:pos],
                )
            )
            pos += 4
            continue
        pos += 1

    blocks.sort(key=lambda b: (b.start, b.end))
    return blocks


def parse_object_tree(cf: CookedFile) -> list[TreeNode]:
    """Walk the object section recursively, returning a tree of nested frames.

    Skips the leading instance-index table block. Top-level frames (listed in
    that table) become root nodes; nested 0xAABB1111/2222 pairs inside any
    body become children of their containing frame.

    The walker scans 4-byte aligned u32s within bodies (since markers are
    always u32s). It assumes the 4 bytes immediately following each
    0xAABB1111 are a class_index — this matches what we've observed for both
    top-level frames and nested sub-objects.
    """
    data = cf.object_section
    if len(data) < 8 or struct.unpack_from("<I", data, 0)[0] != MARK_START:
        raise ValueError("object_section does not start with 0xAABB1111")
    table_count = struct.unpack_from("<I", data, 4)[0]
    table_end = 8 + table_count * 4
    if struct.unpack_from("<I", data, table_end)[0] != MARK_END:
        raise ValueError(
            f"expected 0xAABB2222 at end of leading instance table (offset 0x{table_end:x})"
        )
    pos = table_end + 4

    def parse_one(start: int) -> tuple[TreeNode, int]:
        # start points at 0xAABB1111
        if struct.unpack_from("<I", data, start)[0] != MARK_START:
            raise ValueError(f"expected 0xAABB1111 at 0x{start:x}")
        class_index = struct.unpack_from("<I", data, start + 4)[0]
        children: list[TreeNode] = []
        body_pos = start + 8
        # Walk the body looking for nested marker pairs at 4-byte alignment.
        while body_pos + 4 <= len(data):
            v = struct.unpack_from("<I", data, body_pos)[0]
            if v == MARK_END:
                end = body_pos + 4
                node = TreeNode(start=start, end=end, class_index=class_index, children=children)
                return node, end
            if v == MARK_START:
                child, child_end = parse_one(body_pos)
                children.append(child)
                body_pos = child_end
                continue
            body_pos += 1  # not a marker; advance one byte (markers may not be 4-aligned)
        raise ValueError(f"unbalanced markers starting at 0x{start:x}")

    roots: list[TreeNode] = []
    for _ in range(table_count):
        node, pos = parse_one(pos)
        roots.append(node)
    # After the table_count frames, an "outer object" region follows: this is
    # the root oCDtGameProfile object's serialized body (not in the instance
    # index table because it's the wrapper passed in from outside the loader).
    # Parse any additional 0xAABB1111-framed nodes until end-of-section.
    while pos + 4 <= len(data):
        v = struct.unpack_from("<I", data, pos)[0]
        if v == MARK_START:
            node, pos = parse_one(pos)
            roots.append(node)
        else:
            pos += 1
    return roots


def find_class_in_tree(
    cf: CookedFile, roots: list[TreeNode], class_name: str
) -> list[tuple[list[int], TreeNode]]:
    """Find every node in the tree whose class is ``class_name``.

    Returns a list of (path, node) tuples where path is the list of child
    indices from a root to reach this node (e.g. [3, 0, 2] = root[3].children[0].children[2]).
    """
    out: list[tuple[list[int], TreeNode]] = []

    def visit(node: TreeNode, path: list[int]) -> None:
        if 0 <= node.class_index < len(cf.classes):
            if cf.classes[node.class_index].name == class_name:
                out.append((list(path), node))
        for i, child in enumerate(node.children):
            path.append(i)
            visit(child, path)
            path.pop()

    for i, root in enumerate(roots):
        visit(root, [i])
    return out


def _format_tree(cf: CookedFile, roots: list[TreeNode], max_depth: int = 99) -> str:
    """Render a textual tree. Indented; one line per node. Class names with
    body sizes and absolute file offsets."""
    lines: list[str] = []

    def render(node: TreeNode, depth: int, path: list[int]) -> None:
        if depth > max_depth:
            return
        cls = cf.classes[node.class_index].name if 0 <= node.class_index < len(cf.classes) else f"<bad cls {node.class_index}>"
        body_size = node.body_end - node.body_start
        path_str = ".".join(str(p) for p in path)
        indent = "  " * depth
        lines.append(
            f"{indent}[{path_str}] {cls} (offset 0x{node.start:x}, body 0x{body_size:x} bytes, "
            f"{len(node.children)} children)"
        )
        for i, child in enumerate(node.children):
            path.append(i)
            render(child, depth + 1, path)
            path.pop()

    for i, root in enumerate(roots):
        render(root, 0, [i])
    return "\n".join(lines)


def _is_mostly_printable(bs: bytes) -> bool:
    if not bs:
        return False
    printable = sum(1 for b in bs if b in (9, 10, 13) or 0x20 <= b <= 0x7E)
    return printable / len(bs) > 0.9


def _string_at(data: bytes, off: int) -> tuple[int, str] | None:
    if off + 4 > len(data):
        return None
    (size,) = struct.unpack_from("<I", data, off)
    if not 1 <= size <= 256 or off + 4 + size > len(data):
        return None
    bs = data[off + 4 : off + 4 + size]
    if not _is_mostly_printable(bs):
        return None
    try:
        text = bs.decode("ascii")
    except UnicodeDecodeError:
        return None
    return size, text


def _uuid_at(data: bytes, off: int) -> uuid.UUID | None:
    if off + 16 > len(data):
        return None
    bs = data[off : off + 16]
    if len(set(bs)) < 8 or bs.count(0) > 4:
        return None
    try:
        value = uuid.UUID(bytes_le=bs)
    except ValueError:
        return None
    if value.version not in {1, 2, 3, 4, 5}:
        return None
    if value.variant != uuid.RFC_4122:
        return None
    return value


def _float_at(data: bytes, off: int, raw_u32: int) -> float | None:
    if off + 4 > len(data):
        return None
    if raw_u32 < 1024:
        return None
    (value,) = struct.unpack_from("<f", data, off)
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if -1_000_000.0 <= value <= 1_000_000.0:
        return value
    return None


def _looks_recognized(data: bytes, off: int, classes: list[ClassEntry]) -> bool:
    if _string_at(data, off) is not None or _uuid_at(data, off) is not None:
        return True
    if off + 4 > len(data):
        return False
    (u32,) = struct.unpack_from("<I", data, off)
    return u32 in {MARK_START, MARK_END} or u32 < len(classes) or u32 < 1024


def _raw_annotation(data: bytes, off: int, classes: list[ClassEntry]) -> Annotation:
    end = min(len(data), off + 16)
    for candidate in range(off + 1, end):
        if _looks_recognized(data, candidate, classes):
            end = candidate
            break
    return Annotation(off, end - off, "raw", data[off:end].hex(" "))


def annotate_block(block: ObjectBlock, classes: list[ClassEntry]) -> list[Annotation]:
    """Return best-effort annotations for one object block body.

    These annotations are intentionally heuristic. Guessed interpretations are
    marked with ``guess=True`` so callers can render them differently.
    """
    data = block.body
    anns: list[Annotation] = []
    pos = 0

    while pos < len(data):
        string_hit = _string_at(data, pos)
        if string_hit is not None:
            size, text = string_hit
            anns.append(Annotation(pos, 4 + size, f"string({size})", repr(text)))
            pos += 4 + size
            continue

        if pos + 4 <= len(data):
            (u32,) = struct.unpack_from("<I", data, pos)
            if u32 == MARK_START:
                anns.append(Annotation(pos, 4, "sub-marker", "0xAABB1111"))
                pos += 4
                continue
            if u32 == MARK_END:
                anns.append(Annotation(pos, 4, "sub-marker", "0xAABB2222"))
                pos += 4
                continue

        guid = _uuid_at(data, pos)
        if guid is not None and _string_at(data, pos) is None:
            anns.append(Annotation(pos, 16, "guid", str(guid)))
            pos += 16
            continue

        if pos + 4 <= len(data):
            (u32,) = struct.unpack_from("<I", data, pos)
            if u32 < len(classes):
                anns.append(Annotation(pos, 4, "class-ref", f"{u32} ({classes[u32].name})"))
                pos += 4
                continue

            float_value = _float_at(data, pos, u32)
            if float_value is not None:
                anns.append(Annotation(pos, 4, "float?", f"{float_value:.9g}", guess=True))
                pos += 4
                continue

            if u32 < 1024:
                anns.append(Annotation(pos, 4, "u32", str(u32)))
                pos += 4
                continue

        ann = _raw_annotation(data, pos, classes)
        anns.append(ann)
        pos += ann.size

    return anns


# ---------------------------------------------------------------------------
# encoder (for round-trip verification)


def encode_file(cf: CookedFile, recompute_crc: bool = True) -> bytes:
    """Re-encode a parsed file back to bytes.

    For save (.ob) files, the 4-byte hash at offset 0x0C is a CRC32 (zlib
    polynomial) over the body bytes from 0x10 to end of file. When
    re-encoding modified saves, set recompute_crc=True (default) so the
    written hash matches the new body. For pure round-trip equality
    validation of an unmodified file, recompute=True still produces the
    correct value because the original CRC is consistent with its body.
    """
    out = bytearray()
    h = cf.header
    out += struct.pack("<III", h.hdr_size, h.field1, h.field2)
    if h.is_cooked:
        # .gen files: 'Cooked' magic, no CRC slot
        out += h.magic_or_hash
    else:
        # .ob files: 4-byte CRC slot at offset 0x0C
        # placeholder — patched after body is known
        out += b"\x00\x00\x00\x00"
    out += h.trailer
    out += struct.pack("<II", MARK_START, len(cf.classes))
    for c in cf.classes:
        name_bytes = c.name.encode("utf-8")
        out += struct.pack("<I", len(name_bytes))
        out += name_bytes
        out += struct.pack(
            "<IHHII",
            c.uid,
            c.version_major,
            c.version_minor,
            c.schema_version,
            c.parent_id,
        )
    out += struct.pack("<I", MARK_END)
    out += cf.object_section

    # patch CRC for save files
    if not h.is_cooked:
        if recompute_crc:
            crc = zlib.crc32(bytes(out[0x10:])) & 0xFFFFFFFF
            out[0x0C:0x10] = struct.pack("<I", crc)
        else:
            # preserve original hash
            out[0x0C:0x10] = h.magic_or_hash
    return bytes(out)


# ---------------------------------------------------------------------------
# CLI / quick check


def _summarize(cf: CookedFile) -> str:
    h = cf.header
    lines = [
        f"raw size:     {cf.raw_size} bytes",
        f"header:       hdr_size={h.hdr_size} f1={h.field1} f2={h.field2} "
        f"is_cooked={h.is_cooked} trailer_len={len(h.trailer)}",
    ]
    if h.is_cooked:
        lines.append(f"  magic:      {h.magic_or_hash!r}")
    else:
        lines.append(f"  hash:       {h.magic_or_hash.hex()}")
    if h.trailer:
        lines.append(f"  trailer hex: {h.trailer.hex()}")
    lines.append(f"classes:      {len(cf.classes)}")
    for i, c in enumerate(cf.classes):
        lines.append(
            f"  [{i:2d}] {c.name:<46s} uid=0x{c.uid:08x} "
            f"v={c.version_major}.{c.version_minor} schema_v={c.schema_version} "
            f"parent=0x{c.parent_id:08x}"
        )
    lines.append(f"object section: {len(cf.object_section)} bytes")
    return "\n".join(lines)


def _format_annotation(ann: Annotation) -> str:
    kind = ann.kind
    if ann.guess:
        kind += " (guess)"
    return f"  +0x{ann.offset:04x}  {kind:<16s} {ann.value}"


def _annotated_dump(cf: CookedFile) -> str:
    try:
        from lib import cooked_schemas
    except ImportError:
        cooked_schemas = None

    blocks = parse_object_section(cf)
    lines = [f"object blocks: {len(blocks)}"]
    for i, block in enumerate(blocks):
        if 0 <= block.class_index < len(cf.classes):
            class_entry = cf.classes[block.class_index]
            class_name = class_entry.name
        else:
            class_entry = None
            class_name = f"<invalid class index {block.class_index}>"

        # synthetic note for the leading instance-table block (its "class_index"
        # is actually the entry count)
        if i == 0 and class_entry is None:
            class_name = "<instance table — count of object instances follows>"

        lines.append("")
        lines.append(
            f"=== Object #{i}: {class_name} "
            f"(offset 0x{block.start:x}, size 0x{block.end - block.start:x}) ==="
        )
        lines.append(f"  +0x0000  class-index      {block.class_index}")

        # try schema-based decode if we have one for this class
        schema_decoded = False
        if cooked_schemas and class_entry is not None:
            schema = cooked_schemas.SCHEMAS_BY_NAME.get(class_entry.name)
            if schema is not None:
                try:
                    schema_reader = _Reader(block.body)
                    fields = cooked_schemas.parse_schema(
                        schema_reader, schema, class_entry.schema_version
                    )
                    lines.append(
                        f"  -- schema decode (schema_v={class_entry.schema_version}) --"
                    )
                    for name, value in fields.items():
                        lines.append(f"  {name:<24s} = {value!r}")
                    consumed = schema_reader.pos
                    if consumed < len(block.body):
                        remaining = len(block.body) - consumed
                        lines.append(
                            f"  -- {remaining} unparsed bytes follow (schema is partial) --"
                        )
                    schema_decoded = True
                except Exception as e:
                    lines.append(f"  -- schema decode failed: {e} --")

        if not schema_decoded:
            for ann in annotate_block(block, cf.classes):
                lines.append(_format_annotation(ann))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Cooked .gen/.ob decoder")
    ap.add_argument("path", help="file to parse")
    ap.add_argument("--annotate", action="store_true", help="print a heuristic object-section dump")
    ap.add_argument("--tree", action="store_true", help="print the recursive object tree")
    ap.add_argument("--tree-class", metavar="NAME", help="filter --tree to instances of class NAME (and their parents)")
    ap.add_argument("--tree-depth", type=int, default=99, help="max --tree depth (default unlimited)")
    ap.add_argument("--check-roundtrip", action="store_true", help="verify byte-equal re-encode")
    args = ap.parse_args()

    with open(args.path, "rb") as f:
        data = f.read()
    cf = parse_file(data)
    print(_summarize(cf))

    if args.annotate:
        print()
        print(_annotated_dump(cf))

    if args.tree:
        print()
        roots = parse_object_tree(cf)
        if args.tree_class:
            hits = find_class_in_tree(cf, roots, args.tree_class)
            print(f"=== {args.tree_class}: {len(hits)} instance(s) ===")
            for path, node in hits:
                cls = cf.classes[node.class_index].name
                body_size = node.body_end - node.body_start
                path_str = ".".join(str(p) for p in path)
                print(
                    f"[{path_str}] {cls} (offset 0x{node.start:x}, body 0x{body_size:x} bytes, "
                    f"{len(node.children)} children)"
                )
        else:
            print(_format_tree(cf, roots, max_depth=args.tree_depth))

    if args.check_roundtrip:
        out = encode_file(cf)
        if out == data:
            print("\nround-trip: OK (byte-for-byte match)")
        else:
            # show first diverging offset
            for i in range(min(len(out), len(data))):
                if out[i] != data[i]:
                    print(
                        f"\nround-trip: DIFFERS at offset 0x{i:x} "
                        f"(orig={data[i]:02x} reenc={out[i]:02x})"
                    )
                    print(f"  orig context:   {data[max(0, i - 8) : i + 8].hex()}")
                    print(f"  reenc context:  {out[max(0, i - 8) : i + 8].hex()}")
                    break
            if len(out) != len(data):
                print(f"\nround-trip: SIZE DIFFERS orig={len(data)} reenc={len(out)}")
            sys.exit(1)
