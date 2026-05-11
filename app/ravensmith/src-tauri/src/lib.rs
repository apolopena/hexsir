mod cli;

#[cfg(feature = "superpowers")]
mod state;

#[cfg(feature = "superpowers")]
mod terminal;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init());

    #[cfg(not(feature = "superpowers"))]
    let builder = builder.invoke_handler(tauri::generate_handler![cli::rerw_run]);

    #[cfg(feature = "superpowers")]
    let builder = builder
        .setup(|app| {
            use std::sync::Arc;
            use tauri::Manager;
            use tauri::path::BaseDirectory;

            let mut mt = state::ManagedTerminal::default();

            // Bundled rw_lab.js soft-fail (PRP §"Implementation Plan
            // step 13"). Resolve through Tauri's resource path API; on
            // resolve error or missing file, leave selected_script as
            // None and queue a pending app-stream warning. Never
            // ?-propagate from setup — a setup error panics with no
            // visible UI, the worst dev-experience failure mode in the
            // proposal.
            let resolved = app
                .path()
                .resolve("resources/rw_lab.js", BaseDirectory::Resource);
            match resolved {
                Ok(path) if path.exists() => {
                    mt.state.get_mut().selected_script =
                        Some(path.to_string_lossy().into_owned());
                }
                Ok(path) => {
                    mt.pending_app_messages.get_mut().push(format!(
                        "[ravensmith] bundled rw_lab.js not found at {}; pick one via Frida > Open Script…\n",
                        path.display()
                    ));
                }
                Err(e) => {
                    mt.pending_app_messages.get_mut().push(format!(
                        "[ravensmith] failed to resolve bundled rw_lab.js: {e}; pick one via Frida > Open Script…\n"
                    ));
                }
            }

            app.manage::<terminal::SharedTerminal>(Arc::new(mt));
            Ok(())
        })
        .on_window_event(|window, event| {
            use tauri::Manager;
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let app = window.app_handle();
                if let Some(mt) = app.try_state::<terminal::SharedTerminal>() {
                    terminal::kill_on_close(mt.inner());
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            cli::rerw_run,
            terminal::terminal_get_state,
            terminal::terminal_set_mode,
            terminal::terminal_start,
            terminal::terminal_stop,
            terminal::terminal_restart,
            terminal::terminal_write_input,
            terminal::terminal_resize,
            terminal::terminal_set_frida_script,
        ]);

    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
