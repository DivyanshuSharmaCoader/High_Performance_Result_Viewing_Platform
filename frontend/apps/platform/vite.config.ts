/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Platform console in development: open http://admin.localhost:5174. /api is proxied to the backend with
// the original Host header preserved (the API only serves platform routes on the admin host).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    allowedHosts: [".localhost"],
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
    chunkSizeWarningLimit: 600,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
