/// <reference types="vitest/config" />
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

// Relative asset paths: the same build serves from GitHub Pages (/manc/) and from `manc ui` (/).
export default defineConfig({
  base: "./",
  plugins: [vue()],
  build: { chunkSizeWarningLimit: 1500 }, // plotly.js alone is over a megabyte
  test: { include: ["src/tests/**/*.test.ts"] },
});
