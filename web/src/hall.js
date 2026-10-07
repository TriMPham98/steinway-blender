/**
 * Carnegie Hall set for the web viewer.
 *
 * The hall is generated in Blender by scripts/build_carnegie_hall.py in the
 * piano's own world frame (stage top under the feet, house toward +X), so it
 * lines up by taking the same framing transform frameModel gave the piano.
 * Its Hall_Light vertex colours carry lighting baked in Cycles (stage wash,
 * house lamps, bounce and occlusion), so the room is drawn unlit — far
 * cheaper per pixel than lit PBR on surfaces that fill the screen — over its
 * generated detail textures, plus a small view-dependent term per material
 * (HALL_SHADING) and an additive halo on every lamp.
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
/** Lamp halo diameter in metres, and the grid that groups each lamp's vertices. */
const LAMP_GLOW_SIZE = 0.7;
const LAMP_CLUSTER = 0.3;

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
 * @param {number} [anisotropy]  texture filtering for the grazing stage boards
 * @returns {{ root: THREE.Object3D, bounds: THREE.Box3 }}
 */
export function prepareHall(hall, piano, anisotropy = 1) {
  hall.name = "Carnegie_Hall";
  hall.position.copy(piano.position);
  hall.quaternion.copy(piano.quaternion);
  hall.scale.copy(piano.scale);
  hall.updateMatrixWorld(true);

  hall.traverse((obj) => {
    if (!obj.isMesh) return;
    const old = obj.material;
    obj.material = hallMaterial(old, anisotropy);
    if (obj.material !== old) old.dispose();
    // Baked surfaces can't take the shadow map; the piano's shadow lands on
    // a catcher plane instead (createStageShadowCatcher).
    obj.castShadow = false;
    obj.receiveShadow = false;
    obj.matrixAutoUpdate = false;
  });

  const bulbs = hall.getObjectByName("Hall_Bulb");
  if (bulbs) hall.add(createLampGlow(bulbs, hall));

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
 * View-dependent response per material, layered on the baked diffuse:
 * gilt reflects a warm hall gradient tinted by its leaf, varnished boards
 * get a Fresnel sheen, velvet and damask a soft rim glow. No lights or
 * environment maps are sampled, so it stays a few ALU ops per pixel.
 */
const HALL_SHADING = [
  // [name pattern, { metal: tinted reflection, gloss: clear-coat sheen, sheen: fabric rim, diffuse }]
  [/gold/i, { diffuse: 0.55, metal: 0.95, gloss: 0, sheen: 0 }],
  [/stage_wood/i, { diffuse: 1, metal: 0, gloss: 0.22, sheen: 0 }],
  [/dark_wood|seat_wood/i, { diffuse: 1, metal: 0, gloss: 0.08, sheen: 0 }],
  [/velvet|fabric/i, { diffuse: 0.95, metal: 0, gloss: 0, sheen: 0.4 }],
];

/**
 * Every hall surface becomes unlit MeshBasicMaterial: albedo x baked light.
 * @param {THREE.Material} mat
 * @param {number} anisotropy
 */
function hallMaterial(mat, anisotropy) {
  if (!mat?.isMeshStandardMaterial) return mat;
  const name = mat.name || "";
  const lamp = /bulb|exit/i.test(name);
  const gain = lamp ? LAMP_GAIN : HALL_EXPOSURE * (/gold/i.test(name) ? GILT_GAIN : 1);
  if (mat.map) mat.map.anisotropy = anisotropy;
  const basic = new THREE.MeshBasicMaterial({
    name,
    color: mat.color.clone().multiplyScalar(gain),
    map: lamp ? null : mat.map,
    vertexColors: !lamp,
    // Seats are closed, outward-facing solids: culling their back faces
    // halves the raster work on thousands of them (log depth disables
    // early-z, so every hidden fragment is shaded). The rest of the room is
    // wound arbitrarily and stays double-sided.
    side: /seat/i.test(name) ? THREE.FrontSide : THREE.DoubleSide,
  });
  const shading = HALL_SHADING.find(([re]) => re.test(name))?.[1];
  if (shading) addHallShading(basic, shading);
  return basic;
}

/**
 * @param {THREE.MeshBasicMaterial} mat
 * @param {{ diffuse: number, metal: number, gloss: number, sheen: number }} k
 */
function addHallShading(mat, k) {
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.hallK = { value: new THREE.Vector4(k.diffuse, k.metal, k.gloss, k.sheen) };
    shader.vertexShader = shader.vertexShader
      .replace(
        "#include <common>",
        "#include <common>\nvarying vec3 vHallPos;\nvarying vec3 vHallNormal;",
      )
      .replace(
        "#include <project_vertex>",
        `#include <project_vertex>
        vHallPos = (modelMatrix * vec4(transformed, 1.0)).xyz;
        vHallNormal = normalize(mat3(modelMatrix) * normal);`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        "#include <common>",
        `#include <common>
        uniform vec4 hallK;
        varying vec3 vHallPos;
        varying vec3 vHallNormal;
        // The room as seen in a reflection: dark red stalls below, warm
        // lamp-lit plaster above, and the stage wash overhead upstage.
        vec3 hallEnv(vec3 r) {
          vec3 env = mix(vec3(0.10, 0.035, 0.03), vec3(0.95, 0.82, 0.62), smoothstep(-0.35, 0.65, r.y));
          return env + vec3(1.6, 1.45, 1.25) * pow(max(dot(r, normalize(vec3(-0.35, 1.0, 0.0))), 0.0), 24.0);
        }`,
      )
      .replace(
        "#include <opaque_fragment>",
        `{
          vec3 n = normalize(vHallNormal) * (gl_FrontFacing ? 1.0 : -1.0);
          vec3 v = normalize(cameraPosition - vHallPos);
          float ndv = clamp(dot(n, v), 0.0, 1.0);
          vec3 env = hallEnv(reflect(-v, n));
          // Baked light (typical surfaces ~0.5) also occludes the reflection.
          float occ = clamp(dot(vColor.rgb, vec3(0.33)) * 2.0, 0.0, 1.5);
          float fres = pow(1.0 - ndv, 5.0);
          outgoingLight = diffuseColor.rgb * (hallK.x + hallK.y * env * (0.75 + 0.5 * fres))
            + hallK.z * (0.04 + 0.96 * fres) * env * occ
            + hallK.w * diffuseColor.rgb * pow(1.0 - ndv, 2.5) * 1.6;
        }
        #include <opaque_fragment>`,
      );
  };
  mat.customProgramCacheKey = () => `hall-${k.diffuse}-${k.metal}-${k.gloss}-${k.sheen}`;
}

/**
 * A soft additive halo on every lamp, so the bulbs glow like lit globes
 * instead of reading as specks. One Points draw for all of them.
 * @param {THREE.Mesh} bulbs  every lamp of the hall, merged
 * @param {THREE.Object3D} hall  parent the halo is built in
 */
function createLampGlow(bulbs, hall) {
  // Vertices may be quantized: work in the hall's frame (metres).
  const toHall = hall.matrixWorld.clone().invert().multiply(bulbs.matrixWorld);
  // Lamps are separate little solids: cluster their vertices to find centres
  // (each vertex joins the first lamp within LAMP_CLUSTER, searching the
  // neighbouring grid cells so a lamp straddling a cell edge stays whole).
  const pos = bulbs.geometry.attributes.position;
  const cell = LAMP_CLUSTER;
  const grid = new Map();
  const lamps = [];
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(toHall);
    const cx = Math.floor(v.x / cell);
    const cy = Math.floor(v.y / cell);
    const cz = Math.floor(v.z / cell);
    let lamp = null;
    for (let dx = -1; dx <= 1 && !lamp; dx++) {
      for (let dy = -1; dy <= 1 && !lamp; dy++) {
        for (let dz = -1; dz <= 1 && !lamp; dz++) {
          lamp = grid.get(`${cx + dx},${cy + dy},${cz + dz}`)?.find((l) => l.first.distanceTo(v) < cell);
        }
      }
    }
    if (!lamp) {
      lamp = { first: v.clone(), sum: new THREE.Vector3(), n: 0 };
      lamps.push(lamp);
      const key = `${cx},${cy},${cz}`;
      (grid.get(key) ?? grid.set(key, []).get(key)).push(lamp);
    }
    lamp.sum.add(v);
    lamp.n++;
  }
  const centres = lamps.flatMap(({ sum, n }) => sum.divideScalar(n).toArray());
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(centres, 3));

  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,240,215,1)");
  g.addColorStop(0.12, "rgba(255,214,160,0.55)");
  g.addColorStop(0.4, "rgba(255,180,110,0.12)");
  g.addColorStop(1, "rgba(255,170,100,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const glow = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      map: new THREE.CanvasTexture(canvas),
      color: 0xffffff,
      size: LAMP_GLOW_SIZE,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.8,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  glow.name = "Hall_Lamp_Glow";
  glow.matrixAutoUpdate = false;
  glow.renderOrder = 2;
  return glow;
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
