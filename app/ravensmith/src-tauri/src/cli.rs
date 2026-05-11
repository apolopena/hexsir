//! Build Tester request/response sidecar bridge.
//!
//! `rerw_run` spawns the bundled `rerw` PyInstaller sidecar via the Tauri
//! shell plugin, drains its output to completion (or kills it on timeout),
//! and returns a `CommandResult` with the exit code + accumulated stdout
//! and stderr. This is the path used by short-lived wizard steps; the
//! Dev Console (Superpowers) uses a separate `terminal_*` family that
//! streams output through events rather than blocking on completion.

use serde::Serialize;
use tauri::async_runtime::Receiver;
use tauri::AppHandle;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// Returned to the frontend.
#[derive(Debug, Serialize)]
pub struct CommandResult {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

/// Default timeout when the caller passes `None`. PRP-7 §"Timeout contract"
/// caps any single rerw invocation so a hang (interactive prompt despite
/// `--force`, deadlocked subprocess, etc.) cannot freeze the wizard
/// indefinitely.
const DEFAULT_TIMEOUT_MS: u64 = 30_000;

#[tauri::command]
pub async fn rerw_run(
    app: AppHandle,
    args: Vec<String>,
    timeout_ms: Option<u64>,
) -> Result<CommandResult, String> {
    // PYTHONUNBUFFERED=1 disables Python's stdout/stderr block-buffering
    // (equivalent to `python -u`) so progressive output reaches the IPC
    // layer without waiting for buffer flushes — load-bearing for any
    // wizard step with progressive output.
    //
    // FORCE_COLOR=1 keeps Click's `style`/`secho` ANSI output through the
    // pipe (Click 8.1+ honors this as the documented override when stdout
    // is not a TTY).
    let sidecar = app
        .shell()
        .sidecar("rerw")
        .map_err(|e| format!("sidecar lookup failed: {e}"))?
        .envs([
            ("PYTHONUNBUFFERED".to_string(), "1".to_string()),
            ("FORCE_COLOR".to_string(), "1".to_string()),
        ])
        .args(&args);

    let (mut rx, child) = sidecar.spawn().map_err(|e| format!("spawn failed: {e}"))?;

    let deadline = std::time::Duration::from_millis(timeout_ms.unwrap_or(DEFAULT_TIMEOUT_MS));

    match tokio::time::timeout(deadline, drain_loop(&mut rx)).await {
        Ok(result) => Ok(result),
        Err(_) => {
            // Dropping `rx` does NOT terminate the child; the explicit kill
            // is required or a hung rerw becomes an orphan that keeps the
            // shell-plugin slot warm.
            let _ = child.kill();
            Err(format!(
                "rerw_run: timed out after {}ms",
                deadline.as_millis()
            ))
        }
    }
}

async fn drain_loop(rx: &mut Receiver<CommandEvent>) -> CommandResult {
    let mut stdout = Vec::<u8>::new();
    let mut stderr = Vec::<u8>::new();
    let mut exit_code: i32 = -1;

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(bytes) => stdout.extend_from_slice(&bytes),
            CommandEvent::Stderr(bytes) => stderr.extend_from_slice(&bytes),
            CommandEvent::Terminated(payload) => {
                exit_code = payload.code.unwrap_or(-1);
                break;
            }
            CommandEvent::Error(_) => {
                // tauri-plugin-shell emits Error for unexpected I/O failures;
                // surface the partial output we have rather than blocking.
                break;
            }
            _ => {}
        }
    }

    CommandResult {
        stdout: String::from_utf8_lossy(&stdout).into_owned(),
        stderr: String::from_utf8_lossy(&stderr).into_owned(),
        exit_code,
    }
}
