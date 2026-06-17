/**
 * Regression check: overlay dedupe must not carve the soundboard crown.
 * Run against a live dev server: node scripts/verify-soundboard.mjs [url]
 */
import { chromium } from "playwright";

const url = process.argv[2] || "http://localhost:5173/";
const MIN_TRIS = 800; // full Cube016_5 export is ~860
const MIN_CROWN_UP_FRAC = 0.25; // crowned top is ~33% of up-facing faces

const b = await chromium.launch({
  args: ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist"],
});
const p = await b.newPage();
await p.goto(url, { waitUntil: "networkidle" });
await p.waitForTimeout(8000);

const stats = await p.evaluate(() => {
  const model = window.__model;
  if (!model) return { error: "window.__model missing (DEV only)" };

  const applyMw = (x, y, z, e) => ({
    x: e[0] * x + e[4] * y + e[8] * z + e[12],
    y: e[1] * x + e[5] * y + e[9] * z + e[13],
    z: e[2] * x + e[6] * y + e[10] * z + e[14],
  });
  const cross = (ax, ay, az, bx, by, bz) => ({
    x: ay * bz - az * by,
    y: az * bx - ax * bz,
    z: ax * by - ay * bx,
  });
  const len = (v) => Math.hypot(v.x, v.y, v.z);

  const ps = model.getObjectByName("Piano_Static");
  let sb = null;
  ps?.traverse((o) => {
    if (!o.isMesh || sb) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    if (mats.some((m) => m?.name === "2B_Wood_Beech_mqm")) sb = o;
  });
  if (!sb) return { error: "soundboard mesh not found" };

  const geo = sb.geometry;
  const pos = geo.attributes.position;
  const idx = geo.index;
  sb.updateMatrixWorld(true);
  const e = sb.matrixWorld.elements;

  const upY = [];
  for (let t = 0; t < idx.count; t += 3) {
    const ia = idx.getX(t);
    const ib = idx.getX(t + 1);
    const ic = idx.getX(t + 2);
    const a = applyMw(pos.getX(ia), pos.getY(ia), pos.getZ(ia), e);
    const b = applyMw(pos.getX(ib), pos.getY(ib), pos.getZ(ib), e);
    const c = applyMw(pos.getX(ic), pos.getY(ic), pos.getZ(ic), e);
    const ab = { x: b.x - a.x, y: b.y - a.y, z: b.z - a.z };
    const ac = { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z };
    const n = cross(ab.x, ab.y, ab.z, ac.x, ac.y, ac.z);
    const nl = len(n);
    if (!nl || n.y / nl <= 0.7) continue;
    upY.push((a.y + b.y + c.y) / 3);
  }

  upY.sort((x, y) => x - y);
  const topCut = upY[Math.floor(upY.length * 0.67)] ?? upY[upY.length - 1];
  const crownUp = upY.filter((y) => y >= topCut).length;

  return {
    mesh: sb.name,
    tris: idx.count / 3,
    upFaces: upY.length,
    crownUpFrac: crownUp / upY.length,
  };
});

await b.close();

if (stats.error) {
  console.error(`[verify-soundboard] ${stats.error}`);
  process.exit(1);
}

const ok = stats.tris >= MIN_TRIS && stats.crownUpFrac >= MIN_CROWN_UP_FRAC;

console.log("[verify-soundboard]", stats);
if (!ok) {
  console.error(
    `[verify-soundboard] FAIL — tris=${stats.tris} (min ${MIN_TRIS}), ` +
      `crownUpFrac=${stats.crownUpFrac.toFixed(3)} (min ${MIN_CROWN_UP_FRAC})`,
  );
  process.exit(1);
}
console.log("[verify-soundboard] OK");