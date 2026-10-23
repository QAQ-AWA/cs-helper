import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: path.resolve(rootDir, 'src/mainview'),
  base: './',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(rootDir, 'src/mainview'),
      '@app-icon': path.resolve(rootDir, 'src/mainview/assets/icons/app-icon.svg'),
      '@assets': path.resolve(rootDir, 'src/mainview/assets'),
      '@core': path.resolve(rootDir, 'src/core'),
      '@platforms': path.resolve(rootDir, 'src/platforms'),
      // 回放渲染核与手机端共用同一份文件，避免两份实现漂移。
      '@shared': path.resolve(rootDir, '../server/static'),
    },
  },
  build: {
    outDir: path.resolve(rootDir, 'dist'),
    emptyOutDir: true,
    // Tauri loads assets locally; main chunk routinely exceeds Vite's 500 kB web default.
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      input: {
        main: path.resolve(rootDir, 'src/mainview/index.html'),
      },
    },
  },
  clearScreen: false,
  server: {
    strictPort: true,
    port: 5173,
    fs: {
      // 允许读取仓库根下的 server/static
      allow: [rootDir, path.resolve(rootDir, '..')],
    },
  },
});
