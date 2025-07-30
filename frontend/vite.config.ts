import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import * as path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "./src"),
    },
  },
  server: {
    port: 7777,
    host: '0.0.0.0',
    cors: true,
    proxy: {
      '/api': {
        target: 'http://localhost:9050',
        changeOrigin: true,
        secure: false,
        configure: (proxy, options) => {
          proxy.on('error', (err) => {
            console.log('proxy error', err);
          });
          proxy.on('proxyReq', (_proxyReq, req) => {
            console.log('Proxying:', req.method, req.url, '→', options.target);
          });
        },
      },
      '/ws': {
        target: 'ws://localhost:9050',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
