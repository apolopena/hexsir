"""Helpers for browsing Ravenswatch cooked asset paths."""

from __future__ import annotations

from pathlib import Path

from lib.cipher import COOKING_MARKER, decipher, decipher_path, encipher

DEFAULT_COOKING_ROOT = Path(
    "/mnt/d/steam-storage/steamapps/common/Ravenswatch/DarkTalesResources/_Cooking"
)


def default_cooking_root() -> Path:
    """Return the default Ravenswatch cooked asset root."""
    return DEFAULT_COOKING_ROOT


def normalize_asset_query(query: str) -> str:
    """Normalize a user path to a cooked-relative asset path."""
    normalized = query.strip().replace("\\", "/")
    _reject_truncated_input(normalized)
    if COOKING_MARKER in normalized:
        normalized = normalized.split(COOKING_MARKER, 1)[1]
    elif "rw/harvested/" in normalized:
        normalized = normalized.split("rw/harvested/", 1)[1]
    normalized = normalized.lstrip("/")
    return normalized.rstrip("/")


def _reject_truncated_input(query: str) -> None:
    if "/.../" in query:
        raise ValueError(
            "truncated paths are output-only; pass a real full path or cooked-relative path"
        )


def _full_cooked_root(query: str) -> Path | None:
    normalized = query.strip().replace("\\", "/")
    _reject_truncated_input(normalized)
    if COOKING_MARKER not in normalized:
        return None
    before, _ = normalized.split(COOKING_MARKER, 1)
    if not before.startswith("/") and ":" not in before:
        return None
    return Path((before + COOKING_MARKER).rstrip("/"))


def is_full_cooked_path(query: str) -> bool:
    """Return true when query is an absolute path into the cooked tree."""
    return _full_cooked_root(query) is not None


def _query_root_and_suffix(
    query: str,
    *,
    cooking_root: Path | None,
) -> tuple[Path, str]:
    full_root = _full_cooked_root(query)
    if full_root is not None:
        return full_root, normalize_asset_query(query)
    return cooking_root or default_cooking_root(), normalize_asset_query(query)


def _resolve_child(parent: Path, segment: str, *, query_is_ciphered: bool) -> Path:
    direct = parent / segment
    if direct.exists():
        return direct

    if not query_is_ciphered:
        ciphered = parent / encipher(segment)
        if ciphered.exists():
            return ciphered

    if not parent.is_dir():
        raise FileNotFoundError(f"asset path not found: {parent / segment}")

    for child in sorted(parent.iterdir(), key=lambda entry: entry.name.lower()):
        if child.name == segment:
            return child
        if not query_is_ciphered and decipher(child.name) == segment:
            return child

    raise FileNotFoundError(f"asset path not found: {parent / segment}")


def resolve_game_asset_path(
    query: str,
    *,
    cooking_root: Path | None = None,
    query_is_ciphered: bool = False,
) -> Path:
    """Resolve a decoded or ciphered cooked asset query to an on-disk path."""
    root, suffix = _query_root_and_suffix(query, cooking_root=cooking_root)
    if not root.exists():
        raise FileNotFoundError(f"cooked asset root not found: {root}")

    current = root
    if not suffix:
        return current

    for segment in suffix.split("/"):
        current = _resolve_child(current, segment, query_is_ciphered=query_is_ciphered)
    return current


def _cooked_relative(path: str) -> str:
    if COOKING_MARKER not in path:
        return path
    return path.split(COOKING_MARKER, 1)[1]


def _truncate_cooked_prefix(path: str) -> str:
    if COOKING_MARKER not in path:
        return path
    prefix, suffix = path.split(COOKING_MARKER, 1)
    trimmed = prefix.rstrip("/")
    parts = trimmed.split("/")
    if len(parts) >= 3 and parts[0] == "" and parts[1] == "mnt":
        root = f"/{parts[1]}/{parts[2]}"
    elif len(parts) >= 2 and parts[0] == "":
        root = "/" + parts[1]
    else:
        root = parts[0] if parts else ""
    return f"{root}/.../DarkTalesResources/_Cooking/{suffix}"


def display_game_asset_path(
    path: Path,
    *,
    raw: bool,
    full: bool,
    cooked_relative: bool,
    truncate_prefix: bool,
) -> str:
    rendered = path.as_posix() if raw else decipher_path(path.as_posix())
    if truncate_prefix:
        return _truncate_cooked_prefix(rendered)
    if cooked_relative:
        return _cooked_relative(rendered)
    if full:
        return rendered
    return rendered.rsplit("/", 1)[-1]


def list_game_assets(
    query: str,
    *,
    cooking_root: Path | None = None,
    query_is_ciphered: bool = False,
    raw: bool = False,
    full: bool = False,
    cooked_relative: bool = False,
    truncate_prefix: bool = False,
    include_hidden: bool = False,
    long: bool = False,
    tree_path: Path | None = None,
) -> list[str]:
    """List immediate children from the live cooked asset filesystem.

    ``tree_path`` is accepted for compatibility with older callers but is not
    read; this command should not depend on precomputed tree text files.
    """
    del tree_path
    path = resolve_game_asset_path(
        query,
        cooking_root=cooking_root,
        query_is_ciphered=query_is_ciphered,
    )

    if path.is_file():
        name = display_game_asset_path(
            path,
            raw=raw,
            full=full,
            cooked_relative=cooked_relative,
            truncate_prefix=truncate_prefix,
        )
        return [name]

    entries = [
        entry
        for entry in path.iterdir()
        if include_hidden or not entry.name.startswith(".")
    ]
    entries = sorted(entries, key=lambda entry: decipher(entry.name).lower())
    rendered = [
        display_game_asset_path(
            entry,
            raw=raw,
            full=full,
            cooked_relative=cooked_relative,
            truncate_prefix=truncate_prefix,
        )
        for entry in entries
    ]
    return rendered


def list_game_assets_from_filesystem(
    query: str,
    *,
    raw: bool = False,
    full: bool = False,
) -> list[str]:
    """Compatibility wrapper for callers that already pass filesystem paths."""
    return list_game_assets(query, raw=raw, full=full)
