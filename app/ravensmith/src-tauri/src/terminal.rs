//! Dev Console PTY backend (Superpowers only).
//!
//! Spawns either the bundled `rerw` or `frida` sidecar through a real PTY
//! (`portable-pty`) and bridges I/O to the frontend xterm.js terminal via
//! Tauri events. Bypasses `tauri-plugin-shell` entirely — the shell plugin
//! yields plain pipes, not PTY semantics.
//!
//! State machine + mode-swap rules per PRP-7 §"Console mode swap":
//! `idle | starting | running | swapping | stopping | exited`.
//! Linux SIGKILL via `ChildKiller::clone_killer()`; 5-second `try_wait()`
//! polling demotes `swapping` to `exited` if the child won't die.

use std::io::Read;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use serde::Serialize;
use tauri::{AppHandle, Emitter, State as TauriState};

use crate::state::{ManagedTerminal, Mode, State, TerminalState};

const RAVENSWATCH_PROCESS_NAME: &str = "Ravenswatch.exe";
const SWAP_KILL_TIMEOUT: Duration = Duration::from_secs(5);

/// Tauri-managed value: the entire terminal state lives behind one Arc so
/// background tasks can hold their own owned references via `.clone()`.
pub type SharedTerminal = Arc<ManagedTerminal>;

/// `terminal-output { stream, data }` event payload.
#[derive(Serialize, Clone)]
struct TerminalOutput {
    stream: &'static str,
    data: String,
}

/// `terminal-exit { code }` event payload.
#[derive(Serialize, Clone)]
struct TerminalExit {
    code: Option<i32>,
}

// ---------------------------------------------------------------------------
// IPC commands

#[tauri::command]
pub async fn terminal_get_state(
    mt: TauriState<'_, SharedTerminal>,
) -> Result<TerminalState, String> {
    Ok(mt.state.lock().await.clone())
}

#[tauri::command]
pub async fn terminal_set_mode(
    app: AppHandle,
    mt: TauriState<'_, SharedTerminal>,
    target: String,
) -> Result<(), String> {
    let new_mode = Mode::parse(&target).ok_or_else(|| format!("unknown mode: {target}"))?;

    // Lock state once for the decision; release before any kill or
    // long-running task to honor "never hold a lock across await on I/O".
    let action = {
        let s = mt.state.lock().await;
        if s.state.is_busy() {
            // PRP §IPC: busy states return Err and DO NOT also emit on
            // `app` stream — frontend surfaces the rejection via the
            // invoke channel; double-reporting would duplicate.
            return Err(format!(
                "[ravensmith] Console busy (state={}); try again.",
                s.state.as_str()
            ));
        }
        if s.mode == new_mode {
            // Same mode: emit a resync event but do NOT respawn — same-
            // mode-while-running is a frontend-remount artifact, not a
            // user intent to restart.
            SwapAction::Resync(s.clone())
        } else if matches!(s.state, State::Idle | State::Exited) {
            SwapAction::AtomicSwap {
                old_mode: s.mode,
                new_mode,
            }
        } else {
            // state == Running and mode changed.
            SwapAction::KillAndSwap { new_mode }
        }
    };

    let mt_arc: SharedTerminal = mt.inner().clone();

    match action {
        SwapAction::Resync(snap) => {
            emit_state(&app, &snap);
        }
        SwapAction::AtomicSwap { old_mode, new_mode } => {
            emit_app(
                &app,
                format!(
                    "── switched mode: {} → {} ──\n",
                    old_mode.as_str(),
                    new_mode.as_str()
                ),
            );
            let mut s = mt_arc.state.lock().await;
            s.mode = new_mode;
            s.state = State::Idle;
            let snap = s.clone();
            drop(s);
            emit_state(&app, &snap);
        }
        SwapAction::KillAndSwap { new_mode } => {
            // Transition to Swapping, stash pending target, take killer.
            {
                let mut s = mt_arc.state.lock().await;
                s.state = State::Swapping;
                s.pending_mode_swap = Some(new_mode);
                let snap = s.clone();
                drop(s);
                emit_state(&app, &snap);
            }

            let killer_opt = { mt_arc.killer.lock().await.take() };
            if let Some(mut k) = killer_opt {
                // Linux: SIGKILL. Windows: TerminateProcess. No grace.
                // Per PRP: kill is best-effort; the wait task is the
                // source of truth. Errs from kill are informational.
                let _ = k.kill();
            }

            // Schedule the 5s polling-timeout demotion. The wait task
            // (spawned at the original Start) normally completes the
            // swap before this fires.
            let mt_clone = mt_arc.clone();
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(SWAP_KILL_TIMEOUT).await;
                let mut s = mt_clone.state.lock().await;
                if s.state == State::Swapping {
                    s.state = State::Exited;
                    s.pending_mode_swap = None;
                    let snap = s.clone();
                    drop(s);
                    emit_app(
                        &app_clone,
                        "[ravensmith] terminal child did not exit; mode swap aborted.\n".into(),
                    );
                    emit_state(&app_clone, &snap);
                }
            });
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn terminal_start(
    app: AppHandle,
    mt: TauriState<'_, SharedTerminal>,
    args: Vec<String>,
) -> Result<(), String> {
    {
        let s = mt.state.lock().await;
        if s.state.is_busy() {
            return Err(format!(
                "[ravensmith] Console busy (state={}); try again.",
                s.state.as_str()
            ));
        }
        if matches!(s.state, State::Running) {
            return Err("[ravensmith] terminal already running; use Restart.".into());
        }
    }

    let mt_arc: SharedTerminal = mt.inner().clone();

    // Build argv per active mode. PRP §"args semantics by mode":
    // Frida → ignore caller args, build from state. rerw → passthrough.
    let (mode, selected_script, (cols, rows)) = {
        let s = mt_arc.state.lock().await;
        let size = *mt_arc.size.lock().await;
        (s.mode, s.selected_script.clone(), size)
    };

    let argv: Vec<String> = match mode {
        Mode::Rerw => args,
        Mode::Frida => {
            let script = selected_script.ok_or_else(|| {
                "[ravensmith] no Frida script selected; use Frida > Open Script…".to_string()
            })?;
            vec![
                "-n".into(),
                RAVENSWATCH_PROCESS_NAME.into(),
                "-l".into(),
                script,
            ]
        }
    };

    // Transition to Starting before spawn so concurrent invocations are
    // rejected by the busy guard above.
    {
        let mut s = mt_arc.state.lock().await;
        s.state = State::Starting;
        let snap = s.clone();
        drop(s);
        emit_state(&app, &snap);
    }

    let sidecar_name = match mode {
        Mode::Rerw => "rerw",
        Mode::Frida => "frida",
    };

    let spawned = match spawn_pty_child(sidecar_name, &argv, cols, rows) {
        Ok(s) => s,
        Err(e) => {
            // Spawn failed: revert to Exited so user can retry.
            let mut s = mt_arc.state.lock().await;
            s.state = State::Exited;
            s.last_exit_code = None;
            let snap = s.clone();
            drop(s);
            emit_app(&app, format!("[ravensmith] spawn failed: {e}\n"));
            emit_state(&app, &snap);
            return Err(e);
        }
    };

    {
        *mt_arc.killer.lock().await = Some(spawned.killer);
        *mt_arc.writer.lock().await = Some(spawned.writer);
        *mt_arc.master.lock().await = Some(spawned.master);
    }

    spawn_reader_task(app.clone(), spawned.reader);
    spawn_wait_task(app.clone(), mt_arc.clone(), spawned.child);

    // Flush any pending app messages queued during setup() (bundled
    // rw_lab.js soft-fail warnings, etc.) on the first emit after start.
    let pending = std::mem::take(&mut *mt_arc.pending_app_messages.lock().await);
    for msg in pending {
        emit_app(&app, msg);
    }

    let mut s = mt_arc.state.lock().await;
    s.state = State::Running;
    s.last_exit_code = None;
    let snap = s.clone();
    drop(s);
    emit_state(&app, &snap);
    Ok(())
}

#[tauri::command]
pub async fn terminal_stop(
    app: AppHandle,
    mt: TauriState<'_, SharedTerminal>,
) -> Result<(), String> {
    {
        let mut s = mt.state.lock().await;
        if s.state.is_busy() {
            return Err(format!(
                "[ravensmith] Console busy (state={}); try again.",
                s.state.as_str()
            ));
        }
        if !matches!(s.state, State::Running) {
            return Ok(()); // idempotent: stopping nothing is fine
        }
        s.state = State::Stopping;
        let snap = s.clone();
        drop(s);
        emit_state(&app, &snap);
    }

    let killer_opt = mt.killer.lock().await.take();
    if let Some(mut k) = killer_opt {
        // Best-effort kill; the wait task observes exit and transitions
        // Stopping → Exited (same path as Running → Exited).
        let _ = k.kill();
    }
    Ok(())
}

#[tauri::command]
pub async fn terminal_restart(
    app: AppHandle,
    mt: TauriState<'_, SharedTerminal>,
    args: Vec<String>,
) -> Result<(), String> {
    {
        let s = mt.state.lock().await;
        if s.state.is_busy() {
            return Err(format!(
                "[ravensmith] Console busy (state={}); try again.",
                s.state.as_str()
            ));
        }
    }

    // Stop if running, then start. Stop is best-effort.
    let _ = terminal_stop(app.clone(), mt.clone()).await;
    // Brief yield so the wait task can transition state to Exited before
    // we attempt a fresh spawn.
    tokio::time::sleep(Duration::from_millis(50)).await;
    terminal_start(app, mt, args).await
}

#[tauri::command]
pub async fn terminal_write_input(
    mt: TauriState<'_, SharedTerminal>,
    data: String,
) -> Result<(), String> {
    use std::io::Write as _;
    let mut writer_slot = mt.writer.lock().await;
    if let Some(w) = writer_slot.as_mut() {
        w.write_all(data.as_bytes())
            .map_err(|e| format!("write_input: {e}"))?;
        w.flush().map_err(|e| format!("write_input flush: {e}"))?;
    }
    // Silently no-op when no writer (terminal not running).
    Ok(())
}

#[tauri::command]
pub async fn terminal_resize(
    mt: TauriState<'_, SharedTerminal>,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    *mt.size.lock().await = (cols, rows);
    let master_slot = mt.master.lock().await;
    if let Some(m) = master_slot.as_ref() {
        m.resize(PtySize {
            cols,
            rows,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("resize: {e}"))?;
    }
    // Resize-without-master is a no-op — applies to next spawn via size mutex.
    Ok(())
}

#[tauri::command]
pub async fn terminal_set_frida_script(
    app: AppHandle,
    mt: TauriState<'_, SharedTerminal>,
    path: String,
) -> Result<(), String> {
    let mut s = mt.state.lock().await;
    s.selected_script = Some(path);
    let snap = s.clone();
    drop(s);
    emit_state(&app, &snap);
    Ok(())
}

// ---------------------------------------------------------------------------
// Internal helpers

enum SwapAction {
    /// Same mode, no respawn — just emit a state resync event.
    Resync(TerminalState),
    /// State == Idle/Exited and mode changed — atomic swap, no kill needed.
    AtomicSwap { old_mode: Mode, new_mode: Mode },
    /// State == Running and mode changed — kill, wait task completes swap.
    KillAndSwap { new_mode: Mode },
}

struct SpawnedChild {
    child: Box<dyn portable_pty::Child + Send + Sync>,
    reader: Box<dyn Read + Send>,
    writer: Box<dyn std::io::Write + Send>,
    killer: Box<dyn portable_pty::ChildKiller + Send + Sync>,
    master: Box<dyn portable_pty::MasterPty + Send>,
}

fn spawn_pty_child(
    sidecar: &str,
    args: &[String],
    cols: u16,
    rows: u16,
) -> Result<SpawnedChild, String> {
    let pty_system = native_pty_system();
    let pair = pty_system
        .openpty(PtySize {
            cols,
            rows,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("openpty: {e}"))?;

    let exe_path = resolve_sidecar_path(sidecar)?;
    let mut cmd = CommandBuilder::new(exe_path);
    for arg in args {
        cmd.arg(arg);
    }
    // PYTHONUNBUFFERED + FORCE_COLOR — same rule as `cli::rerw_run`,
    // applies to both rerw-in-PTY and Frida spawns. PRP §"caveats:
    // FORCE_COLOR=1 and PYTHONUNBUFFERED=1 on every spawn".
    cmd.env("PYTHONUNBUFFERED", "1");
    cmd.env("FORCE_COLOR", "1");

    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn: {e}"))?;
    let killer = child.clone_killer();
    let reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("clone_reader: {e}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take_writer: {e}"))?;

    drop(pair.slave);

    Ok(SpawnedChild {
        child,
        reader,
        writer,
        killer,
        master: pair.master,
    })
}

/// Locate a sidecar binary at runtime. Tries the bundled location (next
/// to the main exe) first, then falls back to the dev-mode location at
/// `<src-tauri>/binaries/<name>-<triple><suffix>`.
fn resolve_sidecar_path(name: &str) -> Result<PathBuf, String> {
    let triple = if cfg!(target_os = "linux") {
        "x86_64-unknown-linux-gnu"
    } else if cfg!(target_os = "windows") {
        "x86_64-pc-windows-msvc"
    } else {
        return Err(format!("unsupported target_os: {}", std::env::consts::OS));
    };
    let suffix = if cfg!(windows) { ".exe" } else { "" };
    let filename = format!("{name}-{triple}{suffix}");

    let exe_dir = std::env::current_exe()
        .map_err(|e| format!("current_exe: {e}"))?
        .parent()
        .ok_or("current_exe has no parent")?
        .to_path_buf();

    // Bundled: next to the main exe.
    let bundled = exe_dir.join(&filename);
    if bundled.is_file() {
        return Ok(bundled);
    }

    // Dev: src-tauri/binaries/<filename>. exe_dir in dev is
    // <repo>/app/ravensmith/src-tauri/target/debug — go up two levels.
    let dev = exe_dir
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.join("binaries").join(&filename));
    if let Some(p) = dev {
        if p.is_file() {
            return Ok(p);
        }
    }

    Err(format!("sidecar not found: {filename}"))
}

fn spawn_reader_task(app: AppHandle, mut reader: Box<dyn Read + Send>) {
    tauri::async_runtime::spawn_blocking(move || {
        let mut buf = [0u8; 4096];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break, // EOF: child closed PTY
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buf[..n]).into_owned();
                    let _ = app.emit(
                        "terminal-output",
                        TerminalOutput {
                            stream: "pty",
                            data,
                        },
                    );
                }
                Err(_) => break, // pty closed or other I/O failure
            }
        }
    });
}

fn spawn_wait_task(
    app: AppHandle,
    mt: SharedTerminal,
    mut child: Box<dyn portable_pty::Child + Send + Sync>,
) {
    tauri::async_runtime::spawn_blocking(move || {
        let exit = child.wait().ok();
        let exit_code = exit.map(|s| s.exit_code() as i32);

        // Hop back into async to update Mutex-guarded state.
        tauri::async_runtime::spawn(async move {
            let _ = app.emit("terminal-exit", TerminalExit { code: exit_code });

            let mut s = mt.state.lock().await;
            let was_swapping = s.state == State::Swapping;
            let pending = s.pending_mode_swap.take();
            let old_mode = s.mode;
            s.last_exit_code = exit_code;

            let snap = if was_swapping {
                if let Some(new_mode) = pending {
                    s.mode = new_mode;
                    s.state = State::Idle;
                    let snap = s.clone();
                    drop(s);
                    emit_app(
                        &app,
                        format!(
                            "── switched mode: {} → {} ──\n",
                            old_mode.as_str(),
                            new_mode.as_str()
                        ),
                    );
                    snap
                } else {
                    // Defensive: swapping with no target — degrade to Exited.
                    s.state = State::Exited;
                    let snap = s.clone();
                    drop(s);
                    snap
                }
            } else {
                s.state = State::Exited;
                let snap = s.clone();
                drop(s);
                snap
            };

            emit_state(&app, &snap);

            // Clear resources after state transition.
            *mt.killer.lock().await = None;
            *mt.writer.lock().await = None;
            *mt.master.lock().await = None;
        });
    });
}

// ---------------------------------------------------------------------------
// Event helpers

pub fn emit_app(app: &AppHandle, data: String) {
    let _ = app.emit(
        "terminal-output",
        TerminalOutput {
            stream: "app",
            data,
        },
    );
}

fn emit_state(app: &AppHandle, snap: &TerminalState) {
    let _ = app.emit("terminal-state", snap);
}

/// Public hook called from `lib.rs` on `WindowEvent::CloseRequested`.
/// Best-effort kill of the running child so app shutdown does not leak
/// an orphan sidecar. PRP-7 acceptance: "App close terminates a running
/// child."
pub fn kill_on_close(mt: &ManagedTerminal) {
    if let Ok(mut killer_slot) = mt.killer.try_lock() {
        if let Some(mut k) = killer_slot.take() {
            let _ = k.kill();
        }
    }
}
