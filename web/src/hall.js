/**
 * Carnegie Hall set for the web viewer.
 *
 * The hall is generated in Blender by scripts/build_carnegie_hall.py in the
 * piano's own world frame (stage top under the feet, house toward +X), so it
 * lines up by taking the same framing transform frameModel gave the piano.
 * Its Hall_Light vertex colours carry lighting baked in Cycles (stage wash,
 * house lamps, bounce and occlusion), so the room is drawn unlit — far
 * cheaper per pixel than lit PBR on surfaces that fill the screen.
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
/** Brightness of the baked lighting (the bake puts typical surfaces near 0.5). */
const HALL_EXPOSURE = 1.3;
/** Gilt leaf reads brighter than its albedo under stage light. */
const GILT_GAIN = 1.3;
/** Self-lit lamps and exit signs, pushed past white so ACES blooms them warm. */
const LAMP_GAIN = 3.0;

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
    const old = obj.material;
    obj.material = hallMaterial(old);
    if (obj.material !== old) old.dispose();
    // Baked surfaces can't take the shadow map; the piano's shadow lands on
    // a catcher plane instead (createStageShadowCatcher).
    obj.castShadow = false;
    obj.receiveShadow = false;
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

/**
 * Every hall surface becomes unlit MeshBasicMaterial: albedo x baked light.
 * @param {THREE.Material} mat
 */
function hallMaterial(mat) {
  if (!mat?.isMeshStandardMaterial) return mat;
  const name = mat.name || "";
  const lamp = /bulb|exit/i.test(name);
  const gain = lamp ? LAMP_GAIN : HALL_EXPOSURE * (/gold/i.test(name) ? GILT_GAIN : 1);
  return new THREE.MeshBasicMaterial({
    name,
    color: mat.color.clone().multiplyScalar(gain),
    vertexColors: !lamp,
    // Winding isn't curated in the procedural build.
    side: THREE.DoubleSide,
  });
}

/**
 * Transparent plane that only shows the piano's shadow on the baked stage.
 * @param {THREE.Object3D} piano
 */
export function createStageShadowCatcher(piano) {
  const box = new THREE.Box3().setFromObject(piano);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const catcher = new THREE.Mesh(
    new THREE.PlaneGeometry(size.x * 2.6, size.z * 2.6),
    new THREE.ShadowMaterial({
      opacity: 0.4,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1,
    }),
  );
  catcher.name = "Stage_Shadow_Catcher";
  catcher.rotation.x = -Math.PI / 2;
  // Between the boards (−3 mm) and the contact blob, like the studio stack.
  catcher.position.set(center.x, 0.0008, center.z);
  catcher.receiveShadow = true;
  catcher.renderOrder = 1;
  return catcher;
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
