/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<object, object, unknown>;
  export default component;
}

declare module '@app-icon' {
  const content: string;
  export default content;
}

/** 构建期注入的 package.json 版本（vite define）。 */
declare const __APP_VERSION__: string;
