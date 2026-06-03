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

/** Aim camera and orbit target at the model for a flattering 3/4 view. */
export function fitCameraToModel(camera, controls, root) {
  root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() * 0.5, 0.6);

  controls.target.copy(center);
  const offset = new THREE.Vector3(0.62, 0.5, 1.0)
    .normalize()
    .multiplyScalar(radius * 1.9);
  camera.position.copy(center).add(offset);
  camera.near = Math.max(0.01, radius / 200);
  camera.far = Math.max(50, radius * 40);
  camera.updateProjectionMatrix();
  controls.update();
  return { radius, center };
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
  const color = mat.color?.clone() ?? new THREE.Color(lite ? 0xcfc8b8 : 0x000000);
  const roughness =
    typeof mat.roughness === "number"
      ? mat.roughness
      : matte
        ? lite
          ? 0.85
          : 1.0
        : 0.1;
  return new THREE.MeshPhysicalMaterial({
    color,
    roughness,
    metalness: 0,
    clearcoat: matte ? (lite ? 0 : 0.2) : lite ? 0.4 : 0.88,
    clearcoatRoughness: matte ? 0.32 : lite ? 0.2 : 0.04,
    envMapIntensity: lite ? 0.18 : 0.14,
    specularIntensity: lite ? 0.65 : 0.85,
    specularColor: new THREE.Color(lite ? 0xffffff : 0xbbbcc4),
  });
}

/** Seat Cushion — CW-Plastic-Dapple tile from the .blend (not flat gray plastic). */
function dappleCushion(mat) {
  const opts = {
    name: mat.name,
    color: new THREE.Color(0xffffff),
    metalness: 0,
    roughness: typeof mat.roughness === "number" ? mat.roughness : 0.38,
    envMapIntensity: 0.72,
  };
  if (mat.map) {
    opts.map = mat.map;
    opts.bumpMap = mat.bumpMap ?? mat.normalMap ?? mat.map;
    opts.bumpScale = mat.bumpScale > 0 ? mat.bumpScale : 0.22;
  }
  if (mat.roughnessMap) opts.roughnessMap = mat.roughnessMap;
  if (mat.normalMap) {
    opts.normalMap = mat.normalMap;
    delete opts.bumpMap;
    delete opts.bumpScale;
  }
  const next = new THREE.MeshStandardMaterial(opts);
  if (next.normalMap) next.normalScale.set(1.25, 1.25);
  prepMaps(next);
  return next;
}

function tuneMetal(mat, fallbackColor, fallbackRough) {
  prepMaps(mat);
  mat.metalness = 1.0;
  if (!mat.roughnessMap && typeof mat.roughness !== "number") {
    mat.roughness = fallbackRough;
  }
  mat.envMapIntensity = 0.85;
  if (mat.normalMap) mat.normalScale.set(1.1, 1.1);
  if (!mat.map) mat.color = new THREE.Color(fallbackColor);
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
      mat.envMapIntensity = 0.9;
      if (mat.normalMap) mat.normalScale.set(1.15, 1.15);
      if (!mat.map) mat.color = new THREE.Color(0x7c5a3a);
      next = mat;
    } else if (/dapple|CW-Plastic/i.test(name)) {
      next = dappleCushion(mat);
    } else if (/plastic/i.test(name)) {
      prepMaps(mat);
      mat.metalness = 0;
      mat.roughness = mat.roughness ?? 0.5;
      mat.envMapIntensity = 0.5;
      if (!mat.map) mat.color = new THREE.Color(0x141416);
      else mat.color.setRGB(1, 1, 1);
      next = mat;
    } else {
      prepMaps(mat);
      if (!mat.map) mat.color = new THREE.Color(0x2a2a2e);
      mat.envMapIntensity = 0.8;
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

/** Low-key PMREM so metal/wood get subtle reflections without washing black lacquer. */
function darkStudioEnvironment(pmrem) {
  const envScene = new THREE.Scene();
  envScene.add(new THREE.AmbientLight(0x384050, 0.7));
  const soft = new THREE.DirectionalLight(0xb8c0d0, 1.0);
  soft.position.set(2, 4, 3);
  envScene.add(soft);
  const fill = new THREE.DirectionalLight(0x505868, 0.55);
  fill.position.set(-3, 1, -2);
  envScene.add(fill);
  return pmrem.fromScene(envScene, 0.04).texture;
}

/**
 * Dark gradient backdrop + low-key IBL. Lacquer (sy_*) ignores env maps;
 * brass/wood use a dim environment so they do not blow out to gray.
 */
export function setupEnvironment(renderer, scene) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = darkStudioEnvironment(pmrem);
  scene.background = radialBackground("#2e3648", "#121820");
  // Fog was flattening surface detail — keep backdrop gradient only.
  scene.fog = null;
  pmrem.dispose();
  return scene.environment;
}

/**
 * Multi-angle rig so lacquer edges, keys, and bench texture read in the viewport.
 * @returns {{ key: THREE.DirectionalLight }}
 */
export function setupStudioLights(scene) {
  scene.add(new THREE.AmbientLight(0x4a5268, 0.32));

  const hemi = new THREE.HemisphereLight(0x8898b8, 0x1a2030, 0.55);
  scene.add(hemi);

  const key = new THREE.DirectionalLight(0xfff8f0, 2.6);
  key.position.set(3.5, 6, 2.8);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.intensity = 0.42;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 18;
  const s = 3.5;
  key.shadow.camera.left = -s;
  key.shadow.camera.right = s;
  key.shadow.camera.top = s;
  key.shadow.camera.bottom = -s;
  key.shadow.bias = -0.0003;
  key.shadow.normalBias = 0.015;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xe8e4dc, 1.1);
  fill.position.set(-2.5, 3.5, 4.5);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xa8c0e8, 0.75);
  rim.position.set(-5, 4, -3);
  scene.add(rim);

  // Low raking lights pick up lid mouldings, legs, and key sides.
  const rakeL = new THREE.DirectionalLight(0xd8dce8, 0.55);
  rakeL.position.set(-6, 1.2, 2);
  scene.add(rakeL);

  const rakeR = new THREE.DirectionalLight(0xd0ccc4, 0.45);
  rakeR.position.set(5, 1.5, 1);
  scene.add(rakeR);

  const under = new THREE.DirectionalLight(0x9098a8, 0.28);
  under.position.set(0, 0.5, 5);
  scene.add(under);

  return { key };
}

/** Dark, subtly reflective studio floor (env-lit sheen — no extra render pass). */
export function createStudioGround(scene) {
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(40, 96),
    new THREE.MeshStandardMaterial({
      color: 0x141820,
      roughness: 0.32,
      metalness: 0.65,
      envMapIntensity: 0.9,
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
