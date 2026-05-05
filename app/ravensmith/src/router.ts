import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
import BuildTester from "./views/BuildTester.vue";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "build-tester", component: BuildTester },
];

if (__SUPERPOWERS__) {
  // Dynamic import keeps DevConsole + (eventually) xterm out of the
  // default bundle. The function form is the load-bearing tree-shake
  // signal for Rollup — replacing this with an eager `import` would
  // break the chunk-graph contract.
  routes.push({
    path: "/dev",
    name: "dev-console",
    component: () => import("./views/DevConsole.vue"),
  });
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
