import { defineConfig } from "vite"; 
import path from "path"; 

export default defineConfig({ 
  server: { 
    port: 7777, 
    host: "0.0.0.0", 
    proxy: { 
      "/api": {
        target: "http://localhost:9050",
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: "ws://localhost:9050",
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
