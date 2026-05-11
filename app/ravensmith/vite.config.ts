import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { visualizer } from "rollup-plugin-visualizer";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

// Vite's loadEnv() reads .env* files only — it does NOT read process.env.
// The just recipe sets VITE_SUPERPOWERS=true inline before invoking
// `bun run tauri dev`, which propagates as a process env var, so we must
// read process.env directly here. Vite docs explicitly state: "Environment
// variables available while the config itself is being evaluated are only
// those that already exist in the current process environment (process.env).
// Vite deliberately defers loading any .env* files until after the user
// config has been resolved."
// @ts-expect-error process is a nodejs global
const superpowers = process.env.VITE_SUPERPOWERS === "true";

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [
    vue(),
    tailwindcss(),
    // Emits dist/stats.html and dist/stats.json on every build.
    // Acceptance asserts that the default-build stats.json contains no
    // @xterm/xterm modules; the bundle visualizer is the load-bearing gate
    // (raw `grep '@xterm' dist/assets/*.js` is unreliable since
    // Vite/Rollup transforms import strings away).
    // rollup-plugin-visualizer 5.13.x dropped the `json: true` shorthand
    // in favor of a separate `template: "raw-data"` invocation — emit
    // both files via two plugin instances.
    visualizer({
      filename: "dist/stats.html",
      template: "treemap",
      emitFile: false,
      gzipSize: true,
    }),
    visualizer({
      filename: "dist/stats.json",
      template: "raw-data",
      emitFile: false,
      gzipSize: true,
    }),
  ],

  define: {
    __SUPERPOWERS__: JSON.stringify(superpowers),
  },

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
