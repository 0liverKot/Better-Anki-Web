import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// In development, run the backend on :8000 and open the Vite dev server (:5173).
const backend = process.env.BAW_BACKEND ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/api': backend,
      '/media': backend,
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
