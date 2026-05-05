/// <reference types="vite/client" />

declare const __SUPERPOWERS__: boolean;

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
