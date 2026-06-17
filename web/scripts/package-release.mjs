#!/usr/bin/env node
/**
 * Assemble a shippable folder: dist/ + models/ + README.
 * Run from web/: npm run package
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.dirname(webRoot);
const dist = path.join(webRoot, "dist");
const modelsSrc = path.join(webRoot, "public", "models");
const outDir = path.join(repoRoot, "release", "steinway-midi-piano-web");

if (!fs.existsSync(dist)) {
  console.error("Missing dist/ — run npm run build first");
  process.exit(1);
}
if (!fs.existsSync(path.join(modelsSrc, "steinway.glb"))) {
  console.error(
    "Missing public/models/steinway.glb — export from Blender:\n" +
      "  Blender --background assets/steinway_grand_playable.blend --python scripts/export_glb.py -- \\\n" +
      "    --out web/public/models/steinway.glb --with-action",
  );
  process.exit(1);
}

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const s = path.join(src, name);
    const d = path.join(dest, name);
    if (fs.statSync(s).isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

copyDir(dist, outDir);
copyDir(modelsSrc, path.join(outDir, "models"));

const readme = `# Steinway MIDI Piano (Web)

Static site — same live MIDI behavior as the Blender add-on (v0.4.2):

- Web MIDI input with port picker (Yamaha P-515 / USB-MIDI auto-detect)
- Velocity-sensitive keys (spring-damper, full press depth)
- Sustain pedal CC64 (pedal mesh only; keys are not held by sustain)
- Press angle, snappiness, velocity sensitivity

## Host anywhere

Upload this entire folder to any static host (S3, Netlify, nginx, GitHub Pages).
Open \`index.html\` via HTTPS — Web MIDI requires a secure context in most browsers.

## Local preview

\`\`\`bash
npx serve .
\`\`\`

Then open the URL shown (must be https:// or localhost for MIDI).
`;

fs.writeFileSync(path.join(outDir, "README.txt"), readme);

const glb = path.join(outDir, "models", "steinway.glb");
const mb = (fs.statSync(glb).size / 1e6).toFixed(1);
console.log(`[package] ${outDir}`);
console.log(`[package] model ${mb} MB — deploy folder as-is`);