#!/usr/bin/env node
/**
 * Derive the web-served models from the Blender exports:
 *   public/models/steinway.glb      →  public/models/steinway.min.glb
 *   public/models/carnegie_hall.glb →  public/models/carnegie_hall.min.glb (optional)
 *
 * Geometry is meshopt-compressed WITHOUT position quantization, so vertex positions are
 * bit-identical to the export. That matters here: the viewer's z-fight fixes
 * (scene-utils.js) depend on sub-millimetre offsets, edit positions in place,
 * and the keys pivot on their node origins — quantize() would rewrite node
 * transforms and snap vertices to a grid. Meshes are only reordered for better
 * compression (same triangles), never merged, welded or simplified, so every
 * node name, extras tag and material the viewer looks up survives.
 *
 * Textures are re-encoded as WebP (EXT_texture_webp).
 *
 * Skips work when the output is newer than the input; pass --force to rebuild.
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { NodeIO } from "@gltf-transform/core";
import { ALL_EXTENSIONS, EXTMeshoptCompression } from "@gltf-transform/extensions";
import { quantize, reorder, textureCompress } from "@gltf-transform/functions";
import { MeshoptDecoder, MeshoptEncoder } from "meshoptimizer";
import sharp from "sharp";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const models = path.join(webRoot, "public", "models");
const force = process.argv.includes("--force");

const JOBS = [
  { name: "steinway", required: true },
  // The hall is optional: without it the viewer keeps the studio floor. It
  // has no pivots or sub-mm offsets, so positions (16-bit over the whole
  // room, < 1 mm steps), normals and baked-light colours are quantized
  // (KHR_mesh_quantization); UVs stay float.
  { name: "carnegie_hall", required: false, quantizeAttributes: true },
];

await MeshoptEncoder.ready;
await MeshoptDecoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({
    "meshopt.encoder": MeshoptEncoder,
    "meshopt.decoder": MeshoptDecoder,
  });

for (const job of JOBS) {
  const src = path.join(models, `${job.name}.glb`);
  const dst = path.join(models, `${job.name}.min.glb`);
  if (!fs.existsSync(src)) {
    if (job.required) {
      console.error(`[compress-model] missing ${path.relative(webRoot, src)} — export it from Blender first`);
      process.exit(1);
    }
    console.warn(`[compress-model] no ${path.relative(webRoot, src)} — skipping`);
    continue;
  }
  if (
    !force &&
    fs.existsSync(dst) &&
    fs.statSync(dst).mtimeMs >= fs.statSync(src).mtimeMs
  ) {
    console.log(`[compress-model] ${path.relative(webRoot, dst)} is up to date`);
    continue;
  }
  await compress(src, dst, job);
}

async function compress(src, dst, job) {
  const t0 = Date.now();
  const doc = await io.read(src);
  if (job.quantizeAttributes) {
    await doc.transform(
      quantize({
        pattern: /^(POSITION|NORMAL|COLOR_0)$/,
        quantizationVolume: "scene",
        quantizePosition: 16,
        quantizeNormal: 8,
        quantizeColor: 12,
      }),
    );
  }
  await doc.transform(
    reorder({ encoder: MeshoptEncoder, target: "size" }),
    textureCompress({ encoder: sharp, targetFormat: "webp", quality: 90 }),
  );
  doc
    .createExtension(EXTMeshoptCompression)
    .setRequired(true)
    // QUANTIZE = plain meshopt byte codec, no lossy filters. Since we never call
    // quantize(), attributes stay float32 and decode losslessly.
    .setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.QUANTIZE });

  const tmp = `${dst}.tmp`;
  fs.writeFileSync(tmp, await io.writeBinary(doc));
  fs.renameSync(tmp, dst);

  const mb = (f) => (fs.statSync(f).size / 1e6).toFixed(1);
  console.log(
    `[compress-model] ${path.basename(src)}: ${mb(src)} MB → ${mb(dst)} MB (${((Date.now() - t0) / 1000).toFixed(1)}s)`,
  );
}
