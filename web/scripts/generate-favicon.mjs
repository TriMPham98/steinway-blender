/**
 * Rasterize public/favicon.svg → favicon.ico, PNG sizes, apple-touch-icon.
 * Requires: npm install (sharp, to-ico are devDependencies).
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import toIco from "to-ico";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const publicDir = join(root, "public");
const svg = readFileSync(join(publicDir, "favicon.svg"));

const png16 = await sharp(svg).resize(16, 16).png().toBuffer();
const png32 = await sharp(svg).resize(32, 32).png().toBuffer();
const png180 = await sharp(svg).resize(180, 180).png().toBuffer();

writeFileSync(join(publicDir, "favicon.ico"), await toIco([png16, png32]));
writeFileSync(join(publicDir, "favicon-32.png"), png32);
writeFileSync(join(publicDir, "apple-touch-icon.png"), png180);

console.log("Wrote public/favicon.ico, favicon-32.png, apple-touch-icon.png");