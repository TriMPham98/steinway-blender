import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  base: "./",
  publicDir: "public",
  server: {
    port: 5173,
    open: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});