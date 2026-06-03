import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PianoController } from "./piano.js";
import { LiveSession } from "./live.js";
import { backendAvailable, findDefaultPort, listInputPorts } from "./midi.js";
import {
  CAMERA_PRESETS,
  createStudioGround,
  fitCameraToModel,
  frameModel,
  refineMaterials,
  setupEnvironment,
  setupShadows,
  setupSeatedViewerLights,
  stripBench,
  stripEmbeddedGround,
  stripBenchLegs,
} from "./scene-utils.js";

const MODEL_URL = "/models/steinway.glb";
const MANIFEST_URL = "/models/steinway.keys.json";

const ui = {
  status: document.getElementById("status"),
  keysReady: document.getElementById("keys-ready"),
  midiBackend: document.getElementById("midi-backend"),
  port: document.getElementById("midi-port"),
  btnStart: document.getElementById("btn-start"),
  btnStop: document.getElementById("btn-stop"),
  viewSeated: document.getElementById("view-seated"),
  viewFront: document.getElementById("view-front"),
  viewTop: document.getElementById("view-top"),
};
const viewport = document.getElementById("viewport");

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(
  38,
  window.innerWidth / window.innerHeight,
  0.05,
  50,
);
camera.position.set(2.53, 1.35, 2.21);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.86;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

setupEnvironment(renderer, scene);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0.14, 0.71, 0.19);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 1.0;
controls.maxDistance = 12;
controls.maxPolarAngle = Math.PI * 0.49;

const { syncViewerLight } = setupSeatedViewerLights(scene);
createStudioGround(scene);

const loader = new GLTFLoader();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let piano = null;
let live = null;
/** @type {MIDIAccess | null} */
let midiAccess = null;
const pointerNotes = new Set();
let clock = new THREE.Clock();

// Motion-feel settings, hardcoded for the final product (from the model manifest).
let feelSettings = { pressAngleDeg: 3.5, snappiness: 1, velocitySensitivity: 1 };

// --- Camera tween (shared by the intro sweep and the preset view buttons) ---
const cameraTween = {
  active: false,
  elapsed: 0,
  duration: 1,
  fromPos: new THREE.Vector3(),
  fromTarget: new THREE.Vector3(),
  fromFov: 44,
  toPos: new THREE.Vector3(),
  toTarget: new THREE.Vector3(),
  toFov: 44,
};

const easeInOutCubic = (t) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

/** Smoothly fly the camera to a pose ({position,target,fov} arrays or vec3s). */
function animateCameraTo(pose, duration = 1) {
  cameraTween.fromPos.copy(camera.position);
  cameraTween.fromTarget.copy(controls.target);
  cameraTween.fromFov = camera.fov;
  cameraTween.toPos.set(...pose.position);
  cameraTween.toTarget.set(...pose.target);
  cameraTween.toFov = pose.fov;
  cameraTween.elapsed = 0;
  cameraTween.duration = Math.max(duration, 0.0001);
  cameraTween.active = true;
  controls.enabled = false;
}

function updateCameraTween(dt) {
  if (!cameraTween.active) return;
  cameraTween.elapsed += dt;
  const t = easeInOutCubic(
    Math.min(cameraTween.elapsed / cameraTween.duration, 1),
  );
  camera.position.lerpVectors(cameraTween.fromPos, cameraTween.toPos, t);
  controls.target.lerpVectors(cameraTween.fromTarget, cameraTween.toTarget, t);
  camera.fov = THREE.MathUtils.lerp(cameraTween.fromFov, cameraTween.toFov, t);
  camera.updateProjectionMatrix();
  if (t >= 1) {
    cameraTween.active = false;
    controls.enabled = true;
  }
}

function setStatus(msg) {
  ui.status.textContent = msg;
}

function setTransportRunning(running) {
  ui.btnStart.disabled = running;
  ui.btnStop.disabled = !running;
  ui.port.disabled = running;
}

async function loadManifest() {
  const res = await fetch(MANIFEST_URL);
  if (!res.ok) throw new Error(`manifest ${res.status}`);
  return res.json();
}

function fillPortList(names, selected) {
  ui.port.innerHTML = "";
  if (!names.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No MIDI inputs found";
    ui.port.appendChild(opt);
    ui.port.disabled = true;
    return;
  }
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    ui.port.appendChild(opt);
  }
  ui.port.disabled = false;
  const pick = selected && names.includes(selected) ? selected : findDefaultPort(names);
  ui.port.value = pick;
}

async function setupMidi() {
  if (!backendAvailable()) {
    ui.midiBackend.textContent = "Web MIDI not supported in this browser";
    ui.midiBackend.classList.add("warn");
    ui.btnStart.disabled = true;
    return;
  }
  try {
    midiAccess = await navigator.requestMIDIAccess({ sysex: false });
    ui.midiBackend.textContent = "Web MIDI ready";
    ui.midiBackend.classList.remove("warn");
    const refresh = () => {
      const names = listInputPorts(midiAccess);
      fillPortList(names, ui.port.value);
      ui.btnStart.disabled = names.length === 0 || (live?.isRunning ?? false);
    };
    refresh();
    midiAccess.onstatechange = refresh;
  } catch {
    ui.midiBackend.textContent = "Web MIDI permission denied";
    ui.midiBackend.classList.add("warn");
    ui.btnStart.disabled = true;
  }
}

function onStart() {
  if (!piano || !midiAccess) return;
  const port = ui.port.value;
  if (!port) {
    setStatus("No MIDI input — connect your piano");
    return;
  }
  try {
    live.start(midiAccess, port);
    setTransportRunning(true);
  } catch (err) {
    setStatus(String(err.message ?? err));
  }
}

function onStop() {
  live?.stop();
  setTransportRunning(false);
}

function pointerDown(event) {
  if (!piano || live?.isRunning) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const note = piano.pick(raycaster);
  if (note == null) return;
  piano.noteOn(note, 100);
  pointerNotes.add(note);
}

function pointerUp() {
  if (live?.isRunning) return;
  for (const note of pointerNotes) piano?.noteOff(note);
  pointerNotes.clear();
}

async function init() {
  setStatus("Loading model…");
  const [gltf, manifest] = await Promise.all([
    new Promise((resolve, reject) => {
      loader.load(MODEL_URL, resolve, (xhr) => {
        if (xhr.total) {
          setStatus(`Loading model… ${Math.round((xhr.loaded / xhr.total) * 100)}%`);
        }
      }, reject);
    }),
    loadManifest(),
  ]);

  const model = gltf.scene;
  stripEmbeddedGround(model);
  stripBench(model);
  stripBenchLegs(model);
  scene.add(model);
  frameModel(model);
  refineMaterials(model);
  setupShadows(model);
  const pose = fitCameraToModel(camera, controls, model);
  renderer.toneMappingExposure = pose.exposure;
  syncViewerLight(pose.viewerLightPosition);

  const defaults = manifest.defaults ?? {};
  feelSettings = {
    pressAngleDeg: defaults.press_angle_deg ?? 3.5,
    snappiness: defaults.snappiness ?? 1,
    velocitySensitivity: defaults.velocity_sensitivity ?? 1,
  };

  piano = new PianoController(model, manifest);
  piano.applySettings(feelSettings);

  const ready = piano.keyCount;
  if (ready >= 88) {
    ui.keysReady.textContent = `Keys ready (${ready})`;
    ui.keysReady.classList.add("ok");
  } else {
    ui.keysReady.textContent = `Keys missing (${ready}/88) — re-export model`;
    ui.keysReady.classList.add("warn");
  }

  live = new LiveSession(piano, {
    onStatus: setStatus,
    onRunningChange: setTransportRunning,
    getSettings: () => feelSettings,
  });

  setStatus(`Ready — ${ready} keys · click keys or press Start for MIDI`);
  await setupMidi();

  ui.btnStart.addEventListener("click", onStart);
  ui.btnStop.addEventListener("click", onStop);
  ui.viewSeated.addEventListener("click", () =>
    animateCameraTo(CAMERA_PRESETS.seated, 1.0),
  );
  ui.viewFront.addEventListener("click", () =>
    animateCameraTo(CAMERA_PRESETS.front, 1.0),
  );
  ui.viewTop.addEventListener("click", () =>
    animateCameraTo(CAMERA_PRESETS.top, 1.0),
  );

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && live?.isRunning) onStop();
  });

  // Cinematic intro: reveal from a wide pose, then settle into the seated view.
  const start = new THREE.Vector3(...CAMERA_PRESETS.seated.position)
    .multiplyScalar(1.8)
    .setY(CAMERA_PRESETS.seated.position[1] + 1.2);
  camera.position.copy(start);
  animateCameraTo(CAMERA_PRESETS.seated, 2.2);
}

renderer.domElement.addEventListener("pointerdown", pointerDown);
window.addEventListener("pointerup", pointerUp);

function onResize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
}
window.addEventListener("resize", onResize);

function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  if (!live?.isRunning) {
    piano?.step(dt);
  }
  updateCameraTween(dt);
  controls.update();
  syncViewerLight(camera.position);
  renderer.render(scene, camera);
}

init().catch((err) => {
  console.error(err);
  setStatus(
    "Could not load model. Export first: Blender --background assets/steinway_grand_playable.blend --python scripts/export_glb.py",
  );
});

animate();