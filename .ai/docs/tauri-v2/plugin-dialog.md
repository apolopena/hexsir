# Tauri v2 — Dialog Plugin

> **Source:** https://v2.tauri.app/plugin/dialog/
> **Pulled:** 2026-05-04T15:05Z
> **Purpose:** Verify file-open dialog API and capability strings.

## Installation

```bash
npm run tauri add dialog
```

Or manually add `tauri-plugin-dialog` to `Cargo.toml` and initialize:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .run(tauri::generate_context!())
        .expect("error while running tauri application")
}
```

## JavaScript: File Open Dialog

```javascript
import { open } from '@tauri-apps/plugin-dialog';

const file = await open({
  multiple: false,
  directory: false,
});
console.log(file);
```

## Rust: File Open Dialog

Blocking:

```rust
use tauri_plugin_dialog::DialogExt;

let file_path = app.dialog().file().blocking_pick_file();
```

Non-blocking:

```rust
use tauri_plugin_dialog::DialogExt;

app.dialog().file().pick_file(|file_path| {
    // handle optional file_path
});
```

## Permissions

| Identifier | Effect |
|---|---|
| `dialog:allow-open` | File/directory picker |
| `dialog:deny-open` | Restrict picker |
| `dialog:allow-message` | Message dialogs |
| `dialog:allow-save` | Save dialogs |

The default permission set grants `allow-open`, `allow-save`, `allow-message`.

No scope syntax documented for this plugin — file-picker filters happen at call time, not in capability JSON.

## Notes for PRP-7

- `dialog:allow-open` is needed in `capabilities/default.json` for the Frida script picker.
- File-extension filtering (`.js` only) happens in the JS call (`filters: [{ name: "Frida JavaScript", extensions: ["js"] }]`), not in the capability.
