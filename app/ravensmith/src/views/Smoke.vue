<script setup lang="ts">
// PRP-7 Step 14 — PTY-Frida smoke gate.
//
// Bare xterm.js + Start/Stop pair bound to terminal_start / terminal_stop
// and the existing terminal-output event channel. Exists to prove the
// PTY+Frida combination is fit for purpose before the surrounding Dev
// Console UI is built. Deleted in C6 when the real Dev Console replaces
// it.
//
// Default mode at backend startup is Frida with bundled rw_lab.js
// pre-selected, so clicking Start spawns Frida directly without first
// calling terminal_set_mode — exactly what the gate exercises.

import { onMounted, onUnmounted, ref, useTemplateRef } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";

interface TerminalOutputPayload {
  stream: "pty" | "app";
  data: string;
}

interface TerminalStatePayload {
  mode: "rerw" | "frida";
  state: string;
  selected_script: string | null;
  last_exit_code: number | null;
}

const containerRef = useTemplateRef<HTMLDivElement>("container");
const stateLabel = ref("idle");
const modeLabel = ref<"rerw" | "frida">("frida");
const scriptLabel = ref<string | null>(null);

let term: Terminal | null = null;
let fit: FitAddon | null = null;
const unlisten: UnlistenFn[] = [];

onMounted(async () => {
  if (!containerRef.value) return;

  term = new Terminal({
    cursorBlink: true,
    fontFamily: "var(--font-mono, monospace)",
    fontSize: 13,
    theme: { background: "#0f172a", foreground: "#e5e7eb" },
  });
  fit = new FitAddon();
  term.loadAddon(fit);
  term.open(containerRef.value);
  fit.fit();

  // Forward keystrokes back into the PTY via terminal_write_input.
  term.onData((data) => {
    invoke("terminal_write_input", { data }).catch(() => {});
  });

  // Send initial dimensions so the spawn reads non-default cols/rows.
  invoke("terminal_resize", {
    cols: term.cols,
    rows: term.rows,
  }).catch(() => {});

  unlisten.push(
    await listen<TerminalOutputPayload>("terminal-output", (e) => {
      if (!term) return;
      // CRLF normalization (idempotent — handles LF-only AND existing CRLF
      // without doubling, per PRP §caveats: Stream-into-xterm CR/LF).
      term.write(e.payload.data.replace(/\r?\n/g, "\r\n"));
    }),
  );

  unlisten.push(
    await listen<TerminalStatePayload>("terminal-state", (e) => {
      stateLabel.value = e.payload.state;
      modeLabel.value = e.payload.mode;
      scriptLabel.value = e.payload.selected_script;
    }),
  );

  // Pull initial state so the labels render before any event fires.
  try {
    const snap = await invoke<TerminalStatePayload>("terminal_get_state");
    stateLabel.value = snap.state;
    modeLabel.value = snap.mode;
    scriptLabel.value = snap.selected_script;
  } catch {
    /* noop */
  }

  window.addEventListener("resize", onWindowResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onWindowResize);
  for (const u of unlisten) u();
  term?.dispose();
});

function onWindowResize() {
  fit?.fit();
  if (term) {
    invoke("terminal_resize", { cols: term.cols, rows: term.rows }).catch(
      () => {},
    );
  }
}

async function start() {
  try {
    await invoke("terminal_start", { args: [] });
  } catch (err) {
    term?.write(`\r\n[smoke] start failed: ${err}\r\n`);
  }
}

async function stop() {
  try {
    await invoke("terminal_stop");
  } catch (err) {
    term?.write(`\r\n[smoke] stop failed: ${err}\r\n`);
  }
}
</script>

<template>
  <section class="p-4 flex flex-col h-full gap-3">
    <header class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">PTY-Frida smoke harness</h2>
      <div class="text-xs text-slate-400 font-mono">
        mode={{ modeLabel }} · state={{ stateLabel }}
        <span v-if="scriptLabel"> · {{ scriptLabel }}</span>
      </div>
    </header>

    <div class="flex gap-2">
      <button
        type="button"
        class="px-3 py-1 rounded border border-emerald-700 bg-emerald-700/20 text-emerald-200 text-sm hover:bg-emerald-700/40"
        @click="start"
      >
        Start
      </button>
      <button
        type="button"
        class="px-3 py-1 rounded border border-rose-700 bg-rose-700/20 text-rose-200 text-sm hover:bg-rose-700/40"
        @click="stop"
      >
        Stop
      </button>
    </div>

    <div ref="container" class="flex-1 min-h-0 border border-slate-700 rounded p-2"></div>

    <p class="text-xs text-slate-500">
      Default mode is Frida with bundled <code>rw_lab.js</code> pre-selected.
      Launch <code>Ravenswatch.exe</code> via Steam first, then click Start.
    </p>
  </section>
</template>
