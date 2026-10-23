import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Mounting .vue components in tests needs the same plugin the app build uses.
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(rootDir, 'src/mainview'),
      '@core': path.resolve(rootDir, 'src/core'),
      '@platforms': path.resolve(rootDir, 'src/platforms'),
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
});
