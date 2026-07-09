/**
 * Carnegie Hall set for the web viewer.
 *
 * Loads the low-poly hall GLB exported from assets/carnegie_hall.blend
 * (scripts/export_carnegie_glb.py), places it so the stage top sits at Y=0
 * under the frameModel-grounded piano, and refines materials for the stage
 * lighting + Carnegie HDRI stack.
 */
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

export const HALL_MODEL_URL = "/models/carnegie_hall.glb";
export const HALL_META_URL = "/models/carnegie_hall.meta.json";

/** Camera far plane when the full auditorium is visible (~40 m shell). */
export const HALL_CAMERA_FAR = 120;

/** Orbit pull-back limit so a wide “from the house” shot still works. */
export const HALL_MAX_DISTANCE = 28;

/**
 * @typedef {{
 *   stage_top_gltf_y?: number,
 *   camera_far_hint?: number,
 * }} HallMeta
 */

/**
 * Load hall GLB + optional meta. Resolves null if the asset is missing so the
 * studio floor path remains a graceful fallback.
 * @param {GLTFLoader} [loader]
 * @returns {Promise<{ root: THREE.Object3D, meta: HallMeta } | null>}
 */
export function loadHall(loader = new GLTFLoader()) {
  const gltfP = new Promise((resolve, reject) => {
    loader.load(HALL_MODEL_URL, resolve, undefined, reject);
  });
  const metaP = fetch(HALL_META_URL)
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));

  return Promise.all([gltfP, metaP])
    .then(([gltf, meta]) => {
      const root = gltf.scene;
      root.name = "Carnegie_Hall";
      return { root, meta: /** @type {HallMeta} */ (meta ?? {}) };
    })
    .catch((err) => {
      console.warn("[hall] failed to load Carnegie set — keeping studio floor:", err);
      return null;
    });
}

/**
 * Seat the hall in the three.js scene: stage top at Y=0, house toward +Z.
 * Does **not** call frameModel (would shrink the auditorium to product scale).
 *
 * @param {THREE.Object3D} root
 * @param {HallMeta} [meta]
 */
export function prepareHall(root, meta = {}) {
  // Open the house toward world +Z so stage left/right are ±X in the viewer.
  root.rotation.y = Math.PI;
  root.updateMatrixWorld(true);

  // Prefer Stage_Floor top; fall back to meta or whole-set max Y of floor-ish meshes.
  let stageTopY = meta.stage_top_gltf_y;
  if (stageTopY == null || !Number.isFinite(stageTopY)) {
    stageTopY = measureStageTopY(root);
  }
  if (Number.isFinite(stageTopY) && Math.abs(stageTopY) > 1e-4) {
    root.position.y -= stageTopY;
    root.updateMatrixWorld(true);
  }

  refineHallMaterials(root);
  setupHallShadows(root);
  return root;
}

/**
 * Place the framed Steinway on the live three.js stage: keyboard faces
 * **stage right** (performer’s right when facing the house).
 *
 * Runtime-only — no Blender re-export. Derives house / stage-right from the
 * hall meshes already in the scene, then yaws the piano so its keyboard side
 * (export local +Z) lines up with that axis and re-grounds the feet on Y=0.
 *
 * @param {THREE.Object3D} pianoRoot  frameModel’d piano (still keyboard-+Z local)
 * @param {THREE.Object3D} hallRoot   prepareHall’d Carnegie set
 */
export function placePianoOnStage(pianoRoot, hallRoot) {
  hallRoot.updateMatrixWorld(true);
  pianoRoot.updateMatrixWorld(true);

  const houseDir = measureHouseDirection(hallRoot);
  // Performer faces the house; stage right is their right-hand side on the floor.
  const stageRight = new THREE.Vector3(-houseDir.z, 0, houseDir.x);
  if (stageRight.lengthSq() < 1e-8) stageRight.set(-1, 0, 0);
  else stageRight.normalize();

  // Export keyboard faces local +Z. R_y(yaw)·(0,0,1) = (sin yaw, 0, cos yaw).
  const yaw = Math.atan2(stageRight.x, stageRight.z);
  pianoRoot.rotation.y = yaw;
  pianoRoot.updateMatrixWorld(true);

  const box = new THREE.Box3().setFromObject(pianoRoot);
  if (!box.isEmpty()) {
    pianoRoot.position.y -= box.min.y;
    pianoRoot.updateMatrixWorld(true);
  }

  return { houseDir, stageRight, yaw };
}

/**
 * Unit XZ direction from stage center toward the house (seats / audience).
 * @param {THREE.Object3D} hallRoot
 * @returns {THREE.Vector3}
 */
function measureHouseDirection(hallRoot) {
  const stage = findNamed(hallRoot, /stage_floor/i);
  const seats = findNamed(hallRoot, /^seats/i);
  const proscenium = findNamed(hallRoot, /proscenium(?!_trim)/i);

  const stageC = centerOf(stage) ?? new THREE.Vector3(0, 0, 0);
  // Prefer seats (true house); else opposite of proscenium/back wall.
  if (seats) {
    const dir = centerOf(seats).sub(stageC);
    dir.y = 0;
    if (dir.lengthSq() > 1e-6) return dir.normalize();
  }
  if (proscenium) {
    const dir = stageC.clone().sub(centerOf(proscenium));
    dir.y = 0;
    if (dir.lengthSq() > 1e-6) return dir.normalize();
  }
  return new THREE.Vector3(0, 0, 1);
}

/** @param {THREE.Object3D} root @param {RegExp} re */
function findNamed(root, re) {
  let hit = null;
  root.traverse((obj) => {
    if (hit || !obj.name) return;
    if (re.test(obj.name)) hit = obj;
  });
  return hit;
}

/** @param {THREE.Object3D | null} obj */
function centerOf(obj) {
  if (!obj) return null;
  const box = new THREE.Box3().setFromObject(obj);
  if (box.isEmpty()) return null;
  return box.getCenter(new THREE.Vector3());
}

/**
 * @param {THREE.Object3D} root
 * @returns {number}
 */
function measureStageTopY(root) {
  let stage = null;
  root.traverse((obj) => {
    if (obj.name === "Stage_Floor" || obj.name === "Stage_Floor_0") stage = obj;
  });
  const box = new THREE.Box3();
  if (stage) {
    box.setFromObject(stage);
    if (!box.isEmpty()) return box.max.y;
  }
  // Fallback: highest Y of any mesh named *Floor* (stage is above parquet).
  let maxY = 0;
  let found = false;
  root.traverse((obj) => {
    if (!obj.isMesh || !/floor/i.test(obj.name)) return;
    const b = new THREE.Box3().setFromObject(obj);
    if (b.isEmpty()) return;
    if (!found || b.max.y > maxY) {
      maxY = b.max.y;
      found = true;
    }
  });
  return found ? maxY : 0;
}

/**
 * Stage/floors receive shadows; large shell pieces cast so the lid/piano get
 * soft contact under the ceiling key. House lights stay non-shadowing (emissive).
 * @param {THREE.Object3D} root
 */
export function setupHallShadows(root) {
  root.traverse((obj) => {
    if (!obj.isMesh) return;
    const n = obj.name || "";
    const isEmissive = /house_light|house.?lights/i.test(n);
    const isFloor = /floor|stage/i.test(n);
    obj.receiveShadow = true;
    obj.castShadow = !isEmissive && !isFloor;
  });
}

/**
 * Re-author hall materials by name (glTF names come from the blend).
 * @param {THREE.Object3D} root
 */
export function refineHallMaterials(root) {
  root.traverse((obj) => {
    if (!obj.isMesh) return;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    const next = mats.map((mat) => refineOneHallMaterial(mat));
    obj.material = Array.isArray(obj.material) ? next : next[0];
  });
}

/**
 * @param {THREE.Material} mat
 * @returns {THREE.Material}
 */
function refineOneHallMaterial(mat) {
  if (!mat || !mat.isMeshStandardMaterial) return mat;
  const name = mat.name || "";

  mat.side = THREE.FrontSide;
  mat.envMapIntensity = 0.45;

  if (/house_light/i.test(name)) {
    // Chandeliers — soft warm glow without blowing ACES exposure.
    mat.color.set(0xfff0d4);
    mat.emissive.set(0xffe0a8);
    mat.emissiveIntensity = 2.4;
    mat.roughness = 0.45;
    mat.metalness = 0;
    mat.envMapIntensity = 0.2;
  } else if (/gold/i.test(name)) {
    mat.color.set(0xd4af5a);
    mat.metalness = 0.92;
    mat.roughness = 0.36;
    mat.envMapIntensity = 0.85;
  } else if (/velvet|carpet/i.test(name)) {
    mat.color.set(/carpet/i.test(name) ? 0x5a1420 : 0x7a1822);
    mat.metalness = 0;
    mat.roughness = 0.92;
    mat.envMapIntensity = 0.2;
  } else if (/wood|stage/i.test(name)) {
    mat.color.set(0x6b4428);
    mat.metalness = 0.05;
    mat.roughness = 0.48;
    mat.envMapIntensity = 0.35;
  } else if (/plaster|cream|dome|parquet/i.test(name)) {
    mat.color.set(0xe8dcc4);
    mat.metalness = 0;
    mat.roughness = 0.72;
    mat.envMapIntensity = 0.3;
  } else {
    // Unknown hall mat — keep exported color, quiet the IBL.
    mat.metalness = Math.min(mat.metalness ?? 0, 0.2);
    mat.roughness = Math.max(mat.roughness ?? 0.6, 0.45);
  }

  mat.needsUpdate = true;
  return mat;
}

/**
 * Apply hall-present camera limits (far plane + orbit distance).
 * @param {THREE.PerspectiveCamera} camera
 * @param {import('three/examples/jsm/controls/OrbitControls.js').OrbitControls} controls
 * @param {HallMeta} [meta]
 */
export function applyHallCameraLimits(camera, controls, meta = {}) {
  const far = meta.camera_far_hint ?? HALL_CAMERA_FAR;
  camera.far = Math.max(camera.far, far);
  camera.updateProjectionMatrix();
  if (controls) {
    controls.maxDistance = Math.max(controls.maxDistance, HALL_MAX_DISTANCE);
    // Studio default (~0.49π) stops just short of horizontal — raise it so
    // the player can tip up into the dome / house lights.
    controls.maxPolarAngle = Math.max(controls.maxPolarAngle, Math.PI * 0.88);
  }
}
