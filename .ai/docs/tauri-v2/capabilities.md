# Tauri v2 — Capabilities

> **Source:** https://v2.tauri.app/security/capabilities/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify capability file location, auto-load behavior, JSON schema, and how multiple capabilities combine.

## File Location and Auto-Loading

Capability files live in `src-tauri/capabilities/` as `.json` or `.toml`.

> "All capabilities inside the `capabilities` directory are automatically enabled by default."

**Implication for compile-time gating (PRP-7):** dropping `superpowers.json` into `capabilities/` would activate it on every build, including default builds. To gate, the Superpowers capability must be defined OUTSIDE the auto-load directory and merged in only at Superpowers build time (via the `-c`/`--config` CLI flag — see `cli.md` and `config.md`).

## Capability JSON Structure

Required fields:

- `$schema` — schema reference (e.g., `"../gen/schemas/desktop-schema.json"`)
- `identifier` — unique name
- `description` — human-readable
- `windows` — array of window labels to target
- `permissions` — array of permission identifiers (or scoped objects)

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "main-capability",
  "description": "Capability for the main window",
  "windows": ["main"],
  "permissions": ["core:path:default", "core:window:allow-set-title"]
}
```

## Combining Capabilities

Three approaches in `tauri.conf.json` under `app.security.capabilities`:

1. **Reference pre-defined files** — list capability identifiers as strings.
2. **Inline definitions** — define capability objects directly in the config.
3. **Mixed** — combine both.

> "Inline capabilities can be mixed with pre-defined capabilities."

Used by PRP-7's overlay approach: Superpowers overlay JSON declares an inline capability under `app.security.capabilities`; merged via `-c` flag at build time.

## Platform Scoping

```json
{
  "platforms": ["linux", "macOS", "windows"]
}
```

Available targets: `linux`, `macOS`, `windows`, `iOS`, `android`.

## Remote API Access

```json
{
  "remote": {
    "urls": ["https://*.tauri.app"]
  }
}
```

## Notes for PRP-7

- Auto-load behavior confirms: PRP-7's earlier plan (drop `superpowers.json` into `capabilities/`) would have leaked the capability into default builds.
- Corrected design: keep only `capabilities/default.json` auto-loading; ship the Superpowers capability **inline within the overlay file** loaded via `-c` (see `config.md`).
- Inline-capability syntax in the overlay is supported per the "Inline capabilities can be mixed" guarantee.
