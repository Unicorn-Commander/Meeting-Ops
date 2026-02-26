import { defineConfig } from "vite";
import path from "path";

const backendUrl = process.env.VITE_BACKEND_URL || "http://localhost:9050";

export default defineConfig({
  server: {
    port: 7777,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: backendUrl.replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
        secure: false,
      }
    }
  }, 
  resolve: { 
    alias: { 
      "@": path.resolve(__dirname, "./src") 
    } 
  } 
});
