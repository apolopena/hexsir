"""Plain-text `.ot` manifest decoder.

Many `.ot` files in the game are pipe-delimited ASCII manifests, not the
binary "Cooked" serialization that `lib.cooked` handles. Each non-empty line:

    <resource_type>|<relative_path>|<class_name>

These manifests sit alongside cooked outputs (e.g.
`Geppetto.herodef.UsedRscCache.ot` next to
`Geppetto.herodef.ot.DtHeroDefinition.gen`) and tell the cooking pipeline
what resources a definition references. They are always plain UTF-8 text;
no encryption, no compression.

Format reference: rw/findings/save-edit-pipeline.md (the wider .ot/.gen
pipeline doc) and live confirmation by hex-dumping
`rw/harvested/Definitions/Heroes/Kqjjqiir.nqurtqh.JvqtLvbSgbnq.ri`
(`Geppetto.herodef.UsedRscCache.ot` after rerw filename-decipher).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OtEntry:
    resource_type: str
    path: str
    class_name: str


def parse_text(text: str) -> list[OtEntry]:
    entries: list[OtEntry] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 3:
            entries.append(OtEntry(resource_type="?", path=line, class_name=""))
            continue
        rtype, path, cls = parts
        entries.append(OtEntry(rtype, path, cls))
    return entries


def parse_file(path: str | Path) -> list[OtEntry]:
    return parse_text(Path(path).read_text(encoding="utf-8", errors="replace"))


def group_by_class(entries: list[OtEntry]) -> dict[str, list[OtEntry]]:
    out: "OrderedDict[str, list[OtEntry]]" = OrderedDict()
    for e in entries:
        out.setdefault(e.class_name, []).append(e)
    return out


def group_by_resource_type(entries: list[OtEntry]) -> dict[str, list[OtEntry]]:
    out: "OrderedDict[str, list[OtEntry]]" = OrderedDict()
    for e in entries:
        out.setdefault(e.resource_type, []).append(e)
    return out


def _format_summary(entries: list[OtEntry]) -> str:
    by_cls = group_by_class(entries)
    by_rt = group_by_resource_type(entries)
    lines = [
        f"entries          : {len(entries)}",
        f"distinct classes : {len(by_cls)}",
        f"resource types   : {len(by_rt)}",
        "",
        "By resource type:",
    ]
    for rt, items in sorted(by_rt.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {rt:24s}  {len(items):4d}")
    lines.append("")
    lines.append("By class:")
    for cls, items in sorted(by_cls.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {cls or '(empty)':40s}  {len(items):4d}")
    return "\n".join(lines)


def _format_full(entries: list[OtEntry]) -> str:
    rows = []
    for e in entries:
        rows.append(f"  [{e.resource_type:10s}] {e.path}   ->  {e.class_name}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Pretty-print a Ravenswatch .ot text manifest "
        "(pipe-delimited resource_type|path|class_name)."
    )
    p.add_argument("path", help="Path to a .ot file (plain text manifest).")
    p.add_argument(
        "--full",
        action="store_true",
        help="Print every entry instead of just the summary.",
    )
    p.add_argument(
        "--filter-class",
        metavar="CLASS",
        default=None,
        help="Only show entries with this class_name (substring match).",
    )
    args = p.parse_args(argv)

    entries = parse_file(args.path)
    if args.filter_class:
        needle = args.filter_class
        entries = [e for e in entries if needle in e.class_name]

    if args.full:
        print(_format_full(entries))
        print()
    print(_format_summary(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
