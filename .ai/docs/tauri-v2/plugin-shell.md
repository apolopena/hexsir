# Tauri v2 — Shell Plugin

> **Source:** https://v2.tauri.app/plugin/shell/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify ShellExt API, sidecar spawn semantics, and capability permission strings.

## Installation

```bash
npm run tauri add shell
# or manually:
cargo add tauri-plugin-shell
npm install @tauri-apps/plugin-shell
```

Initialize in `src-tauri/src/lib.rs`:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application")
}
```

## JavaScript API

```javascript
import { Command } from '@tauri-apps/plugin-shell';

let result = await Command.create('exec-sh', [
  '-c',
  "echo 'Hello World!'",
]).execute();
console.log(result);
```

## Rust API (ShellExt)

```rust
use tauri_plugin_shell::ShellExt;

let shell = app_handle.shell();
let output = tauri::async_runtime::block_on(async move {
    shell
        .command("echo")
        .args(["Hello from Rust!"])
        .output()
        .await
        .unwrap()
});

if output.status.success() {
    println!("Result: {:?}", String::from_utf8(output.stdout));
} else {
    println!("Exit with code: {}", output.status.code().unwrap());
}
```

## Capability Permissions

| Identifier | Effect |
|---|---|
| `shell:allow-execute` | Spawning child processes (without scope = unrestricted) |
| `shell:allow-spawn` | The spawn command |
| `shell:allow-kill` | Terminating running processes |
| `shell:allow-open` | Opening URLs/files |
| `shell:allow-stdin-write` | Writing to process stdin |

Each has a `deny-*` counterpart.

## Scoped Execution Example

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "main-capability",
  "permissions": [
    {
      "identifier": "shell:allow-execute",
      "allow": [
        {
          "name": "exec-sh",
          "cmd": "sh",
          "args": ["-c", {"validator": "\\S+"}],
          "sidecar": false
        }
      ]
    }
  ]
}
```

For sidecars, set `"sidecar": true` and use the sidecar's `binaries/<name>` path as `name`.

## Platform Support

Windows, Linux, macOS — full. iOS/Android: only `open` operations.

## Notes for PRP-7

- The `terminal.rs` PTY-spawn path uses `portable-pty` directly, NOT the shell plugin — so `shell:allow-spawn` does **not** apply to the Frida/rerw terminal-mode spawn. The shell plugin permissions only gate `rerw_run` (Build Tester) which uses `app.shell().sidecar("rerw")`.
- `shell:allow-stdin-write` may be needed for `rerw_run` if it ever pipes stdin — not currently a V1 feature.
- The terminal mode does not need any shell plugin capabilities since it bypasses the plugin entirely (per design — PTY semantics required, plugin gives plain pipes).
