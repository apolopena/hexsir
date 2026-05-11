# Tauri v2 — Sidecar (externalBin)

> **Source:** https://v2.tauri.app/develop/sidecar/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify externalBin syntax, target-triple naming, ShellExt spawn API, and capability syntax for sidecar binaries.

## Configuration in `tauri.conf.json`

External binaries are listed via `externalBin` under `bundle`:

```json
{
  "bundle": {
    "externalBin": [
      "/absolute/path/to/sidecar",
      "../relative/path/to/binary",
      "binaries/my-sidecar"
    ]
  }
}
```

Paths are relative to the `src-tauri` directory.

## Target-Triple Naming

Each binary requires a target-triple suffix. Examples:

- Linux: `my-sidecar-x86_64-unknown-linux-gnu`
- macOS (Apple Silicon): `my-sidecar-aarch64-apple-darwin`
- Windows x64: `my-sidecar-x86_64-pc-windows-msvc`

Discover the host triple:

```bash
rustc --print host-tuple        # Rust 1.84.0+
rustc -Vv | grep host | cut -f2 -d' '   # Older Rust
```

## Spawning from Rust

```rust
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;
use tauri::Emitter;

let sidecar_command = app.shell().sidecar("my-sidecar").unwrap();
let (mut rx, mut child) = sidecar_command.spawn().expect("Failed to spawn sidecar");

tauri::async_runtime::spawn(async move {
  while let Some(event) = rx.recv().await {
    if let CommandEvent::Stdout(line_bytes) = event {
      let line = String::from_utf8_lossy(&line_bytes);
      app.emit("message", Some(format!("'{}'", line))).unwrap();
      child.write("message from Rust\n".as_bytes()).unwrap();
    }
  }
});
```

Use the **filename only** (not the full path) when calling `sidecar()`.

## Spawning from JavaScript

```javascript
import { Command } from '@tauri-apps/plugin-shell';

const command = Command.sidecar('binaries/my-sidecar');
const output = await command.execute();
```

## Capability Syntax for Sidecar Permissions

`src-tauri/capabilities/default.json`:

```json
{
  "permissions": [
    "core:default",
    {
      "identifier": "shell:allow-execute",
      "allow": [
        {
          "name": "binaries/app",
          "sidecar": true
        }
      ]
    }
  ]
}
```

- Use `shell:allow-execute` for `Command.execute()` flow.
- Use `shell:allow-spawn` for `Command.spawn()` flow.
- The `name` matches the path passed to `Command.sidecar()` / `app.shell().sidecar()`.
- `sidecar: true` distinguishes from arbitrary-command grants.

## Allowed Arguments

Restrict args via the same capability shape:

```json
{
  "identifier": "shell:allow-execute",
  "allow": [
    {
      "args": [
        "arg1",
        "-a",
        "--arg2",
        { "validator": "\\S+" }
      ],
      "name": "binaries/my-sidecar",
      "sidecar": true
    }
  ]
}
```

Static literals must match exactly; `{"validator": "<regex>"}` matches any non-whitespace token (etc.).

Calls must match:

```rust
let sidecar_command = app.shell().sidecar("my-sidecar").unwrap()
  .args(["arg1", "-a", "--arg2", "value"]);
```

```javascript
const command = Command.sidecar('binaries/my-sidecar',
  ['arg1', '-a', '--arg2', 'value']);
```

## Notes for PRP-7

- Sidecar names verified: `binaries/rerw` and `binaries/frida` are correct paths.
- Target-triple naming: matches PRP-7's `rerw-x86_64-pc-windows-msvc.exe` etc.
- Capability scope syntax confirmed — replaces PRP-7's "Document the exact scope expression at instance time" placeholder.
