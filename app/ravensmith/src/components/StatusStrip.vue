<script setup lang="ts">
import { onMounted, ref } from "vue";
import { rerwRun } from "../lib/api";

type SidecarState =
  | { kind: "checking" }
  | { kind: "resolved"; version: string }
  | { kind: "missing"; reason: string };

const sidecar = ref<SidecarState>({ kind: "checking" });

onMounted(async () => {
  try {
    const result = await rerwRun(["--version"], 5000);
    if (result.exit_code === 0) {
      sidecar.value = { kind: "resolved", version: result.stdout.trim() };
    } else {
      sidecar.value = {
        kind: "missing",
        reason: `rerw exited ${result.exit_code}: ${result.stderr.trim() || "(no stderr)"}`,
      };
    }
  } catch (err) {
    sidecar.value = { kind: "missing", reason: String(err) };
  }
});
</script>

<template>
  <div class="text-xs text-slate-400">
    <span v-if="sidecar.kind === 'checking'">rerw sidecar: checking…</span>
    <span v-else-if="sidecar.kind === 'resolved'" class="text-emerald-400">
      rerw sidecar: resolved · {{ sidecar.version }}
    </span>
    <span v-else class="text-rose-400">
      rerw sidecar: missing · {{ sidecar.reason }}
    </span>
  </div>
</template>
