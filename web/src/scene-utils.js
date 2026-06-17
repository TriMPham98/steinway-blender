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
  }
  root.updateMatrixWorld(true);

  const finalBox = new THREE.Box3().setFromObject(root);
  return {
    size: finalBox.getSize(new THREE.Vector3()),
    center: finalBox.getCenter(new THREE.Vector3()),
  };
}

/** Default hero (¾ product) view — tuned in scene debug. */
export const HERO_CAMERA_DEFAULTS = {
  position: [2.39, 1.38, 2.37],
  target: [0, 0.74, 0.35],
  fov: 44,
  exposure: 1.86,
};

/** Default scene lighting (tuned in scene debug). */
export const LIGHTING_DEFAULTS = {
  ambientIntensity: 0.72,
  hemiIntensity: 1.05,
  hemiPosition: [0, 6, 0],
  ceilingIntensity: 1.15,
  ceilingPosition: [0, 5, 0.5],
  roomIntensity: 0.65,
  roomPosition: [-3, 2.5, 2],
  viewerIntensity: 6.5,
  viewerDistance: 14,
  viewerDecay: 1.8,
  viewerFollowCamera: true,
  viewerOffset: [0, 0.05, 0],
  viewerPosition: [0, 1.05, 1.65],
  keySpotIntensity: 2.8,
  keySpotDistance: 10,
  keySpotAngleDeg: 36,
  keySpotPenumbra: 0.12,
  keySpotDecay: 1.2,
  keySpotFollowCamera: true,
  keySpotPosition: [0, 2.2, 1.1],
  keySpotTarget: [0, 0.95, 0],
  keySpotCamX: 0.3,
  keySpotCamY: 1.1,
  keySpotCamZMul: 0.55,
  keySpotCamZAdd: 0.35,
};

/** Snap-to preset views for the viewer. Tune positions by eye if framing drifts. */
export const CAMERA_PRESETS = {
  hero: {
    position: [...HERO_CAMERA_DEFAULTS.position],
    target: [...HERO_CAMERA_DEFAULTS.target],
    fov: HERO_CAMERA_DEFAULTS.fov,
  },
  front: {
    position: [0.02, 1.19, 3.08],
    target: [0.01, 0.75, 0.03],
    fov: 42,
  },
  top: {
    position: [0, 3.0, 1.3],
    target: [0, 0.7, 0],
    fov: 46,
  },
  /** Player-at-keyboard view — used when live MIDI session starts. */
  seated: {
    position: [0.02, 1.58, 1.85],
    target: [0.01, 0.75, 0.74],
    fov: 42,
    exposure: 1.86,
  },
};

/**
 * Reference framing for the computer-keyboard octave range (no-MIDI mode),
 * hand-tuned in the scene-debug panel for the home range (C4–E5). The live view
 * keeps this distance/angle/height and pans to the active octave's keys, so the
 * framing stays consistent across octave shifts.
 */
export const KEYBOARD_RANGE_VIEW = {
  position: [0.06, 1.1, 1.22],
  target: [0.06, 0.75, 0.77],
  fov: 40,
  exposure: 1.86,
};

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
    color: new THREE.Color(lite ? 0xcfc8b8 : shiny ? 0x121212 : 0x0a0a0a),
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
function tuneMetal(mat, fallbackColor, fallbackRough) {
  prepMaps(mat);
  mat.metalness = 1.0;
  mat.roughness = fallbackRough;
  mat.envMapIntensity = 1.28;
  if (mat.normalMap) mat.normalScale.set(1.1, 1.1);
  // Render metal double-sided: the thin gold lid-spine trim (continuous-hinge
  // leaves + screw plate) are flat shells whose winding faces *into* the lid, so
  // single-sided FrontSide culls them and only the curved rod survives. The
  // global side assignment below honors this DoubleSide flag.
  mat.side = THREE.DoubleSide;
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
  // Inner rim wood sits under lacquer at the lid edge — nudge behind trim/lacquer.
  mat.polygonOffset = true;
  mat.polygonOffsetFactor = 1;
  mat.polygonOffsetUnits = 1;
  return mat;
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

    if (/^sy_lite/i.test(name)) {
      next = lacquerFromExport(mat, { matte: /matte/i.test(name), lite: true });
    } else if (/^sy_/i.test(name)) {
      next = lacquerFromExport(mat, { matte: /matte/i.test(name), lite: false });
    } else if (/gold/i.test(name)) {
      next = tuneMetal(mat, 0xd4af37, 0.24);
    } else if (/brass/i.test(name)) {
      next = tuneMetal(mat, 0xc6a456, 0.2);
    } else if (/copper/i.test(name)) {
      next = tuneMetal(mat, 0xb87333, 0.28);
    } else if (/steel|chrome|metal/i.test(name)) {
      next = tuneMetal(mat, 0xc6c4c0, 0.22);
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
 * Vignetted studio cyclorama: a soft warm-neutral glow behind the piano that
 * falls off to dark edges, so the backdrop has depth instead of reading flat.
 */
function radialBackground(center, mid, edge) {
  const c = document.createElement("canvas");
  c.width = c.height = 1024;
  const ctx = c.getContext("2d");
  // Focus the glow slightly above center so the horizon sits behind the piano.
  const g = ctx.createRadialGradient(512, 460, 30, 512, 470, 820);
  g.addColorStop(0.0, center);
  g.addColorStop(0.5, mid);
  g.addColorStop(1.0, edge);
  ctx.fillStyle = edge;
  ctx.fillRect(0, 0, 1024, 1024);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 1024, 1024);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = SRGB;
  return tex;
}

/** Bright room probe for lacquer / wood reflections. */
function roomEnvironment(pmrem) {
  const envScene = new THREE.Scene();
  // Neutral-gray probe matching Blender's neutral world (sRGB ~64). The glossy
  // black lacquer is effectively a mirror, so a blue probe (was 0x2a3040 bg,
  // cool fill 0xc0c8d8) tinted the whole body blue. Keep it neutral/warm so the
  // body reads as the neutral black of the Blender render.
  envScene.background = new THREE.Color(0x3a3a3a);
  envScene.add(new THREE.AmbientLight(0xefece6, 1.1));
  const window = new THREE.DirectionalLight(0xfff6ec, 1.6);
  window.position.set(1, 3, 4);
  envScene.add(window);
  const fill = new THREE.DirectionalLight(0xd2cec6, 0.75);
  fill.position.set(-2, 2, -1);
  envScene.add(fill);

  // Bright overhead softbox panels — glossy black lacquer needs distinct bright
  // shapes to reflect, otherwise it has no highlights and reads as flat.
  const panel = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const makePanel = (w, h, x, y, z, rx) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), panel);
    m.position.set(x, y, z);
    m.rotation.x = rx;
    envScene.add(m);
  };
  makePanel(7, 2.6, 0, 7.5, 1.5, -Math.PI / 2); // ceiling strip overhead
  makePanel(5, 3.5, 0, 4.5, 6.5, 0); // front fill window
  makePanel(2.8, 1.6, -3.5, 3.2, 2, 0.15); // side kicker for lacquer edge highlights

  return pmrem.fromScene(envScene, 0.04).texture;
}

/** Light room backdrop + IBL (seated viewing context). */
export function setupEnvironment(renderer, scene) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = roomEnvironment(pmrem);
  scene.background = radialBackground("#c9c6bf", "#9a9ca2", "#33363d");
  // Fog was flattening surface detail — keep backdrop gradient only.
  scene.fog = null;
  pmrem.dispose();
  return scene.environment;
}

/**
 * Lighting as if you're seated at the piano: room fill + lamp from your viewpoint.
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

  // Neutral fill (was cool 0xf2f4fa / hemi ground 0x9098a8 / room 0xe8ecf8) so
  // diffuse parts and the matte body don't pick up a blue tint — Blender's world
  // and lamps are neutral. Warm key/viewer lights are kept warm.
  const ambient = new THREE.AmbientLight(0xf4f2ee, d.ambientIntensity);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0xfaf8f4, 0x9a988f, d.hemiIntensity);
  hemi.position.set(...d.hemiPosition);
  scene.add(hemi);

  const ceiling = new THREE.DirectionalLight(0xfffaf5, d.ceilingIntensity);
  ceiling.position.set(...d.ceilingPosition);
  scene.add(ceiling);

  const room = new THREE.DirectionalLight(0xefece6, d.roomIntensity);
  room.position.set(...d.roomPosition);
  scene.add(room);

  const viewerLight = new THREE.PointLight(
    0xfff6ea,
    d.viewerIntensity,
    d.viewerDistance,
    d.viewerDecay,
  );
  viewerLight.position.set(...d.viewerPosition);
  viewerLight.castShadow = true;
  viewerLight.shadow.mapSize.set(1024, 1024);
  viewerLight.shadow.bias = -0.0002;
  viewerLight.shadow.normalBias = 0.012;
  scene.add(viewerLight);

  const keySpotAngle = THREE.MathUtils.degToRad(d.keySpotAngleDeg);
  const keySpot = new THREE.SpotLight(
    0xffffff,
    d.keySpotIntensity,
    d.keySpotDistance,
    keySpotAngle,
    d.keySpotPenumbra,
    d.keySpotDecay,
  );
  keySpot.position.set(...d.keySpotPosition);
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
 * Custom Reflector shader: a true planar mirror, but dimmed toward a dark floor
 * base and faded out with distance so the piano reflection reads near the center
 * while the far floor melts into the backdrop (no hard disc-edge horizon).
 * `color`, `tDiffuse`, `textureMatrix` are required by the Reflector constructor.
 */
const STUDIO_FLOOR_SHADER = {
  name: "StudioFloorReflectorShader",
  uniforms: {
    color: { value: null },
    tDiffuse: { value: null },
    textureMatrix: { value: null },
    uFloorColor: { value: new THREE.Color(0x23262c) },
    uReflStrength: { value: 0.55 },
    uFadeStart: { value: 3.0 },
    uFadeEnd: { value: 14.0 },
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
    uniform float uReflStrength;
    uniform float uFadeStart;
    uniform float uFadeEnd;
    varying vec4 vUv;
    varying float vDist;

    #include <logdepthbuf_pars_fragment>

    float blendOverlay( float base, float blend ) {
      return( base < 0.5 ? ( 2.0 * base * blend ) : ( 1.0 - 2.0 * ( 1.0 - base ) * ( 1.0 - blend ) ) );
    }
    vec3 blendOverlay( vec3 base, vec3 blend ) {
      return vec3( blendOverlay( base.r, blend.r ), blendOverlay( base.g, blend.g ), blendOverlay( base.b, blend.b ) );
    }

    void main() {
      #include <logdepthbuf_fragment>
      vec4 base = texture2DProj( tDiffuse, vUv );
      vec3 refl = blendOverlay( base.rgb, color );
      float fade = 1.0 - smoothstep( uFadeStart, uFadeEnd, vDist );
      vec3 col = mix( uFloorColor, refl, uReflStrength * fade );
      gl_FragColor = vec4( col, 1.0 );
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
export function createStudioGround(scene) {
  const dpr = Math.min(window.devicePixelRatio, 2);
  const floor = new Reflector(new THREE.PlaneGeometry(80, 80), {
    textureWidth: window.innerWidth * dpr,
    textureHeight: window.innerHeight * dpr,
    clipBias: 0.003,
    // Neutral tint: dimming is handled by the shader's mix toward uFloorColor.
    color: 0x808080,
    shader: STUDIO_FLOOR_SHADER,
  });
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0;
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
      opacity: 0.9,
    }),
  );
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.set(center.x, 0.004, center.z);
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
