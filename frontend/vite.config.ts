import { defineConfig } from "vite";
import path from "path";
import { VitePWA } from "vite-plugin-pwa";

const backendUrl = process.env.VITE_BACKEND_URL || "http://localhost:9050";

export default defineConfig({
  plugins: [
    VitePWA({
      // "prompt" (not autoUpdate) so a freshly-deployed service worker
      // parks in the waiting state instead of taking over the page. The
      // PWAUpdate component decides WHEN to activate it (via updateSW(true)),
      // which it defers while a recording is in progress — applying a new
      // SW mid-capture can swap cached chunks out from under an active
      // recording. See src/components/PWAUpdate.tsx.
      registerType: "prompt",
      injectRegister: "auto",
      manifest: false,
      includeAssets: [
        "manifest.webmanifest",
        "icons/icon-192.png",
        "icons/icon-512.png",
        "icons/icon-512-maskable.png",
        "icons/apple-touch-icon.png",
        "vite.svg",
      ],
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,webmanifest,woff,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/ws\//, /^\/oauth2\//, /^\/realms\//],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        // skipWaiting stays false so the new SW waits until PWAUpdate
        // explicitly tells it to activate (never mid-recording). clientsClaim
        // still applies on that deferred activation so the reload picks up
        // the new SW immediately.
        skipWaiting: false,
        maximumFileSizeToCacheInBytes: 6 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: ({ url, request }) =>
              request.method === "GET" &&
              (url.pathname === "/api/auth/me" || url.pathname === "/api/system/pipeline"),
            handler: "NetworkFirst",
            options: {
              cacheName: "meet-ops-api-getters",
              networkTimeoutSeconds: 4,
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 32, maxAgeSeconds: 60 * 5 },
            },
          },
          {
            urlPattern: ({ url, request }) =>
              request.method === "GET" &&
              url.pathname.startsWith("/api/") &&
              !url.pathname.startsWith("/api/uploads"),
            handler: "NetworkFirst",
            options: {
              cacheName: "meet-ops-api-read",
              networkTimeoutSeconds: 4,
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 64, maxAgeSeconds: 60 * 60 },
            },
          },
          {
            urlPattern: ({ request }) => request.destination === "image",
            handler: "CacheFirst",
            options: {
              cacheName: "meet-ops-images",
              cacheableResponse: { statuses: [0, 200] },
              expiration: { maxEntries: 64, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
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
