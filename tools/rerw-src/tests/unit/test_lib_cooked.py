"""Tests for cooked object-section annotation helpers."""

import struct
import uuid

from lib.cooked import (
    MARK_END,
    MARK_START,
    ClassEntry,
    CookedFile,
    Header,
    annotate_block,
    parse_object_section,
)


def _class(name: str, uid: int) -> ClassEntry:
    return ClassEntry(name, uid, 1, 0, 0, 0)


def test_parse_object_section_and_annotate_synthetic_block():
    classes = [_class("Root", 0x100), _class("Thing", 0x101)]
    guid = uuid.UUID("a90787f8-ae77-4747-9e44-0bbd4eee915f")
    body = b"".join(
        [
            struct.pack("<I", 5),
            b"Hello",
            guid.bytes_le,
            struct.pack("<I", 0),
            struct.pack("<I", 42),
        ]
    )
    object_section = (
        struct.pack("<II", MARK_START, 1)
        + body
        + struct.pack("<I", MARK_END)
    )
    cf = CookedFile(
        header=Header(16, 1, 6, b"Cooked", True, b""),
        classes=classes,
        object_section=object_section,
        raw_size=len(object_section),
    )

    blocks = parse_object_section(cf)
    assert len(blocks) == 1
    assert blocks[0].class_index == 1
    assert blocks[0].body == body

    annotations = annotate_block(blocks[0], classes)
    assert [(a.offset, a.kind, a.value) for a in annotations] == [
        (0, "string(5)", "'Hello'"),
        (9, "guid", str(guid)),
        (25, "class-ref", "0 (Root)"),
        (29, "u32", "42"),
    ]
