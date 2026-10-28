import { defineConfig } from 'vite';
import process from 'node:process';

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.PETRATERRIUM_API_URL ?? 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          react: ['react', 'react-dom'],
          'dsl-graph': ['@xyflow/react', '@dagrejs/dagre'],
        },
      },
    },
  },
});
