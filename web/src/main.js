import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PianoController } from "./piano.js";
import { LiveSession } from "./live.js";
import { backendAvailable, findDefaultPort, listInputPorts } from "./midi.js";
import {
  createStudioGround,
  fitCameraToModel,
  frameModel,
  refineMaterials,
  setupEnvironment,
  setupShadows,
  setupStudioLights,
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
  pressAngle: document.getElementById("press-angle"),
  snappiness: document.getElementById("snappiness"),
  velocitySens: document.getElementById("velocity-sens"),
  pressAngleVal: document.getElementById("press-angle-val"),
  snappinessVal: document.getElementById("snappiness-val"),
  velocitySensVal: document.getElementById("velocity-sens-val"),
};
const viewport = document.getElementById("viewport");

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(
  38,
  window.innerWidth / window.innerHeight,
  0.05,
  50,
);
camera.position.set(1.2, 1.0, 2.0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.42;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

setupEnvironment(renderer, scene);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0.82, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 1.0;
controls.maxDistance = 12;
controls.maxPolarAngle = Math.PI * 0.49;

setupStudioLights(scene);
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

function setStatus(msg) {
  ui.status.textContent = msg;
}

function readSettingsFromUi() {
  return {
    pressAngleDeg: Number(ui.pressAngle.value),
    snappiness: Number(ui.snappiness.value),
    velocitySensitivity: Number(ui.velocitySens.value),
  };
}

function syncSettingLabels() {
  ui.pressAngleVal.textContent = `${Number(ui.pressAngle.value).toFixed(1)}°`;
  ui.snappinessVal.textContent = Number(ui.snappiness.value).toFixed(1);
  ui.velocitySensVal.textContent = Number(ui.velocitySens.value).toFixed(1);
}

function bindSettings() {
  const onChange = () => {
    syncSettingLabels();
    piano?.applySettings(readSettingsFromUi());
  };
  ui.pressAngle.addEventListener("input", onChange);
  ui.snappiness.addEventListener("input", onChange);
  ui.velocitySens.addEventListener("input", onChange);
  onChange();
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
  const benchesRemoved = stripBench(model);
  if (benchesRemoved) console.info(`[viewer] removed ${benchesRemoved} bench object(s)`);
  const benchLegsRemoved = stripBenchLegs(model);
  if (benchLegsRemoved) {
    console.info(`[viewer] removed ${benchLegsRemoved} bench leg object(s)`);
  }
  scene.add(model);
  frameModel(model);
  refineMaterials(model);
  setupShadows(model);
  fitCameraToModel(camera, controls, model);

  if (manifest.defaults) {
    ui.pressAngle.value = String(manifest.defaults.press_angle_deg ?? 3.5);
    ui.snappiness.value = String(manifest.defaults.snappiness ?? 1);
    ui.velocitySens.value = String(manifest.defaults.velocity_sensitivity ?? 1);
  }

  piano = new PianoController(model, manifest);
  bindSettings();
  piano.applySettings(readSettingsFromUi());

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
    getSettings: readSettingsFromUi,
  });

  setStatus(`Ready — ${ready} keys · click keys or press Start for MIDI`);
  await setupMidi();

  ui.btnStart.addEventListener("click", onStart);
  ui.btnStop.addEventListener("click", onStop);

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && live?.isRunning) onStop();
  });
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
  controls.update();
  renderer.render(scene, camera);
}

init().catch((err) => {
  console.error(err);
  setStatus(
    "Could not load model. Export first: Blender --background assets/steinway_grand_playable.blend --python scripts/export_glb.py",
  );
});

animate();