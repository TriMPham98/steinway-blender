import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

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

function metalize(mat, color, roughness) {
  mat.color = new THREE.Color(color);
  mat.metalness = 1.0;
  mat.roughness = roughness;
  mat.envMapIntensity = 1.3;
  if (mat.map) mat.map.colorSpace = SRGB;
  return mat;
}

/**
 * The GLB's procedural "smart material" body/keys arrive flat from glTF (node
 * groups don't translate), so pin them by material name; metals/wood keep their
 * exported image textures and just get sensible PBR + IBL response.
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
      // Ivory white keys + light parts.
      const matte = /matte/i.test(name);
      next = new THREE.MeshPhysicalMaterial({
        color: 0xece4d2,
        roughness: matte ? 0.6 : 0.36,
        metalness: 0,
        clearcoat: matte ? 0 : 0.35,
        clearcoatRoughness: 0.25,
        envMapIntensity: 0.5,
      });
    } else if (/^sy_/i.test(name)) {
      // Every other smart material = polished black lacquer body / ebony keys.
      // Keep envMapIntensity low so the bright IBL doesn't wash the black to gray;
      // clearcoat still gives the lacquered specular highlights.
      const matte = /matte/i.test(name);
      next = new THREE.MeshPhysicalMaterial({
        color: 0x08080a,
        roughness: matte ? 0.5 : 0.12,
        metalness: 0,
        clearcoat: matte ? 0.2 : 1.0,
        clearcoatRoughness: 0.05,
        envMapIntensity: matte ? 0.25 : 0.45,
      });
    } else if (/gold/i.test(name)) {
      next = metalize(mat, 0xd4af37, 0.3);
    } else if (/brass/i.test(name)) {
      next = metalize(mat, 0xc6a456, 0.32);
    } else if (/copper/i.test(name)) {
      next = metalize(mat, 0xb87333, 0.34);
    } else if (/steel|chrome|metal/i.test(name)) {
      next = metalize(mat, 0xc2c6cd, 0.28);
    } else if (/wood|beech|maple/i.test(name)) {
      // Flattened on export (node-group textures bake too slowly); warm solid
      // wood tone, and keep a map if a textured GLB is ever loaded.
      mat.color = new THREE.Color(0x7c5a3a);
      mat.metalness = 0;
      mat.roughness = 0.55;
      mat.envMapIntensity = 0.9;
      if (mat.map) mat.map.colorSpace = SRGB;
      next = mat;
    } else if (/plastic|dapple/i.test(name)) {
      mat.color = new THREE.Color(0x141416);
      mat.metalness = 0;
      mat.roughness = 0.7;
      mat.envMapIntensity = 0.6;
      next = mat;
    } else {
      mat.color = new THREE.Color(0x2a2a2e);
      mat.envMapIntensity = 0.8;
      if (mat.map) mat.map.colorSpace = SRGB;
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

/**
 * Image-based lighting (procedural studio) + dark gradient backdrop + fog.
 * Reflections on the lacquer/metal come from scene.environment.
 */
export function setupEnvironment(renderer, scene) {
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.background = radialBackground("#16181f", "#05060a");
  scene.fog = new THREE.Fog(0x05060a, 7, 24);
  pmrem.dispose();
  return scene.environment;
}

/** Dark, subtly reflective studio floor (env-lit sheen — no extra render pass). */
export function createStudioGround(scene) {
  const ground = new THREE.Mesh(
    new THREE.CircleGeometry(40, 96),
    new THREE.MeshStandardMaterial({
      color: 0x0a0c11,
      roughness: 0.34,
      metalness: 0.7,
      envMapIntensity: 0.7,
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
