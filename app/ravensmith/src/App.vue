<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";

// Vite replaces __SUPERPOWERS__ at build time via the `define` config in
// vite.config.ts. Capture it as a top-level const so the template scope
// can reference it.
const superpowers = __SUPERPOWERS__;
</script>

<template>
  <div class="min-h-screen flex flex-col bg-slate-900 text-slate-200">
    <header class="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
      <h1 class="text-lg font-semibold">Ravensmith</h1>
    </header>

    <nav class="px-4 py-2 border-b border-slate-800 flex gap-2">
      <RouterLink
        to="/"
        class="px-3 py-1 rounded text-sm hover:bg-slate-800"
        active-class="bg-slate-800"
      >
        Build Tester
      </RouterLink>
      <RouterLink
        v-if="superpowers"
        to="/dev"
        class="px-3 py-1 rounded text-sm hover:bg-slate-800"
        active-class="bg-slate-800"
      >
        Dev Console
      </RouterLink>
    </nav>

    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>

    <footer class="px-4 py-2 border-t border-slate-800 text-xs text-slate-400">
      <span>rerw sidecar: pending wiring</span>
    </footer>
  </div>
</template>
