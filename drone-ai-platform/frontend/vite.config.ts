import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', 'VITE_');
  const backend = process.env.VITE_BACKEND_TARGET || env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000';

  return {
    envDir: '..',
    plugins: [tailwindcss(), react()],
    server: {
      host: '0.0.0.0',
      allowedHosts: true,
      proxy: {
        '/api': { target: backend, changeOrigin: true },
        '/ws': { target: backend, changeOrigin: true, ws: true },
        '/health': { target: backend, changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      setupFiles: './src/test-setup.ts',
      css: true,
    },
  };
});
