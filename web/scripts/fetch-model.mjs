#!/usr/bin/env node
/**
 * Ensure public/models/steinway.glb is the real binary (not a Git LFS pointer).
 * Vercel clones do not always hydrate LFS objects; download from GitHub media CDN.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const modelPath = path.join(webRoot, "public", "models", "steinway.glb");
const DEFAULT_URL =
  "https://media.githubusercontent.com/media/TriMPham98/steinway-blender/main/web/public/models/steinway.glb";
const MIN_BYTES = 1_000_000;

function isLfsPointer(file) {
  const head = fs.readFileSync(file, { encoding: "utf8", start: 0, end: 64 });
  return head.startsWith("version https://git-lfs.github.com/spec/v1");
}

function hasModel() {
  if (!fs.existsSync(modelPath)) return false;
  const { size } = fs.statSync(modelPath);
  if (size < MIN_BYTES) return false;
  if (isLfsPointer(modelPath)) return false;
  return true;
}

async function download(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`[fetch-model] GET ${url} → ${res.status} ${res.statusText}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  fs.mkdirSync(path.dirname(modelPath), { recursive: true });
  fs.writeFileSync(modelPath, buf);
  console.log(
    `[fetch-model] downloaded ${(buf.length / 1e6).toFixed(1)} MB → ${path.relative(webRoot, modelPath)}`,
  );
}

const url = process.env.STEINWAY_MODEL_URL?.trim() || DEFAULT_URL;

if (hasModel()) {
  const mb = (fs.statSync(modelPath).size / 1e6).toFixed(1);
  console.log(`[fetch-model] using existing model (${mb} MB)`);
} else {
  await download(url);
}