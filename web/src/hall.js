/**
 * Carnegie Hall set for the web viewer.
 *
 * The hall is generated in Blender by scripts/build_carnegie_hall.py in the
 * piano's own world frame (stage top under the feet, house toward +X), so it
 * lines up by taking the same framing transform frameModel gave the piano.
 * Its Hall_Light vertex colours carry a baked stage-to-house falloff; the
 * viewer's piano lights then light it like everything else.
 */
import * as THREE from "three";

export const HALL_URL = "/models/carnegie_hall.min.glb";

/** Far plane / orbit radius once the whole auditorium is in play. */
const HALL_CAMERA_FAR = 120;
const HALL_MAX_DISTANCE = 24;
/** Keep the orbiting eye this far inside the walls, floor and ceiling. */
const HALL_WALL_MARGIN = 0.6;
/** DOME_H in build_carnegie_hall.py: how far the dome rises above the ceiling. */
const HALL_DOME_RISE = 2.8;

/**
 * Load the hall. Resolves null when it's missing or broken so the viewer
 * keeps the studio floor.
 * @param {import("three/examples/jsm/loaders/GLTFLoader.js").GLTFLoader} loader
 * @returns {Promise<THREE.Object3D | null>}
 */
export function loadHall(loader) {
  return new Promise((resolve) => {
    loader.load(
      HALL_URL,
      (gltf) => resolve(gltf.scene),
      undefined,
      (err) => {
        console.warn("[hall] Carnegie Hall unavailable — studio floor only:", err);
        resolve(null);
      },
    );
  });
}

/**
 * Seat the hall around the framed piano and tune its materials.
 * @param {THREE.Object3D} hall
 * @param {THREE.Object3D} piano  frameModel'd piano root
 * @returns {{ root: THREE.Object3D, bounds: THREE.Box3 }}
 */
export function prepareHall(hall, piano) {
  hall.name = "Carnegie_Hall";
  hall.position.copy(piano.position);
  hall.quaternion.copy(piano.quaternion);
  hall.scale.copy(piano.scale);
  hall.updateMatrixWorld(true);

  hall.traverse((obj) => {
    if (!obj.isMesh) return;
    obj.material = refineHallMaterial(obj.material);
    // Only the stage takes the piano's shadow; nothing in the hall casts (the
    // shadow camera only covers the piano anyway).
    obj.castShadow = false;
    obj.receiveShadow = /stage/i.test(obj.name);
    obj.matrixAutoUpdate = false;
  });

  // Interior volume (walls in, floor/ceiling) for clamping the orbit camera.
  const bounds = new THREE.Box3();
  hall.traverse((obj) => {
    if (obj.isMesh && /plaster/i.test(obj.name)) bounds.expandByObject(obj);
  });
  bounds.expandByScalar(-HALL_WALL_MARGIN);
  // The plaster box reaches up into the dome; cap at the flat ceiling instead.
  bounds.max.y -= HALL_DOME_RISE * hall.scale.y;
  bounds.min.y = 0.25; // stay above the stage boards
  return { root: hall, bounds };
}

/** @param {THREE.Material} mat */
function refineHallMaterial(mat) {
  if (!mat?.isMeshStandardMaterial) return mat;
  const name = mat.name || "";
  // Winding is not curated in the procedural build; DoubleSide also flips the
  // normal for back faces, so shading stays correct either way.
  mat.side = THREE.DoubleSide;
  // The studio IBL is a softbox room; keep its reflections faint on the set.
  mat.envMapIntensity = 0.25;
  if (/bulb/i.test(name)) {
    mat.emissiveIntensity = 1.4;
    mat.toneMapped = true;
  } else if (/gold/i.test(name)) {
    mat.envMapIntensity = 0.9;
    mat.roughness = 0.38;
  } else if (/stage_wood/i.test(name)) {
    mat.envMapIntensity = 0.45;
  }
  mat.needsUpdate = true;
  return mat;
}

/**
 * Switch camera limits between the studio and the hall.
 * @param {THREE.PerspectiveCamera} camera
 * @param {import("three/examples/jsm/controls/OrbitControls.js").OrbitControls} controls
 * @param {boolean} inHall
 * @param {{ far: number, maxDistance: number }} studio  studio-mode values to restore
 */
export function applyHallCameraLimits(camera, controls, inHall, studio) {
  camera.far = inHall ? Math.max(studio.far, HALL_CAMERA_FAR) : studio.far;
  camera.updateProjectionMatrix();
  controls.maxDistance = inHall ? HALL_MAX_DISTANCE : studio.maxDistance;
}

/**
 * Keep the eye inside the auditorium. Returns true if it had to move.
 * @param {THREE.Vector3} eye
 * @param {THREE.Box3} bounds
 */
export function clampToHall(eye, bounds) {
  const before = eye.clone();
  bounds.clampPoint(eye, eye);
  return !before.equals(eye);
}
