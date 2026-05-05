<script setup lang="ts">
import { ref } from "vue";
import { rerwRun, type CommandResult } from "../lib/api";
import { renderRerwOutput } from "../lib/rerw";
import Wizard from "../components/Wizard.vue";

const steps = [
  { title: "Choose hero" },
  { title: "Choose chapter" },
  { title: "Choose level" },
  { title: "Review" },
  { title: "Apply" },
];

type ProbeState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; result: CommandResult }
  | { kind: "timeout" }
  | { kind: "error"; message: string };

const probe = ref<ProbeState>({ kind: "idle" });

async function runProbe() {
  probe.value = { kind: "running" };
  try {
    const result = await rerwRun(["--version"]);
    probe.value = { kind: "done", result };
  } catch (err) {
    const message = String(err);
    if (message.includes("timed out")) {
      probe.value = { kind: "timeout" };
    } else {
      probe.value = { kind: "error", message };
    }
  }
}
</script>

<template>
  <section class="p-6 flex flex-col gap-6">
    <header>
      <h2 class="text-xl font-semibold">Build Tester</h2>
    </header>

    <p class="text-sm text-slate-400">
      V1 stub — placeholder steps. The Apply step is the only wired one;
      it exercises the rerw sidecar IPC pipe end-to-end.
    </p>

    <Wizard :steps="steps">
      <template #default="{ index, step }">
        <div v-if="index < 4">
          <h3 class="text-base font-medium mb-2">{{ step.title }}</h3>
          <p class="text-sm text-slate-400">Placeholder. Wizard wiring lands in a follow-up PRP.</p>
        </div>

        <div v-else>
          <h3 class="text-base font-medium mb-2">{{ step.title }}</h3>
          <p class="text-sm text-slate-400 mb-3">
            Probe step — invokes <code class="text-slate-200">rerw --version</code> through the sidecar
            and renders the result.
          </p>
          <button
            type="button"
            :disabled="probe.kind === 'running'"
            class="px-3 py-1 rounded border border-emerald-700 bg-emerald-700/20 text-emerald-200 text-sm hover:bg-emerald-700/40 disabled:opacity-40"
            @click="runProbe"
          >
            {{ probe.kind === "running" ? "Running…" : probe.kind === "done" ? "Re-run" : "Run probe" }}
          </button>

          <!-- exit_code 0, stderr empty: render stdout, no banner -->
          <div
            v-if="probe.kind === 'done' && probe.result.exit_code === 0 && !probe.result.stderr.trim()"
            class="mt-3 font-mono text-xs"
          >
            <div class="output-region" v-html="renderRerwOutput(probe.result.stdout)"></div>
          </div>

          <!-- exit_code 0, stderr non-empty: stdout, divider, stderr -->
          <div
            v-else-if="probe.kind === 'done' && probe.result.exit_code === 0"
            class="mt-3 font-mono text-xs"
          >
            <div class="output-region" v-html="renderRerwOutput(probe.result.stdout)"></div>
            <div class="my-2 border-t border-slate-700"></div>
            <div class="output-region" v-html="renderRerwOutput(probe.result.stderr)"></div>
          </div>

          <!-- exit_code non-zero: banner + stdout + stderr, Retry only -->
          <div
            v-else-if="probe.kind === 'done'"
            class="mt-3 font-mono text-xs"
          >
            <div class="px-3 py-2 mb-2 bg-rose-900/40 text-rose-200 rounded text-sm font-sans">
              rerw exited with code {{ probe.result.exit_code }}
            </div>
            <div v-if="probe.result.stdout" class="output-region" v-html="renderRerwOutput(probe.result.stdout)"></div>
            <div v-if="probe.result.stderr" class="output-region mt-2" v-html="renderRerwOutput(probe.result.stderr)"></div>
          </div>

          <!-- timeout -->
          <div v-else-if="probe.kind === 'timeout'" class="mt-3">
            <div class="px-3 py-2 bg-rose-900/40 text-rose-200 rounded text-sm">
              rerw timed out after 30 s · child killed
            </div>
          </div>

          <!-- non-timeout error path (lookup failure, spawn failure) -->
          <div v-else-if="probe.kind === 'error'" class="mt-3">
            <div class="px-3 py-2 bg-rose-900/40 text-rose-200 rounded text-sm font-mono whitespace-pre-wrap">
              {{ probe.message }}
            </div>
          </div>
        </div>
      </template>
    </Wizard>
  </section>
</template>

<style scoped>
.output-region {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
