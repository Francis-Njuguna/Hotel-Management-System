import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';

const backend = process.env.HMS_API_TARGET || 'http://127.0.0.1:8017';
export default defineConfig({
  plugins: [react(), tailwind()],
  server: { host: '127.0.0.1', port: 5187, strictPort: true, proxy: { '/api': backend } },
  test: { environment: 'jsdom', globals: true, maxWorkers: 2, testTimeout: 15000, setupFiles: ['./src/test/setup.ts'], include: ['src/**/*.{test,spec}.{ts,tsx}'] },
});
