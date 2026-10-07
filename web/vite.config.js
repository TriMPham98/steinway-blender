import fs from "fs";
import { defineConfig } from "vite";

// Decoded size of the served model, for the loading bar (see main.js MODEL_BYTES).
// scripts/compress-model.mjs runs before dev/build, so the file exists by now.
const MODEL_PATH = "public/models/steinway.min.glb";
const modelBytes = fs.existsSync(MODEL_PATH) ? fs.statSync(MODEL_PATH).size : 0;

// Only the compressed derivative is served; don't ship the raw Blender exports.
const RAW_MODELS = ["models/steinway.glb", "models/steinway_keys.glb"];

export default defineConfig({
  root: ".",
  base: "./",
  publicDir: "public",
  define: {
    __MODEL_BYTES__: JSON.stringify(modelBytes),
  },
  server: {
    port: 5173,
    open: true,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  plugins: [
    {
      name: "strip-raw-models",
      apply: "build",
      closeBundle() {
        for (const f of RAW_MODELS) fs.rmSync(`dist/${f}`, { force: true });
      },
    },
  ],
});
