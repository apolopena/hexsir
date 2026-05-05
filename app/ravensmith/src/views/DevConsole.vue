<script setup lang="ts">
// Superpowers-only view. Lazy-imported from router.ts when __SUPERPOWERS__
// is true, so the default-build chunk graph never reaches xterm or the
// Frida-related utilities.
//
// V1: placeholder. Wiring to xterm.js + the terminal_* commands lands in
// the PTY-backend commit (PRP-7 step 13/15).
</script>

<template>
  <section class="p-6">
    <h2 class="text-xl font-semibold mb-4">Dev Console</h2>
    <p class="text-slate-400">xterm.js terminal wiring pending.</p>
  </section>
</template>
