import { invoke } from "@tauri-apps/api/core";

/** Mirror of `cli::CommandResult` in src-tauri/src/cli.rs. */
export interface CommandResult {
  stdout: string;
  stderr: string;
  exit_code: number;
}

/**
 * Run the bundled `rerw` sidecar as a single short-lived invocation.
 * Streams output is buffered and returned as `{ stdout, stderr, exit_code }`
 * once the child terminates (or `Err` if it times out).
 *
 * Default timeout is 30 s; pass `timeoutMs` to override.
 */
export async function rerwRun(
  args: string[],
  timeoutMs?: number,
): Promise<CommandResult> {
  // Snake_case keys match the Rust command parameter names verbatim — Tauri
  // v2's #[tauri::command] uses serde's default field naming (no rename),
  // so frontend keys must mirror the Rust function signature exactly.
  return invoke<CommandResult>("rerw_run", {
    args,
    timeout_ms: timeoutMs ?? null,
  });
}
