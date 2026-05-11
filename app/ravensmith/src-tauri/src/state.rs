//! Managed state for the Dev Console terminal (Superpowers only).
//!
//! The terminal module owns one `Arc<ManagedTerminal>` via `app.manage()`;
//! all `terminal_*` IPC handlers serialize through these Mutexes. Each
//! long-lived resource has its own Mutex so a brief reader-thread access
//! doesn't block a kill from another task — PRP-7 §"Tauri Backend Contract
//! → State synchronization": one Mutex per long-lived resource, never
//! hold a lock across `await` on long-running I/O.

use std::io::Write;

use portable_pty::{ChildKiller, MasterPty};
use serde::Serialize;
use tauri::async_runtime::Mutex;

/// Active console mode. Persisted in `TerminalState`; the frontend's
/// segmented control reads this via `terminal_get_state`.
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Rerw,
    Frida,
}

impl Mode {
    pub fn as_str(&self) -> &'static str {
        match self {
            Mode::Rerw => "rerw",
            Mode::Frida => "frida",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "rerw" => Some(Mode::Rerw),
            "frida" => Some(Mode::Frida),
            _ => None,
        }
    }
}

/// Lifecycle state. PRP-7 §"Console mode swap" defines the transitions.
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum State {
    Idle,
    Starting,
    Running,
    Swapping,
    Stopping,
    Exited,
}

impl State {
    pub fn as_str(&self) -> &'static str {
        match self {
            State::Idle => "idle",
            State::Starting => "starting",
            State::Running => "running",
            State::Swapping => "swapping",
            State::Stopping => "stopping",
            State::Exited => "exited",
        }
    }

    /// Busy states reject `terminal_set_mode`, `terminal_stop`, and
    /// `terminal_restart` with `Err` — never an `app`-stream emit, since
    /// double-reporting on both channels would duplicate the error in the UI.
    pub fn is_busy(&self) -> bool {
        matches!(self, State::Starting | State::Stopping | State::Swapping)
    }
}

/// Snapshot returned to the frontend by `terminal_get_state` and emitted
/// inside `terminal-state` events. Mirrors the IPC contract in PRP-7
/// §"IPC Boundary → Dev Console".
#[derive(Debug, Clone, Serialize)]
pub struct TerminalState {
    pub mode: Mode,
    pub state: State,
    pub selected_script: Option<String>,
    pub last_exit_code: Option<i32>,
    /// When `state == Swapping`, this carries the target mode the
    /// completion path will switch into. Cleared on successful swap or
    /// 5-second polling-timeout demotion.
    #[serde(skip)]
    pub pending_mode_swap: Option<Mode>,
}

impl Default for TerminalState {
    fn default() -> Self {
        Self {
            // Frida default reflects the primary Superpowers use case
            // (PRP-7 §"Implementation Plan step 13"): the dev console
            // exists for Frida work; rerw-via-CLI work has the Build
            // Tester wizard.
            mode: Mode::Frida,
            state: State::Idle,
            selected_script: None,
            last_exit_code: None,
            pending_mode_swap: None,
        }
    }
}

/// All long-lived child-process resources owned by the Dev Console.
/// Stored behind `app.manage()` as a single value; the inner Mutexes
/// scope contention to the resource that actually changes.
pub struct ManagedTerminal {
    pub state: Mutex<TerminalState>,
    /// Last known terminal dimensions (cols, rows). Survives mode swap
    /// per PRP-7 §"Console mode swap → Resize state survives a swap".
    pub size: Mutex<(u16, u16)>,
    /// Killer cloned via `ChildKiller::clone_killer()` at spawn — lives
    /// in a separate task than the wait loop so kill can be invoked
    /// without coordinating with the waiter.
    pub killer: Mutex<Option<Box<dyn ChildKiller + Send + Sync>>>,
    /// Master PTY writer. `terminal_write_input` borrows briefly to post
    /// bytes; never held across an await.
    pub writer: Mutex<Option<Box<dyn Write + Send>>>,
    /// Master PTY handle. Kept around for `resize()`; dropped when the
    /// child exits (next spawn replaces it).
    pub master: Mutex<Option<Box<dyn MasterPty + Send>>>,
    /// Soft-fail messages queued during `setup()` that should flush onto
    /// the `app` stream on the first `terminal-state` emit. PRP-7
    /// §"Implementation Plan step 13": the bundled-rw_lab.js soft-fail
    /// path stashes its warning here so a missing resource never panics
    /// `setup`.
    pub pending_app_messages: Mutex<Vec<String>>,
}

impl Default for ManagedTerminal {
    fn default() -> Self {
        Self {
            state: Mutex::new(TerminalState::default()),
            size: Mutex::new((24, 80)),
            killer: Mutex::new(None),
            writer: Mutex::new(None),
            master: Mutex::new(None),
            pending_app_messages: Mutex::new(Vec::new()),
        }
    }
}
