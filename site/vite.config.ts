/// <reference types="vitest/config" />
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// Relative asset paths: the build serves from wherever `manc api` mounts it. In development
// the API paths are proxied to a local `manc api`, so the page is same-origin there too.
const API = "http://localhost:8888";

export default defineConfig({
  base: "./",
  plugins: [vue()],
  build: { chunkSizeWarningLimit: 1500 }, // plotly.js alone is over a megabyte
  server: { proxy: { "/api": API, "/health": API } },
  test: { include: ["src/tests/**/*.test.ts"] },
});
