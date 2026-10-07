import * as THREE from "three";
import { Reflector } from "three/examples/jsm/objects/Reflector.js";

/**
 * Center model on ground and scale to a reasonable size for the viewer.
 * @returns {{ size: THREE.Vector3, center: THREE.Vector3 }}
 */
export function frameModel(root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  if (box.isEmpty()) {
    console.warn("Model bounding box is empty");
    return { size: new THREE.Vector3(1, 1, 1), center: new THREE.Vector3() };
  }

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  root.position.sub(center);
  root.updateMatrixWorld(true);

  const grounded = new THREE.Box3().setFromObject(root);
  root.position.y -= grounded.min.y;
  root.updateMatrixWorld(true);

  const maxDim = Math.max(size.x, size.y, size.z);
  if (maxDim > 2.5 && Number.isFinite(maxDim)) {
    root.scale.setScalar(2.5 / maxDim);
    root.updateMatrixWorld(true);
    // Scale is around the model origin (above the feet) — re-seat on Y=0.
    const afterScale = new THREE.Box3().setFromObject(root);
    root.position.y -= afterScale.min.y;
    root.updateMatrixWorld(true);
  }

  const finalBox = new THREE.Box3().setFromObject(root);
  return {
    size: finalBox.getSize(new THREE.Vector3()),
    center: finalBox.getCenter(new THREE.Vector3()),
  };
}

/**
 * Hand-tuned camera poses for the export layout (keyboard faces +Z).
 * If the piano is yawed, call {@link applyCameraPresetsYaw} with the same yaw
 * so every preset keeps its original relative orientation.
 */
export const CAMERA_AUTHORING = Object.freeze({
  hero: {
    position: /** @type {[number, number, number]} */ ([2.39, 1.38, 2.37]),
    target: /** @type {[number, number, number]} */ ([0, 0.74, 0.35]),
    fov: 44,
    exposure: 1.12,
  },
  front: {
    position: /** @type {[number, number, number]} */ ([0.02, 1.19, 3.08]),
    target: /** @type {[number, number, number]} */ ([0.01, 0.75, 0.03]),
    fov: 42,
  },
  top: {
    position: /** @type {[number, number, number]} */ ([0, 3.0, 1.3]),
    target: /** @type {[number, number, number]} */ ([0, 0.7, 0]),
    fov: 46,
  },
  seated: {
    position: /** @type {[number, number, number]} */ ([0.02, 1.58, 1.85]),
    target: /** @type {[number, number, number]} */ ([0.01, 0.75, 0.74]),
    fov: 42,
    exposure: 1.12,
  },
  keyboardRange: {
    position: /** @type {[number, number, number]} */ ([0.06, 1.1, 1.22]),
    target: /** @type {[number, number, number]} */ ([0.06, 0.75, 0.77]),
    fov: 40,
    exposure: 1.12,
  },
});

/** Live hero defaults (mutated by {@link applyCameraPresetsYaw}). */
export const HERO_CAMERA_DEFAULTS = {
  position: [...CAMERA_AUTHORING.hero.position],
  target: [...CAMERA_AUTHORING.hero.target],
  fov: CAMERA_AUTHORING.hero.fov,
  exposure: CAMERA_AUTHORING.hero.exposure,
};

/** Default scene lighting (tuned in scene debug). */
export const LIGHTING_DEFAULTS = {
  // Even soft showroom: most energy in ambient + hemi so the body reads flatly
  // lit without a hot key. Directionals stay modest — the open harp plate is a
  // huge flat face, and stacked keys above ~2 total direct irradiance clip gold
  // to pure white under ACES. Camera-follow lamps stay off so orbiting doesn't
  // drag a hotspot around the keys.
  ambientIntensity: 0.48,
  hemiIntensity: 0.58,
  hemiPosition: [0, 8, 0],
  ceilingIntensity: 0.26,
  ceilingPosition: [0.6, 9, 1.2],
  roomIntensity: 0.3,
  roomPosition: [-3.5, 5.5, 2.8],
  // Gentle fixed front fill (not a camera lamp).
  viewerIntensity: 0.22,
  viewerDistance: 18,
  viewerDecay: 1.4,
  viewerFollowCamera: false,
  viewerOffset: [0, 0.05, 0],
  viewerPosition: [0.2, 2.4, 2.8],
  // Wide soft key wash over the keyboard — high penumbra, low intensity.
  keySpotIntensity: 0.16,
  keySpotDistance: 16,
  keySpotAngleDeg: 62,
  keySpotPenumbra: 0.9,
  keySpotDecay: 1.2,
  keySpotFollowCamera: false,
  keySpotPosition: [0.35, 3.0, 2.4],
  keySpotTarget: [0, 0.85, 0.15],
  keySpotCamX: 0.3,
  keySpotCamY: 1.1,
  keySpotCamZMul: 0.55,
  keySpotCamZAdd: 0.35,
};

/** Snap-to preset views (mutated by {@link applyCameraPresetsYaw}). */
export const CAMERA_PRESETS = {
  hero: {
    position: [...CAMERA_AUTHORING.hero.position],
    target: [...CAMERA_AUTHORING.hero.target],
    fov: CAMERA_AUTHORING.hero.fov,
  },
  front: {
    position: [...CAMERA_AUTHORING.front.position],
    target: [...CAMERA_AUTHORING.front.target],
    fov: CAMERA_AUTHORING.front.fov,
  },
  top: {
    position: [...CAMERA_AUTHORING.top.position],
    target: [...CAMERA_AUTHORING.top.target],
    fov: CAMERA_AUTHORING.top.fov,
  },
  /** Player-at-keyboard view — used when live MIDI session starts. */
  seated: {
    position: [...CAMERA_AUTHORING.seated.position],
    target: [...CAMERA_AUTHORING.seated.target],
    fov: CAMERA_AUTHORING.seated.fov,
    exposure: CAMERA_AUTHORING.seated.exposure,
  },
  /** From the Carnegie Hall stalls (house is +X); only offered in the hall. */
  house: {
    position: [20, 5.5, -3.5],
    target: [-1, 2.2, 0],
    fov: 42,
  },
};

/**
 * Reference framing for the computer-keyboard octave range (no-MIDI mode).
 * Authoring pose is keyboard-+Z; live values track {@link applyCameraPresetsYaw}.
 */
export const KEYBOARD_RANGE_VIEW = {
  position: [...CAMERA_AUTHORING.keyboardRange.position],
  target: [...CAMERA_AUTHORING.keyboardRange.target],
  fov: CAMERA_AUTHORING.keyboardRange.fov,
  exposure: CAMERA_AUTHORING.keyboardRange.exposure,
};

/**
 * Rotate a point by yaw around world Y (right-hand).
 * R_y(yaw)·(x,y,z) = (c·x + s·z, y, −s·x + c·z)
 * @param {number} x @param {number} y @param {number} z @param {number} yaw
 * @returns {[number, number, number]}
 */
export function rotateYawPoint(x, y, z, yaw) {
  const c = Math.cos(yaw);
  const s = Math.sin(yaw);
  return [c * x + s * z, y, -s * x + c * z];
}

/**
 * Apply a piano yaw to every hand-tuned camera pose so relative framing
 * matches the pre-rotation product shot (no flipped approach axis).
 * @param {number} yaw  same value as modelRoot.rotation.y
 */
export function applyCameraPresetsYaw(yaw) {
  const copy = (src) => ({
    position: rotateYawPoint(src.position[0], src.position[1], src.position[2], yaw),
    target: rotateYawPoint(src.target[0], src.target[1], src.target[2], yaw),
    fov: src.fov,
    exposure: src.exposure,
  });

  for (const id of /** @type {const} */ (["hero", "front", "top", "seated"])) {
    const next = copy(CAMERA_AUTHORING[id]);
    CAMERA_PRESETS[id].position = next.position;
    CAMERA_PRESETS[id].target = next.target;
    CAMERA_PRESETS[id].fov = next.fov;
    if (next.exposure != null) CAMERA_PRESETS[id].exposure = next.exposure;
  }

  HERO_CAMERA_DEFAULTS.position = [...CAMERA_PRESETS.hero.position];
  HERO_CAMERA_DEFAULTS.target = [...CAMERA_PRESETS.hero.target];
  HERO_CAMERA_DEFAULTS.fov = CAMERA_PRESETS.hero.fov;
  HERO_CAMERA_DEFAULTS.exposure = CAMERA_AUTHORING.hero.exposure;

  const kb = copy(CAMERA_AUTHORING.keyboardRange);
  KEYBOARD_RANGE_VIEW.position = kb.position;
  KEYBOARD_RANGE_VIEW.target = kb.target;
  KEYBOARD_RANGE_VIEW.fov = kb.fov;
  KEYBOARD_RANGE_VIEW.exposure = kb.exposure;
}

/** Hero (¾ product) view — fixed pose after frameModel centers the piano. */
export function getHeroCameraPose(root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const radius = Math.max(box.getSize(new THREE.Vector3()).length() * 0.5, 0.6);

  const position = new THREE.Vector3(...HERO_CAMERA_DEFAULTS.position);
  const target = new THREE.Vector3(...HERO_CAMERA_DEFAULTS.target);

  return {
    position,
    target,
    fov: HERO_CAMERA_DEFAULTS.fov,
    exposure: HERO_CAMERA_DEFAULTS.exposure,
    radius,
    viewerLightPosition: position.clone().add(new THREE.Vector3(0, 0.06, 0.12)),
  };
}

/** Aim camera at the default hero framing. */
export function fitCameraToModel(camera, controls, root) {
  const pose = getHeroCameraPose(root);
  controls.target.copy(pose.target);
  camera.position.copy(pose.position);
  camera.fov = pose.fov;
  // Near-plane distance sets the floor on depth precision. The old radius/200 (≈0.01)
  // left the interior gold frame z-fighting through the thin black case; pull near out
  // to 0.08 — still well inside controls.minDistance (0.3), so nothing close clips —
  // for far more bits near the rim. far stays generous so the studio floor isn't cut.
  camera.near = Math.max(0.08, pose.radius / 30);
  camera.far = Math.max(50, pose.radius * 40);
  camera.updateProjectionMatrix();
  controls.update();
  return pose;
}

/**
 * Remove any oversized / degenerate mesh welded into the model (the original
 * asset's 30x66m Floor plane). Safety net — the export now strips it at source,
 * but this keeps old GLBs from shrinking the piano. Returns count removed.
 */
export function stripEmbeddedGround(root) {
  const remove = [];
  root.traverse((obj) => {
    if (!obj.isMesh || !obj.geometry?.attributes?.position) return;
    const geo = obj.geometry;
    if (!geo.boundingBox) geo.computeBoundingBox();
    const size = geo.boundingBox.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    if (geo.attributes.position.count <= 4 || maxDim > 5) remove.push(obj);
  });
  for (const m of remove) {
    m.parent?.remove(m);
    m.geometry?.dispose();
  }
  return remove.length;
}

const BENCH_NAMES = new Set(["Piano_Bench", "Seat Cushion", "Seat Frame"]);

function isBenchObject(obj) {
  const name = obj.name || "";
  if (BENCH_NAMES.has(name)) return true;
  if (obj.userData?.steinway_role === "bench") return true;
  if (/bench|seat cushion|seat frame/i.test(name)) return true;
  if (obj.isMesh && obj.geometry?.name === "SeatCushionSolid") return true;
  return false;
}

/** Remove bench objects (export omits them; keeps older GLBs piano-centric). */
export function stripBench(root) {
  const remove = [];
  root.traverse((obj) => {
    if (isBenchObject(obj)) remove.push(obj);
  });
  for (const obj of remove) {
    obj.parent?.remove(obj);
    obj.traverse((child) => {
      if (child.isMesh) child.geometry?.dispose();
    });
  }
  return remove.length;
}

const BENCH_LEG_NAMES = new Set(["Leg-01", "Leg-02", "Leg-03", "Leg-04"]);

function isBenchLegObject(obj) {
  const name = obj.name || "";
  if (BENCH_LEG_NAMES.has(name)) return true;
  if (obj.userData?.steinway_role === "bench_leg") return true;
  return /^leg-0[1-4]$/i.test(name);
}

/** Remove bench leg meshes only (piano legs and casters stay). */
export function stripBenchLegs(root) {
  const remove = [];
  root.traverse((obj) => {
    if (isBenchLegObject(obj)) remove.push(obj);
  });
  for (const obj of remove) {
    obj.parent?.remove(obj);
    obj.traverse((child) => {
      if (child.isMesh) child.geometry?.dispose();
    });
  }
  return remove.length;
}

function isStrayCurveObject(obj) {
  // Blender "Curve" objects skip the export's mesh-only static join, so the glTF
  // exporter tessellates them into standalone meshes (e.g. a flat gold disc that
  // floats above the case rim). No real piano part is named "Curve".
  return /^curve(\.\d+)?$/i.test(obj.name || "");
}

/** Remove stray tessellated curve objects welded into the model. Returns count removed. */
export function stripStrayCurves(root) {
  const remove = [];
  root.traverse((obj) => {
    if (isStrayCurveObject(obj)) remove.push(obj);
  });
  for (const obj of remove) {
    obj.parent?.remove(obj);
    obj.traverse((child) => {
      if (child.isMesh) child.geometry?.dispose();
    });
  }
  return remove.length;
}

const SRGB = THREE.SRGBColorSpace;
const DATA = THREE.NoColorSpace;

/** glTF color/normal/roughness maps from steinway_grand_playable export. */
function prepMaps(mat) {
  if (mat.map) mat.map.colorSpace = SRGB;
  if (mat.normalMap) mat.normalMap.colorSpace = DATA;
  if (mat.roughnessMap) mat.roughnessMap.colorSpace = DATA;
  if (mat.metalnessMap) mat.metalnessMap.colorSpace = DATA;
  if (mat.aoMap) mat.aoMap.colorSpace = DATA;
}

function lacquerFromExport(mat, { matte, lite }) {
  const shiny = !matte;
  const roughness = matte
    ? lite
      ? 0.85
      : 1.0
    : lite
      ? 0.12
      : 0.06;
  return new THREE.MeshPhysicalMaterial({
    // Blender's sy_dark lacquer is pure black; lift it a hair to a *neutral*
    // charcoal (equal RGB) so unreflected areas read as deep gray under tone
    // mapping instead of an ACES-crushed void — but with no blue bias, so the
    // body matches the neutral black of the Blender render.
    color: new THREE.Color(lite ? 0xe4dece : shiny ? 0x121212 : 0x0a0a0a),
    roughness,
    metalness: 0,
    clearcoat: matte ? (lite ? 0 : 0.12) : lite ? 0.35 : 1.0,
    clearcoatRoughness: matte ? 0.4 : lite ? 0.18 : 0.03,
    // Glossy lacquer has almost no diffuse color — it reads through IBL highlights.
    envMapIntensity: lite ? 0.75 : matte ? 0.95 : 1.75,
    specularIntensity: lite ? 0.7 : shiny ? 0.88 : 0.62,
    // Neutral spec tint (was cool 0xd8dce8, which blued the lacquer highlights).
    specularColor: new THREE.Color(lite ? 0xffffff : 0xece8e0),
  });
}

/** Opposing depth bias: bottom leaf behind, top/screws in front. */
const HINGE_DEPTH_BIAS = {
  Long_Continuous_Hinge_Bottom: { factor: 1, units: 1 },
  Long_Continuous_Hinge_Top: { factor: -1.5, units: -1.5 },
  Long_Continuous_Hinge_Screws: { factor: -2, units: -2 },
};

/**
 * Thin hinge leaves/screw plate: export splits the top/bottom stack and tiers
 * normal push. Front faces only; opposing polygon bias clears residual coplanar
 * flicker where the two ~1 mm shells overlap (e.g. around middle C).
 */
export function prepHingeTrim(root) {
  root.traverse((obj) => {
    const bias = HINGE_DEPTH_BIAS[obj.name];
    if (!obj.isMesh || !bias) return;
    const cloneMat = (mat) => {
      if (!mat) return mat;
      const next = mat.clone();
      next.side = THREE.FrontSide;
      next.polygonOffset = true;
      next.polygonOffsetFactor = bias.factor;
      next.polygonOffsetUnits = bias.units;
      return next;
    };
    obj.material = Array.isArray(obj.material)
      ? obj.material.map(cloneMat)
      : cloneMat(obj.material);
  });
}

/** Tune exported metals (color/roughness); depth is left to the geometry + log buffer. */
function tuneMetal(
  mat,
  fallbackColor,
  fallbackRough,
  {
    doubleSided = true,
    anisotropy = 0,
    anisotropyRotation = 0,
    envMapIntensity = 1.28,
    metalness = 1.0,
    specularIntensity = 1.0,
    clearcoat = 0,
    clearcoatRoughness = 0.25,
  } = {},
) {
  // glTF metallic-roughness loads as MeshStandardMaterial, which has no
  // anisotropy / clearcoat. Upgrade when those channels are needed.
  const needsPhysical =
    anisotropy > 0 || specularIntensity < 1 || clearcoat > 0;
  if (needsPhysical && !mat.isMeshPhysicalMaterial) {
    const phys = new THREE.MeshPhysicalMaterial();
    phys.name = mat.name;
    phys.map = mat.map;
    phys.roughnessMap = mat.roughnessMap;
    phys.metalnessMap = mat.metalnessMap;
    phys.normalMap = mat.normalMap;
    if (mat.normalMap) phys.normalScale.copy(mat.normalScale);
    mat = phys;
  }
  prepMaps(mat);
  mat.metalness = metalness;
  mat.roughness = fallbackRough;
  mat.envMapIntensity = envMapIntensity;
  if (mat.isMeshPhysicalMaterial) {
    if (specularIntensity < 1) mat.specularIntensity = specularIntensity;
    if (clearcoat > 0) {
      mat.clearcoat = clearcoat;
      mat.clearcoatRoughness = clearcoatRoughness;
    }
  }
  // Gilded cast-iron plates carry a faint brushed radial grain. A little
  // anisotropy stretches the env reflection along the grain so the gold reads
  // as cast metal rather than a chrome mirror. UV-derived tangents drive the
  // direction; anisotropyRotation orients it (0 = along U).
  if (anisotropy > 0) {
    mat.anisotropy = anisotropy;
    mat.anisotropyRotation = anisotropyRotation;
  }
  if (mat.normalMap) mat.normalScale.set(1.1, 1.1);
  // Thin trim (hinge leaves, rim gold) needs DoubleSide; solid harp plate/rim and
  // pin hardware are closed volumes — DoubleSide draws the back face at the same
  // depth and z-fights (probe: two Cube016_3 hits at Δ0.00 mm).
  mat.side = doubleSided ? THREE.DoubleSide : THREE.FrontSide;
  // The materialiq metals export a flat *grayscale* base-color texture; the gold/
  // brass/copper hue lived in the Blender base-color factor, which glTF dropped
  // (defaults to white). Used as albedo, that gray map makes the metal mirror the
  // gray environment and read as chrome. Drop it and apply the metal's own tint.
  // The packed metallic-roughness map averages ~0.63 roughness (satin) — strip it
  // so the scalar fallback drives a polished cast-plate read; keep the normal map.
  if (mat.map) {
    mat.map.dispose?.();
    mat.map = null;
  }
  if (mat.roughnessMap) {
    mat.roughnessMap.dispose?.();
    mat.roughnessMap = null;
  }
  if (mat.metalnessMap) {
    mat.metalnessMap.dispose?.();
    mat.metalnessMap = null;
  }
  mat.color = new THREE.Color(fallbackColor);
  // No polygonOffset: the old -2 bias pulled metals toward the camera and let the
  // interior gold frame punch through the thin black case. The lid-edge trim is
  // separated geometrically at export (_fix_lid_trim_zfight) and the log depth
  // buffer resolves it cleanly, so the forward bias is no longer needed.
  return mat;
}

function tuneWood(mat) {
  prepMaps(mat);
  mat.metalness = 0;
  if (!mat.roughnessMap && typeof mat.roughness !== "number") {
    mat.roughness = 0.55;
  }
  mat.envMapIntensity = 1.1;
  if (mat.normalMap) mat.normalScale.set(1.15, 1.15);
  if (!mat.map) mat.color = new THREE.Color(0x7c5a3a);
  // Solid interior wood (soundboard slab) — glTF often marks DoubleSide; that
  // draws front/back at the same depth and z-fights (Cube016_5 probe).
  mat.side = THREE.FrontSide;
  return mat;
}

/**
 * Piano action materials (build/action.py `Action_*`): plain base colors with no
 * maps. Keep the exported color — the generic fallback would paint them all
 * dark gray — and give felt a soft sheen and the metals real reflectance.
 */
function tuneAction(mat, name) {
  if (/Brass/i.test(name)) {
    return tuneMetal(mat, 0xcaa55c, 0.3, {
      doubleSided: false,
      envMapIntensity: 0.8,
      clearcoat: 0.25,
      clearcoatRoughness: 0.25,
    });
  }
  if (/Steel/i.test(name)) {
    return tuneMetal(mat, 0xb8b8bc, 0.28, { doubleSided: false, envMapIntensity: 0.75 });
  }
  if (/Iron/i.test(name)) {
    return tuneMetal(mat, 0x1e1e21, 0.45, {
      doubleSided: false,
      metalness: 0.6,
      envMapIntensity: 0.6,
    });
  }
  prepMaps(mat);
  if (/Felt/i.test(name)) {
    // Wool felt: fully rough with a faint fiber sheen at grazing angles.
    const felt = new THREE.MeshPhysicalMaterial({
      name: mat.name,
      color: mat.color.clone(),
      roughness: 1.0,
      metalness: 0,
      sheen: 0.8,
      sheenRoughness: 0.75,
      sheenColor: mat.color.clone().lerp(new THREE.Color(0xffffff), 0.35),
      envMapIntensity: 0.6,
    });
    mat.dispose?.();
    return felt;
  }
  mat.metalness = 0;
  mat.envMapIntensity = /Leather/i.test(name) ? 0.7 : 0.9;
  return mat;
}

/** Depth stack for the joined harp interior (Piano_Static material groups). */
function applyInteriorDepthBias(mat, name) {
  if (/Bridge/i.test(name) && /wood|beech|maple/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = -6;
    mat.polygonOffsetUnits = -6;
    return;
  }
  if (/^2B_Wood|wood|beech|maple/i.test(name) && !/^Action_/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 5;
    mat.polygonOffsetUnits = 5;
    return;
  }
  if (/^sy_(dark|lite)/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = -1;
    mat.polygonOffsetUnits = -1;
    return;
  }
  if (/Rim/i.test(name) && /brass/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 1.5;
    mat.polygonOffsetUnits = 1.5;
    return;
  }
  if (/Plate/i.test(name) && /brass/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 1;
    mat.polygonOffsetUnits = 1;
    return;
  }
  if (/^0T_Brass/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 1;
    mat.polygonOffsetUnits = 1;
    return;
  }
  if (/battlehsip/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = 2;
    mat.polygonOffsetUnits = 2;
    return;
  }
  if (/^0C_Copper|^Strings_Steel/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = -2.5;
    mat.polygonOffsetUnits = -2.5;
    return;
  }
  if (/^0A_Steel/i.test(name)) {
    mat.polygonOffset = true;
    mat.polygonOffsetFactor = -1.5;
    mat.polygonOffsetUnits = -1.5;
  }
}

const PIANO_WORLD_MAX = 2.5;

/**
 * Blender 5.x glTF export can emit a stray degenerate triangle (e.g. x≈215 m on
 * the soundboard material) when interior materials are split. Drop any face that
 * references out-of-range or non-finite world coordinates.
 * @param {THREE.Object3D} root
 * @returns {number} removed triangle count
 */
export function repairPianoStatic(root) {
  const ps = root.getObjectByName("Piano_Static");
  if (!ps?.isMesh || !ps.geometry?.index) return 0;

  const geo = ps.geometry;
  const pos = geo.attributes.position;
  const src = geo.index;
  const keep = [];
  const va = new THREE.Vector3();
  const vb = new THREE.Vector3();
  const vc = new THREE.Vector3();
  ps.updateMatrixWorld(true);
  const mw = ps.matrixWorld;

  const ok = (p) =>
    Number.isFinite(p.x) &&
    Number.isFinite(p.y) &&
    Number.isFinite(p.z) &&
    Math.abs(p.x) < PIANO_WORLD_MAX &&
    Math.abs(p.y) < PIANO_WORLD_MAX &&
    Math.abs(p.z) < PIANO_WORLD_MAX;

  for (let i = 0; i < src.count; i += 3) {
    const ia = src.getX(i);
    const ib = src.getX(i + 1);
    const ic = src.getX(i + 2);
    if (ia === ib || ib === ic || ia === ic) continue;

    va.fromBufferAttribute(pos, ia).applyMatrix4(mw);
    vb.fromBufferAttribute(pos, ib).applyMatrix4(mw);
    vc.fromBufferAttribute(pos, ic).applyMatrix4(mw);
    if (ok(va) && ok(vb) && ok(vc)) keep.push(ia, ib, ic);
  }

  if (keep.length === src.count) return 0;
  geo.setIndex(keep);
  geo.computeBoundingSphere();
  geo.computeBoundingBox();
  return src.count / 3 - keep.length / 3;
}

// The speaking strings (plain steel + bass copper) overlay the plate/soundboard
// from above, modeled coplanar with the bridge top and inside the plate's Y span.
const STRING_MAT_RE = /^(0C_Copper|Strings_Steel)/i;
// 0A_Steel is hardware (pins/capo/agraffes), not speaking strings — leave it seated.

const SOUNDBOARD_MESH_MAT_RE = /^2B_Wood_Beech_mqm$/i; // exact: excludes …_Bridge
const PLATE_MAT_RE = /^0T_Brass_mqm_Plate$/i;

function meshMatchesMaterial(mesh, re) {
  const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
  return mats.some((m) => m && re.test(m.name || ""));
}

// Overlay duplicate shells are thin (≈0.5–4 mm). Larger Y steps are real crown/profile.
const OVERLAY_GAP_MIN_M = 0.0005;
const OVERLAY_GAP_MAX_M = 0.004;
const OVERLAY_UPPER_MAX_FRAC = 0.2;

/**
 * Drop a thin duplicate up-facing shell (plate lip skins only). Only removes
 * up-facing triangles in a small upper cluster — never side walls or crown step.
 * @param {THREE.Mesh} mesh
 * @returns {number} removed triangle count
 */
function dedupeOverlayOnMesh(mesh) {
  if (!mesh?.geometry?.index) return 0;

  const geo = mesh.geometry;
  const pos = geo.attributes.position;
  const idx = geo.index;
  mesh.updateMatrixWorld(true);
  const mw = mesh.matrixWorld;
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const ab = new THREE.Vector3();
  const ac = new THREE.Vector3();
  const n = new THREE.Vector3();

  const upTris = [];
  for (let t = 0; t < idx.count; t += 3) {
    a.fromBufferAttribute(pos, idx.getX(t)).applyMatrix4(mw);
    b.fromBufferAttribute(pos, idx.getX(t + 1)).applyMatrix4(mw);
    c.fromBufferAttribute(pos, idx.getX(t + 2)).applyMatrix4(mw);
    n.copy(ab.subVectors(b, a)).cross(ac.subVectors(c, a)).normalize();
    if (n.y <= 0.7) continue;
    upTris.push({ t, cy: (a.y + b.y + c.y) / 3 });
  }
  if (upTris.length < 8) return 0;

  upTris.sort((u, v) => u.cy - v.cy);

  let best = null;
  for (let i = 1; i < upTris.length; i++) {
    const g = upTris[i].cy - upTris[i - 1].cy;
    if (g < OVERLAY_GAP_MIN_M || g > OVERLAY_GAP_MAX_M) continue;
    const above = upTris.length - i;
    if (above / upTris.length > OVERLAY_UPPER_MAX_FRAC) continue;
    const cut = (upTris[i].cy + upTris[i - 1].cy) / 2;
    if (!best || g < best.g) best = { g, cut };
  }
  if (!best) return 0;

  const drop = new Set();
  for (const { t, cy } of upTris) {
    if (cy > best.cut) drop.add(t);
  }
  if (!drop.size) return 0;

  const keep = [];
  for (let t = 0; t < idx.count; t += 3) {
    if (!drop.has(t)) keep.push(idx.getX(t), idx.getX(t + 1), idx.getX(t + 2));
  }
  if (keep.length === idx.count) return 0;
  geo.setIndex(keep);
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
  geo.computeBoundingBox();
  return drop.size;
}

/**
 * glTF loads Piano_Static as per-material child meshes. Only the cast plate may
 * carry a thin duplicate skin. Soundboard flicker was DoubleSide back-faces, not
 * a carvable overlay (max-gap dedupe removed the crowned top).
 * @param {THREE.Object3D} root
 * @returns {number} removed triangle count
 */
export function dedupeInteriorOverlays(root) {
  const ps = root.getObjectByName("Piano_Static");
  if (!ps) return 0;
  let removed = 0;
  ps.traverse((o) => {
    if (!o.isMesh || !meshMatchesMaterial(o, PLATE_MAT_RE)) return;
    removed += dedupeOverlayOnMesh(o);
  });
  return removed;
}

/** @deprecated use dedupeInteriorOverlays */
export function dedupeSoundboardOverlay(root) {
  return dedupeInteriorOverlays(root);
}

/**
 * Translate every vertex of a mesh by `deltaY` in *world* space (then back into
 * the mesh's local frame), leaving normals untouched since it's a pure translation.
 */
function liftMeshWorldY(mesh, deltaY) {
  const geo = mesh.geometry;
  const pos = geo?.attributes?.position;
  if (!pos) return 0;
  mesh.updateMatrixWorld(true);
  const inv = mesh.matrixWorld.clone().invert();
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(mesh.matrixWorld);
    v.y += deltaY;
    v.applyMatrix4(inv);
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  pos.needsUpdate = true;
  geo.computeBoundingSphere();
  geo.computeBoundingBox();
  return pos.count;
}

const STRING_LIFT = 0.005; // world metres; clears the plate/bridge under the strings
const BRIDGE_LIFT = 0.003;

function actionExtras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

/**
 * Action dampers are exported at rest on the string plane. prepInteriorStack
 * lifts Piano_Static speaking strings for plate clearance; ride the same offset
 * on the damper heads so felts stay seated on the strings in the viewer.
 *
 * Heads share geometry by size group (and carry their wire as a child), so lift
 * the node, never the vertices — a shared buffer would be lifted once per user.
 */
function prepActionStringPlane(root) {
  const scale = new THREE.Vector3();
  root.traverse((obj) => {
    if (actionExtras(obj).action_part !== "damper_head") return;
    if (obj.userData.stringLifted) return;
    obj.userData.stringLifted = true;
    obj.parent?.updateWorldMatrix(true, false);
    const sy = obj.parent ? scale.setFromMatrixScale(obj.parent.matrixWorld).y : 1;
    obj.position.y += STRING_LIFT / (sy || 1);
  });
}

function meshWorldYExtents(mesh) {
  const pos = mesh.geometry?.attributes?.position;
  if (!pos) return null;
  mesh.updateMatrixWorld(true);
  const mw = mesh.matrixWorld;
  const v = new THREE.Vector3();
  let minY = Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(mw);
    minY = Math.min(minY, v.y);
    maxY = Math.max(maxY, v.y);
  }
  return { minY, maxY };
}

/**
 * Physically separate the speaking strings (and, in older joined GLBs, the seated
 * bridge) from the surface beneath them in world Y. polygonOffset can't do this —
 * logarithmicDepthBuffer rewrites fragment depth in the shader and discards the
 * rasterizer offset — so the only reliable fix is real geometric clearance.
 *
 * glTF loads Piano_Static as a group of per-material child meshes (Cube016_N).
 * Legacy single-mesh joins are still handled.
 * @param {THREE.Object3D} root
 */
export function prepInteriorStack(root) {
  const ps = root.getObjectByName("Piano_Static");

  // Per-primitive child meshes (current GLB layout).
  if (ps && !ps.isMesh) {
    let wood = null;
    let bridge = null;
    ps.traverse((obj) => {
      if (!obj.isMesh) return;
      if (meshMatchesMaterial(obj, STRING_MAT_RE)) liftMeshWorldY(obj, STRING_LIFT);
      if (meshMatchesMaterial(obj, SOUNDBOARD_MESH_MAT_RE)) wood = obj;
      if (meshMatchesMaterial(obj, /Bridge/i)) bridge = obj;
    });
    if (wood && bridge) {
      const w = meshWorldYExtents(wood);
      const b = meshWorldYExtents(bridge);
      if (w && b) {
        const gap = b.minY - w.maxY;
        if (gap < 0.001) liftMeshWorldY(bridge, BRIDGE_LIFT + Math.max(0, -gap));
      }
    }
    prepActionStringPlane(root);
    return;
  }

  // Legacy joined-mesh layout (single multi-material Piano_Static).
  if (!ps?.isMesh || !ps.geometry?.index || !ps.geometry.groups?.length) {
    prepActionStringPlane(root);
    return;
  }

  const geo = ps.geometry;
  const pos = geo.attributes.position;
  const idx = geo.index;
  const materials = Array.isArray(ps.material) ? ps.material : [ps.material];

  const matIndex = (re) => materials.findIndex((m) => m && re.test(m.name || ""));
  const woodMi = matIndex(/^2B_Wood_Beech_mqm$/i);
  const bridgeMi = matIndex(/Bridge/i);
  const stringMis = new Set(
    materials.flatMap((m, i) => (m && STRING_MAT_RE.test(m.name || "") ? [i] : [])),
  );
  if (woodMi < 0 || bridgeMi < 0) {
    prepActionStringPlane(root);
    return;
  }

  ps.updateMatrixWorld(true);
  const inv = ps.matrixWorld.clone().invert();
  const v = new THREE.Vector3();
  const centroidY = (t) => {
    let y = 0;
    for (let k = 0; k < 3; k++) {
      v.fromBufferAttribute(pos, idx.getX(t + k)).applyMatrix4(ps.matrixWorld);
      y += v.y;
    }
    return y / 3;
  };

  let bridgeMinY = Infinity;
  let bridgeMaxY = -Infinity;
  for (const g of geo.groups) {
    if (g.materialIndex !== bridgeMi) continue;
    for (let t = g.start; t < g.start + g.count; t += 3) {
      const y = centroidY(t);
      bridgeMinY = Math.min(bridgeMinY, y);
      bridgeMaxY = Math.max(bridgeMaxY, y);
    }
  }
  if (!Number.isFinite(bridgeMinY)) {
    prepActionStringPlane(root);
    return;
  }

  const SINK = 0.003;
  const LIFT = 0.003;
  const touchBand = Math.max(0.006, (bridgeMaxY - bridgeMinY) * 0.05);

  const nudgeVerts = (t, deltaY) => {
    for (let k = 0; k < 3; k++) {
      const vi = idx.getX(t + k);
      v.fromBufferAttribute(pos, vi).applyMatrix4(ps.matrixWorld);
      v.y += deltaY;
      v.applyMatrix4(inv);
      pos.setXYZ(vi, v.x, v.y, v.z);
    }
  };

  let sunk = 0;
  let lifted = 0;
  for (const g of geo.groups) {
    if (g.materialIndex === woodMi) {
      for (let t = g.start; t < g.start + g.count; t += 3) {
        const y = centroidY(t);
        if (y >= bridgeMinY - touchBand && y <= bridgeMinY + touchBand * 0.5) {
          nudgeVerts(t, -SINK);
          sunk++;
        }
      }
    } else if (g.materialIndex === bridgeMi) {
      for (let t = g.start; t < g.start + g.count; t += 3) {
        nudgeVerts(t, LIFT);
        lifted++;
      }
    } else if (stringMis.has(g.materialIndex)) {
      for (let t = g.start; t < g.start + g.count; t += 3) {
        nudgeVerts(t, STRING_LIFT);
        lifted++;
      }
    }
  }

  if (sunk || lifted) {
    pos.needsUpdate = true;
    geo.computeVertexNormals();
    geo.computeBoundingSphere();
    geo.computeBoundingBox();
  }

  prepActionStringPlane(root);
}

/**
 * Materials from export_glb.py: sy_* base colors from the .blend, wood/metal maps
 * embedded. Lacquer/ivory get clearcoat here; textured parts keep their GLB maps.
 * @param {THREE.Object3D} root
 */
export function refineMaterials(root) {
  const cache = new Map();

  const remap = (mat) => {
    if (!mat) return mat;
    if (cache.has(mat.uuid)) return cache.get(mat.uuid);
    const name = mat.name || "";
    let next = mat;

    if (/^Action_/i.test(name)) {
      next = tuneAction(mat, name);
    } else if (/^sy_lite/i.test(name)) {
      next = lacquerFromExport(mat, { matte: /matte/i.test(name), lite: true });
    } else if (/^sy_/i.test(name)) {
      next = lacquerFromExport(mat, { matte: /matte/i.test(name), lite: false });
    } else if (/gold/i.test(name)) {
      // materialiq gold: metal 1, packed roughness ~0.63. Satin base + light
      // clearcoat reads shiny like Blender without mirror-clipping flat faces.
      next = tuneMetal(mat, 0xc6a456, 0.52, {
        doubleSided: true,
        anisotropy: 0.35,
        envMapIntensity: 0.55,
        metalness: 1.0,
        clearcoat: 0.45,
        clearcoatRoughness: 0.18,
      });
    } else if (/brass/i.test(name)) {
      // Cast plate (0T_Brass_mqm bulk + _Plate shell): match Blender satin metal
      // (map rough ~0.63). Clearcoat adds the lacquered-gold sheen; roughness
      // stays high enough that large faces keep gold color under ACES.
      const isHarpPlate = /Plate/i.test(name) || /^0T_Brass_mqm$/i.test(name);
      const isRim = /Rim/i.test(name);
      if (isHarpPlate) {
        // Deeper, more saturated bronze-gold than the trim: the lighter tint +
        // heavier white clearcoat desaturated the huge flat plate under ACES.
        next = tuneMetal(mat, 0xb48c3e, 0.55, {
          doubleSided: false,
          anisotropy: 0.4,
          envMapIntensity: 0.5,
          metalness: 1.0,
          clearcoat: 0.3,
          clearcoatRoughness: 0.16,
        });
      } else {
        // The rim flange is a big flat face like the plate: same deeper tint and
        // lighter coat so it doesn't wash out to cream next to it.
        next = tuneMetal(mat, isRim ? 0xb48c3e : 0xc6a456, isRim ? 0.5 : 0.4, {
          doubleSided: !isRim,
          anisotropy: isRim ? 0.3 : 0,
          envMapIntensity: isRim ? 0.5 : 0.65,
          metalness: 1.0,
          clearcoat: isRim ? 0.25 : 0.4,
          clearcoatRoughness: 0.2,
        });
      }
    } else if (/copper/i.test(name)) {
      next = tuneMetal(mat, 0xb87333, 0.4, {
        metalness: 1.0,
        envMapIntensity: 0.6,
        clearcoat: 0.25,
        clearcoatRoughness: 0.3,
      });
    } else if (/steel|chrome|metal/i.test(name)) {
      next = tuneMetal(mat, 0xc6c4c0, 0.35, {
        doubleSided: !/^0A_Steel/i.test(name),
        metalness: 1.0,
        envMapIntensity: 0.65,
      });
    } else if (/wood|beech|maple/i.test(name)) {
      next = tuneWood(mat);
    } else if (/plastic/i.test(name)) {
      prepMaps(mat);
      mat.metalness = 0;
      mat.roughness = mat.roughness ?? 0.5;
      mat.envMapIntensity = 0.75;
      if (!mat.map) mat.color = new THREE.Color(0x141414);
      else mat.color.setRGB(1, 1, 1);
      next = mat;
    } else {
      prepMaps(mat);
      if (!mat.map) mat.color = new THREE.Color(0x2a2a2a);
      mat.envMapIntensity = 1.0;
      next = mat;
    }

    // Default to FrontSide, but keep DoubleSide where a branch asked for it
    // (thin metal trim that would otherwise be backface-culled).
    if (next.side !== THREE.DoubleSide) next.side = THREE.FrontSide;
    // Strings are closed tubes: DoubleSide draws each tube's far wall too, so
    // every string reads as a doubled line that z-fights/shimmers at grazing
    // angles. Force FrontSide — the outer surface is all we ever see.
    if (STRING_MAT_RE.test(name)) next.side = THREE.FrontSide;
    applyInteriorDepthBias(next, name);
    cache.set(mat.uuid, next);
    return next;
  };

  root.traverse((obj) => {
    if (!obj.isMesh) return;
    obj.material = Array.isArray(obj.material)
      ? obj.material.map(remap)
      : remap(obj.material);
  });
}

/**
 * Shared studio cyclorama palette: the dome's horizon and the floor's far field
 * use the same color so the floor melts into the backdrop with no visible seam.
 */
export const STUDIO_PALETTE = {
  zenith: new THREE.Color(0x141517),
  horizon: new THREE.Color(0x524f4a),
  floor: new THREE.Color(0x302e2b),
};

/** 8-bit ordered-ish noise to break up banding in the dark gradients. */
const DITHER_GLSL = /* glsl */ `
  float studioDither( vec2 p ) {
    return ( fract( sin( dot( p, vec2( 12.9898, 78.233 ) ) ) * 43758.5453 ) - 0.5 ) / 255.0;
  }`;

/**
 * World-space backdrop dome (replaces the old screen-space radial texture, which
 * met the floor in a hard light/dark line). Gradient runs from the shared
 * horizon color up to a dark zenith, so it lines up with the floor's far fade
 * from every camera angle.
 */
function createStudioDome() {
  const mat = new THREE.ShaderMaterial({
    name: "StudioDome",
    uniforms: {
      uZenith: { value: STUDIO_PALETTE.zenith },
      uHorizon: { value: STUDIO_PALETTE.horizon },
    },
    vertexShader: /* glsl */ `
      varying vec3 vWorldPos;
      void main() {
        vec4 wp = modelMatrix * vec4( position, 1.0 );
        vWorldPos = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uZenith;
      uniform vec3 uHorizon;
      varying vec3 vWorldPos;
      ${DITHER_GLSL}
      void main() {
        vec3 dir = normalize( vWorldPos - cameraPosition );
        // Bright band hugging the horizon, falling off fast toward the zenith.
        float t = pow( smoothstep( 0.0, 0.7, max( dir.y, 0.0 ) ), 0.6 );
        vec3 col = mix( uHorizon, uZenith, t );
        gl_FragColor = vec4( col + studioDither( gl_FragCoord.xy ), 1.0 );
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    side: THREE.BackSide,
    depthTest: false,
    depthWrite: false,
  });
  // Encloses the full orbit range (maxDistance 12) inside the camera far plane.
  const dome = new THREE.Mesh(new THREE.SphereGeometry(30, 48, 24), mat);
  dome.name = "Studio_Dome";
  dome.frustumCulled = false;
  dome.renderOrder = -10;
  return dome;
}

/**
 * Room probe for lacquer / wood / metal reflections. Only emissive (MeshBasic)
 * panels matter here — PMREM just captures what they look like, so lights in
 * this scene would do nothing.
 *
 * Panels are DoubleSide on purpose: a PlaneGeometry faces +Z, so a ceiling
 * rotated -90° about X (or a wall facing away from the origin) is back-face
 * culled and silently missing from the probe. That left the lacquer reflecting
 * a near-black void and the body read as a flat silhouette.
 */
function roomEnvironment(pmrem) {
  const envScene = new THREE.Scene();
  // Neutral-warm probe: glossy black lacquer is nearly a mirror, so cool probes
  // tint the body blue.
  envScene.background = new THREE.Color(0x1c1b19);

  const makePanel = (color, w, h, x, y, z, rx = 0, ry = 0) => {
    const m = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }),
    );
    m.position.set(x, y, z);
    m.rotation.x = rx;
    m.rotation.y = ry;
    envScene.add(m);
  };
  const c = (hex, k) => new THREE.Color(hex).multiplyScalar(k);

  // Dim lit floor: the vertical rim and legs mostly mirror the lower hemisphere,
  // so a floor bounce gives the black body a soft gradient instead of a void.
  makePanel(c(0x5c5852, 1), 30, 30, 0, -3, 0, -Math.PI / 2);
  // Broad overhead softbox — kept modest so the flat gilded plate stays gold
  // instead of mirroring white (see refineMaterials brass notes).
  makePanel(c(0xb8b2a6, 1), 6, 4, 0, 6, 0.5, Math.PI / 2);
  // Long, bright strip softboxes near the horizon: these draw the crisp
  // highlight lines along the curved rim, fallboard and lid edge that make
  // black lacquer read as glossy.
  makePanel(c(0xfff4e6, 3.2), 9, 0.7, 0, 1.2, 7, 0); // front
  makePanel(c(0xfff4e6, 2.4), 9, 0.6, -7, 0.6, 0.5, 0, Math.PI / 2); // left
  makePanel(c(0xfff4e6, 2.0), 9, 0.6, 7, 1.6, -0.5, 0, Math.PI / 2); // right
  makePanel(c(0xe8e2d6, 1.4), 9, 0.6, 0, 1.0, -7, 0); // rear
  // Low strip toward the hero camera (front-right): the vertical rim mirrors
  // directions ~15° below the horizon from that view, so this draws the long
  // highlight down the curved side instead of leaving it a flat silhouette.
  makePanel(c(0xfff4e6, 1.8), 8, 1.0, 5, -1.4, 5, 0, Math.PI / 4);
  // Large soft side fills for gentle broad shape on the curved rim.
  makePanel(c(0x8a857c, 1), 6, 4, -6.8, 3.6, -1.5, 0, Math.PI / 2);
  makePanel(c(0x8a857c, 1), 6, 4, 6.8, 3.6, 2, 0, Math.PI / 2);

  // 0.04 is PMREM's max blur (20 samples); larger sigmas clip with a warning.
  return pmrem.fromScene(envScene, 0.04).texture;
}

/** Light room backdrop + IBL (seated viewing context). */
export function setupEnvironment(renderer, scene) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = roomEnvironment(pmrem);
  scene.background = null;
  scene.add(createStudioDome());
  // Fog was flattening surface detail — keep backdrop gradient only.
  scene.fog = null;
  pmrem.dispose();
  return scene.environment;
}

/**
 * Remove the showroom Reflector floor (and dispose GPU resources).
 * @param {THREE.Object3D | null | undefined} floor
 */
export function disposeStudioGround(floor) {
  if (!floor) return;
  floor.parent?.remove(floor);
  floor.geometry?.dispose?.();
  const mat = floor.material;
  if (mat) {
    mat.map?.dispose?.();
    mat.dispose?.();
  }
  // Reflector keeps an internal render target.
  floor.getRenderTarget?.()?.dispose?.();
}

/**
 * Remove the soft contact-shadow blob and free GPU resources.
 * @param {THREE.Object3D | null | undefined} shadow
 */
export function disposeContactShadow(shadow) {
  if (!shadow) return;
  shadow.parent?.remove(shadow);
  shadow.geometry?.dispose?.();
  const mat = shadow.material;
  if (mat) {
    mat.map?.dispose?.();
    mat.dispose?.();
  }
}

/**
 * Even soft showroom lighting: ambient + hemisphere carry most of the level;
 * a high ceiling key and side fill add gentle shape; wide soft key wash on the
 * keyboard. No camera-follow lamps by default (avoids hotspots while orbiting).
 * @returns {{
 *   lights: {
 *     ambient: THREE.AmbientLight,
 *     hemi: THREE.HemisphereLight,
 *     ceiling: THREE.DirectionalLight,
 *     room: THREE.DirectionalLight,
 *     viewerLight: THREE.PointLight,
 *     keySpot: THREE.SpotLight,
 *     keySpotTarget: THREE.Object3D,
 *   },
 *   lightingConfig: {
 *     viewerFollowCamera: boolean,
 *     viewerOffset: THREE.Vector3,
 *     keySpotFollowCamera: boolean,
 *     keySpotCamX: number,
 *     keySpotCamY: number,
 *     keySpotCamZMul: number,
 *     keySpotCamZAdd: number,
 *   },
 *   syncViewerLight: (pos: THREE.Vector3) => void,
 * }}
 */
export function setupSeatedViewerLights(scene) {
  const d = LIGHTING_DEFAULTS;

  // Neutral-warm fill so diffuse parts don't pick up a blue cast.
  const ambient = new THREE.AmbientLight(0xf6f4f0, d.ambientIntensity);
  scene.add(ambient);

  // Soft sky / floor bounce — main evenness of the scene.
  const hemi = new THREE.HemisphereLight(0xfaf8f4, 0xa8a59c, d.hemiIntensity);
  hemi.position.set(...d.hemiPosition);
  scene.add(hemi);

  // High, soft overhead key — only shadow caster so contact stays single and soft.
  const ceiling = new THREE.DirectionalLight(0xfffaf5, d.ceilingIntensity);
  ceiling.position.set(...d.ceilingPosition);
  ceiling.castShadow = true;
  ceiling.shadow.mapSize.set(2048, 2048);
  // PCFSoftShadowMap uses radius to widen the filter kernel.
  ceiling.shadow.radius = 6;
  ceiling.shadow.blurSamples = 12;
  const sc = ceiling.shadow.camera;
  // Slightly wider frustum softens the lid/keybed umbra edge.
  sc.left = -2.0;
  sc.right = 2.0;
  sc.top = 2.2;
  sc.bottom = -2.2;
  sc.near = 0.5;
  sc.far = 14;
  sc.updateProjectionMatrix();
  ceiling.shadow.bias = -0.0004;
  ceiling.shadow.normalBias = 0.035;
  scene.add(ceiling);
  // DirectionalLight aims at its target (default origin); the piano sits at
  // origin, so no target move is needed.

  // Side / front fill — no shadows (keeps shading soft and even).
  const room = new THREE.DirectionalLight(0xf0ede6, d.roomIntensity);
  room.position.set(...d.roomPosition);
  room.castShadow = false;
  scene.add(room);

  // Fixed front point fill — no shadows (avoids a second hard contact line).
  const viewerLight = new THREE.PointLight(
    0xfff6ea,
    d.viewerIntensity,
    d.viewerDistance,
    d.viewerDecay,
  );
  viewerLight.position.set(...d.viewerPosition);
  viewerLight.castShadow = false;
  scene.add(viewerLight);

  const keySpotAngle = THREE.MathUtils.degToRad(d.keySpotAngleDeg);
  const keySpot = new THREE.SpotLight(
    0xfffaf5,
    d.keySpotIntensity,
    d.keySpotDistance,
    keySpotAngle,
    d.keySpotPenumbra,
    d.keySpotDecay,
  );
  keySpot.position.set(...d.keySpotPosition);
  keySpot.castShadow = false;
  const keySpotTarget = new THREE.Object3D();
  keySpotTarget.position.set(...d.keySpotTarget);
  scene.add(keySpotTarget);
  keySpot.target = keySpotTarget;
  scene.add(keySpot);

  const lightingConfig = {
    viewerFollowCamera: d.viewerFollowCamera,
    viewerOffset: new THREE.Vector3(...d.viewerOffset),
    keySpotFollowCamera: d.keySpotFollowCamera,
    keySpotCamX: d.keySpotCamX,
    keySpotCamY: d.keySpotCamY,
    keySpotCamZMul: d.keySpotCamZMul,
    keySpotCamZAdd: d.keySpotCamZAdd,
  };

  const syncViewerLight = (eyePosition) => {
    if (lightingConfig.viewerFollowCamera) {
      viewerLight.position.copy(eyePosition).add(lightingConfig.viewerOffset);
    }
    if (lightingConfig.keySpotFollowCamera) {
      const c = lightingConfig;
      keySpot.position.set(
        eyePosition.x * c.keySpotCamX,
        eyePosition.y + c.keySpotCamY,
        eyePosition.z * c.keySpotCamZMul + c.keySpotCamZAdd,
      );
    }
  };

  return {
    lights: { ambient, hemi, ceiling, room, viewerLight, keySpot, keySpotTarget },
    lightingConfig,
    syncViewerLight,
  };
}

function wireRangeSphere(color) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(1, 24, 16),
    new THREE.MeshBasicMaterial({
      color,
      wireframe: true,
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
    }),
  );
  mesh.renderOrder = 998;
  return mesh;
}

function wireSourceMarker(color, size = 0.12) {
  const mesh = new THREE.Mesh(
    new THREE.OctahedronGeometry(size, 0),
    new THREE.MeshBasicMaterial({ color, wireframe: true }),
  );
  mesh.renderOrder = 999;
  return mesh;
}

/**
 * Debug wireframes for each scene light (source + reach). Hidden until toggled on.
 * @param {THREE.Scene} scene
 * @param {ReturnType<typeof setupSeatedViewerLights>["lights"]} lights
 */
export function createLightHelpers(scene, lights) {
  const group = new THREE.Group();
  group.name = "light-helpers";
  group.visible = false;

  const ambientMarker = wireSourceMarker(0xc8d0e0, 0.1);
  ambientMarker.position.set(0, 1.15, 0);
  group.add(ambientMarker);

  const hemiHelper = new THREE.HemisphereLightHelper(lights.hemi, 0.55, 0xf8fafc);
  group.add(hemiHelper);

  const ceilingHelper = new THREE.DirectionalLightHelper(lights.ceiling, 0.45, 0xfffaf5);
  const roomHelper = new THREE.DirectionalLightHelper(lights.room, 0.4, 0xe8ecf8);
  group.add(ceilingHelper, roomHelper);

  const viewerSource = new THREE.PointLightHelper(lights.viewerLight, 0.14, 0xfff6ea);
  const viewerRange = wireRangeSphere(0xfff6ea);
  group.add(viewerSource, viewerRange);

  const keySpotHelper = new THREE.SpotLightHelper(lights.keySpot, 0xffffff);
  const keySpotRange = wireRangeSphere(0xffffff);
  const keyTargetMarker = wireSourceMarker(0xffffff, 0.07);
  group.add(keySpotHelper, keySpotRange, keyTargetMarker);

  scene.add(group);

  const syncRangeSphere = (mesh, light, fallback = 8) => {
    mesh.position.copy(light.position);
    const r = light.distance > 0 ? light.distance : fallback;
    mesh.scale.setScalar(r);
  };

  const update = () => {
    hemiHelper.update();
    ceilingHelper.update();
    roomHelper.update();
    viewerSource.update();
    keySpotHelper.update();
    syncRangeSphere(viewerRange, lights.viewerLight, lights.viewerLight.distance || 14);
    syncRangeSphere(keySpotRange, lights.keySpot, lights.keySpot.distance || 10);
    keyTargetMarker.position.copy(lights.keySpotTarget.position);
  };

  return {
    group,
    setVisible(visible) {
      group.visible = visible;
    },
    update,
  };
}

/**
 * Custom Reflector shader: a true planar mirror over a dark studio floor. The
 * reflection fades out with distance, a soft pool brightens the floor under the
 * piano, and the far floor blends into the dome's horizon color so the floor
 * never meets the backdrop in a hard edge.
 * `color`, `tDiffuse`, `textureMatrix` are required by the Reflector constructor.
 */
const STUDIO_FLOOR_SHADER = {
  name: "StudioFloorReflectorShader",
  uniforms: {
    color: { value: null },
    tDiffuse: { value: null },
    textureMatrix: { value: null },
    uFloorColor: { value: STUDIO_PALETTE.floor },
    uHorizonColor: { value: STUDIO_PALETTE.horizon },
    uReflStrength: { value: 0.38 },
    uFadeStart: { value: 1.5 },
    uFadeEnd: { value: 7.0 },
    uPoolStrength: { value: 0.9 },
    uPoolRadius: { value: 3.2 },
    uHorizonStart: { value: 4.0 },
    uHorizonEnd: { value: 24.0 },
  },
  vertexShader: /* glsl */ `
    uniform mat4 textureMatrix;
    varying vec4 vUv;
    varying float vDist;

    #include <common>
    #include <logdepthbuf_pars_vertex>

    void main() {
      vUv = textureMatrix * vec4( position, 1.0 );
      // Plane local XY maps to the world ground plane (geometry is rotated flat):
      // distance from center drives the radial reflection fade.
      vDist = length( position.xy );
      gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
      #include <logdepthbuf_vertex>
    }`,
  fragmentShader: /* glsl */ `
    uniform vec3 color;
    uniform sampler2D tDiffuse;
    uniform vec3 uFloorColor;
    uniform vec3 uHorizonColor;
    uniform float uReflStrength;
    uniform float uFadeStart;
    uniform float uFadeEnd;
    uniform float uPoolStrength;
    uniform float uPoolRadius;
    uniform float uHorizonStart;
    uniform float uHorizonEnd;
    varying vec4 vUv;
    varying float vDist;

    #include <logdepthbuf_pars_fragment>
    ${DITHER_GLSL}

    float blendOverlay( float base, float blend ) {
      return( base < 0.5 ? ( 2.0 * base * blend ) : ( 1.0 - 2.0 * ( 1.0 - base ) * ( 1.0 - blend ) ) );
    }
    vec3 blendOverlay( vec3 base, vec3 blend ) {
      return vec3( blendOverlay( base.r, blend.r ), blendOverlay( base.g, blend.g ), blendOverlay( base.b, blend.b ) );
    }

    void main() {
      #include <logdepthbuf_fragment>
      // Soft light pool under the piano (gaussian-ish falloff).
      float pool = exp( -2.5 * ( vDist * vDist ) / ( uPoolRadius * uPoolRadius ) );
      vec3 floorCol = uFloorColor * ( 1.0 + uPoolStrength * pool );
      // Far field sweeps up into the dome's horizon color.
      floorCol = mix( floorCol, uHorizonColor, smoothstep( uHorizonStart, uHorizonEnd, vDist ) );
      float fade = 1.0 - smoothstep( uFadeStart, uFadeEnd, vDist );
      vec3 col = floorCol;
      // Only sample the mirror where it contributes: on the huge floor quads the
      // projective lookup can produce NaN far out, and NaN * 0 still poisons the
      // mix (showed as stray black dashes on the floor).
      if ( fade > 0.0 ) {
        vec3 refl = blendOverlay( texture2DProj( tDiffuse, vUv ).rgb, color );
        col = mix( floorCol, refl, uReflStrength * fade );
      }
      gl_FragColor = vec4( col + studioDither( gl_FragCoord.xy ), 1.0 );
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
};

/**
 * Glossy "showroom glass" floor — a true planar reflection (Reflector) of the
 * piano, dimmed and distance-faded so it grounds the model without a visible edge.
 * Adds one extra render pass per frame.
 * @returns {Reflector} the floor (use getRenderTarget().setSize() on resize)
 */
/** World Y of the studio Reflector — slightly below grounded feet (y=0). */
export const STUDIO_FLOOR_Y = -0.003;

/**
 * Soft contact-shadow plane sits above the floor and below caster bottoms
 * so it doesn't coplanar-fight either surface under logarithmic depth.
 */
export const CONTACT_SHADOW_Y = 0.0015;

/**
 * Floor-mirror resolution relative to the canvas. The reflection is dimmed and
 * distance-faded, so half resolution is visually indistinguishable while
 * cutting the mirror pass (~40% of GPU frame time at full res) roughly in half.
 */
export const FLOOR_REFLECTION_SCALE = 0.5;

export function createStudioGround(scene) {
  const scale = Math.min(window.devicePixelRatio, 2) * FLOOR_REFLECTION_SCALE;
  // Subdivided so the projective reflection UVs and log depth interpolate
  // accurately (two 80 m triangles spanning behind the camera don't).
  const floor = new Reflector(new THREE.PlaneGeometry(80, 80, 40, 40), {
    textureWidth: window.innerWidth * scale,
    textureHeight: window.innerHeight * scale,
    // Higher bias reduces reflection-plane acne under the body/casters.
    clipBias: 0.01,
    // Neutral tint: dimming is handled by the shader's mix toward uFloorColor.
    color: 0x808080,
    shader: STUDIO_FLOOR_SHADER,
  });
  floor.rotation.x = -Math.PI / 2;
  // Below the grounded feet so coplanar caster bottoms don't z-fight the glass.
  floor.position.y = STUDIO_FLOOR_Y;
  floor.renderOrder = -1;
  scene.add(floor);
  return floor;
}

function softShadowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(128, 128, 8, 128, 128, 124);
  g.addColorStop(0.0, "rgba(0,0,0,0.55)");
  g.addColorStop(0.55, "rgba(0,0,0,0.28)");
  g.addColorStop(1.0, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = SRGB;
  return tex;
}

/**
 * Soft elliptical contact shadow under the piano. The Reflector floor can't
 * receive the scene's shadow map, so this blurred blob grounds the model instead.
 * Sized to the loaded model's footprint.
 * @param {THREE.Scene} scene
 * @param {THREE.Object3D} model
 */
export function createContactShadow(scene, model) {
  model.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());

  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(size.x * 1.5, size.z * 1.45),
    new THREE.MeshBasicMaterial({
      map: softShadowTexture(),
      transparent: true,
      depthWrite: false,
      // Pull slightly toward the camera so log-depth + floor separation stay stable.
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1,
      opacity: 0.9,
    }),
  );
  shadow.rotation.x = -Math.PI / 2;
  // Between studio floor (below) and caster contact geometry (above).
  shadow.position.set(center.x, CONTACT_SHADOW_Y, center.z);
  shadow.renderOrder = 1;
  scene.add(shadow);
  return shadow;
}

export function setupShadows(root) {
  root.traverse((obj) => {
    if (obj.isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
    }
  });
}
