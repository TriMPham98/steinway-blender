import * as THREE from "three";

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
  ceilingIntensity: 1.15,
  ceilingPosition: [0, 5, 0.5],
  roomIntensity: 0.65,
  roomPosition: [-3, 2.5, 2],
  viewerIntensity: 6.5,
  viewerDistance: 14,
  viewerDecay: 1.8,
  keySpotIntensity: 2.8,
};

/** Snap-to preset views for the viewer. Tune positions by eye if framing drifts. */
export const CAMERA_PRESETS = {
  hero: {
    position: [...HERO_CAMERA_DEFAULTS.position],
    target: [...HERO_CAMERA_DEFAULTS.target],
    fov: HERO_CAMERA_DEFAULTS.fov,
  },
  front: {
    position: [0, 1.05, 2.6],
    target: [0, 0.7, 0],
    fov: 42,
  },
  top: {
    position: [0, 3.0, 1.3],
    target: [0, 0.7, 0],
    fov: 46,
  },
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
  camera.near = Math.max(0.01, pose.radius / 200);
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
  const roughness =
    typeof mat.roughness === "number"
      ? mat.roughness
      : matte
        ? lite
          ? 0.85
          : 1.0
        : 0.1;
  return new THREE.MeshPhysicalMaterial({
    // Blender base is pure black; lift it a hair so unreflected areas read as
    // deep charcoal (mimics Blender's view-transform black lift) instead of an
    // ACES-crushed void that flattens the piano into a silhouette.
    color: new THREE.Color(lite ? 0xcfc8b8 : 0x0a0a0a),
    roughness,
    metalness: 0,
    clearcoat: matte ? (lite ? 0 : 0.12) : lite ? 0.28 : 0.85,
    clearcoatRoughness: matte ? 0.4 : lite ? 0.22 : 0.06,
    // Glossy lacquer gets its form from reflecting the room — the old 0.52 barely
    // picked up the environment, so the black lid looked flat. Crank it up.
    envMapIntensity: lite ? 0.7 : matte ? 0.95 : 1.35,
    specularIntensity: lite ? 0.65 : 0.62,
    specularColor: new THREE.Color(lite ? 0xffffff : 0xd0d4e0),
  });
}

function tuneMetal(mat, fallbackColor, fallbackRough) {
  prepMaps(mat);
  mat.metalness = 1.0;
  if (!mat.roughnessMap && typeof mat.roughness !== "number") {
    mat.roughness = fallbackRough;
  }
  mat.envMapIntensity = 1.05;
  if (mat.normalMap) mat.normalScale.set(1.1, 1.1);
  // The materialiq metals export a flat *grayscale* base-color texture; the gold/
  // brass/copper hue lived in the Blender base-color factor, which glTF dropped
  // (defaults to white). Used as albedo, that gray map makes the metal mirror the
  // gray environment and read as chrome. Drop it and apply the metal's own tint so
  // reflections pick up the right color — normal + roughness/metalness maps stay.
  if (mat.map) {
    mat.map.dispose?.();
    mat.map = null;
  }
  mat.color = new THREE.Color(fallbackColor);
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
      next = tuneMetal(mat, 0xd4af37, 0.3);
    } else if (/brass/i.test(name)) {
      next = tuneMetal(mat, 0xc6a456, 0.32);
    } else if (/copper/i.test(name)) {
      next = tuneMetal(mat, 0xb87333, 0.34);
    } else if (/steel|chrome|metal/i.test(name)) {
      next = tuneMetal(mat, 0xc2c6cd, 0.28);
    } else if (/wood|beech|maple/i.test(name)) {
      prepMaps(mat);
      mat.metalness = 0;
      if (!mat.roughnessMap && typeof mat.roughness !== "number") {
        mat.roughness = 0.55;
      }
      mat.envMapIntensity = 1.1;
      if (mat.normalMap) mat.normalScale.set(1.15, 1.15);
      if (!mat.map) mat.color = new THREE.Color(0x7c5a3a);
      next = mat;
    } else if (/plastic/i.test(name)) {
      prepMaps(mat);
      mat.metalness = 0;
      mat.roughness = mat.roughness ?? 0.5;
      mat.envMapIntensity = 0.75;
      if (!mat.map) mat.color = new THREE.Color(0x141416);
      else mat.color.setRGB(1, 1, 1);
      next = mat;
    } else {
      prepMaps(mat);
      if (!mat.map) mat.color = new THREE.Color(0x2a2a2e);
      mat.envMapIntensity = 1.0;
      next = mat;
    }

    next.side = THREE.FrontSide;
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

function radialBackground(inner, outer) {
  const c = document.createElement("canvas");
  c.width = c.height = 1024;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(512, 470, 40, 512, 470, 760);
  g.addColorStop(0, inner);
  g.addColorStop(1, outer);
  ctx.fillStyle = outer;
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
  envScene.background = new THREE.Color(0x2a3040);
  envScene.add(new THREE.AmbientLight(0xe8ecf4, 1.1));
  const window = new THREE.DirectionalLight(0xfff8f0, 1.6);
  window.position.set(1, 3, 4);
  envScene.add(window);
  const fill = new THREE.DirectionalLight(0xc0c8d8, 0.75);
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
  makePanel(6, 2.2, 0, 7, 1.5, -Math.PI / 2); // ceiling strip overhead
  makePanel(4, 3, 0, 4, 6, 0); // front fill window

  return pmrem.fromScene(envScene, 0.04).texture;
}

/** Light room backdrop + IBL (seated viewing context). */
export function setupEnvironment(renderer, scene) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = roomEnvironment(pmrem);
  scene.background = radialBackground("#b8c0cc", "#8a94a4");
  // Fog was flattening surface detail — keep backdrop gradient only.
  scene.fog = null;
  pmrem.dispose();
  return scene.environment;
}

/**
 * Lighting as if you're seated at the piano: room fill + lamp from your viewpoint.
 * @returns {{ viewerLight: THREE.PointLight, syncViewerLight: (pos: THREE.Vector3) => void }}
 */
export function setupSeatedViewerLights(scene) {
  const d = LIGHTING_DEFAULTS;

  const ambient = new THREE.AmbientLight(0xf2f4fa, d.ambientIntensity);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0xf8fafc, 0x9098a8, d.hemiIntensity);
  scene.add(hemi);

  const ceiling = new THREE.DirectionalLight(0xfffaf5, d.ceilingIntensity);
  ceiling.position.set(...d.ceilingPosition);
  scene.add(ceiling);

  const room = new THREE.DirectionalLight(0xe8ecf8, d.roomIntensity);
  room.position.set(...d.roomPosition);
  scene.add(room);

  const viewerLight = new THREE.PointLight(
    0xfff6ea,
    d.viewerIntensity,
    d.viewerDistance,
    d.viewerDecay,
  );
  viewerLight.position.set(0, 1.05, 1.65);
  viewerLight.castShadow = true;
  viewerLight.shadow.mapSize.set(1024, 1024);
  viewerLight.shadow.bias = -0.0002;
  viewerLight.shadow.normalBias = 0.012;
  scene.add(viewerLight);

  const keySpot = new THREE.SpotLight(0xffffff, d.keySpotIntensity, 10, Math.PI / 5, 0.12, 1.2);
  keySpot.position.set(0, 2.2, 1.1);
  const keyTarget = new THREE.Object3D();
  keyTarget.position.set(0, 0.95, 0);
  scene.add(keyTarget);
  keySpot.target = keyTarget;
  scene.add(keySpot);

  const syncViewerLight = (eyePosition) => {
    viewerLight.position.copy(eyePosition);
    viewerLight.position.y += 0.05;
    keySpot.position.set(
      eyePosition.x * 0.3,
      eyePosition.y + 1.1,
      eyePosition.z * 0.55 + 0.35,
    );
  };

  return {
    lights: { ambient, hemi, ceiling, room, viewerLight, keySpot },
    syncViewerLight,
  };
}

/** Subtly reflective studio floor (env-lit sheen — no extra render pass). */
export function createStudioGround(scene) {
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(40, 96),
    new THREE.MeshStandardMaterial({
      color: 0x4a5260,
      roughness: 0.55,
      metalness: 0.35,
      envMapIntensity: 1.0,
    }),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = 0;
  ground.receiveShadow = true;
  scene.add(ground);
  return ground;
}

export function setupShadows(root) {
  root.traverse((obj) => {
    if (obj.isMesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
    }
  });
}
