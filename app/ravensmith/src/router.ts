import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
import BuildTester from "./views/BuildTester.vue";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "build-tester", component: BuildTester },
];

if (__SUPERPOWERS__) {
  // Dynamic import keeps DevConsole + xterm out of the default bundle.
  // The function form is the load-bearing tree-shake signal for Rollup —
  // replacing this with an eager `import` would break the chunk-graph
  // contract.
  routes.push({
    path: "/dev",
    name: "dev-console",
    component: () => import("./views/DevConsole.vue"),
  });
  // Single-purpose Frida-PTY smoke harness (PRP-7 step 14). Deleted in
  // C6 when the real Dev Console replaces it; exists only to prove
  // PTY+Frida fit before mode-swap UI complicates debugging.
  routes.push({
    path: "/smoke",
    name: "smoke",
    component: () => import("./views/Smoke.vue"),
  });
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
