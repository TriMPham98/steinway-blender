import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PianoController } from "./piano.js";
import { LiveSession } from "./live.js";
import { PianoAudio } from "./audio.js";
import { MIDI_HIGH, MIDI_LOW } from "./anim.js";
import { backendAvailable, findDefaultPort, listInputPorts } from "./midi.js";
import { createSceneDebugPanel } from "./scene-debug.js";
import {
  CAMERA_PRESETS,
  createContactShadow,
  createStudioGround,
  fitCameraToModel,
  frameModel,
  getHeroCameraPose,
  refineMaterials,
  HERO_CAMERA_DEFAULTS,
  setupEnvironment,
  setupShadows,
  createLightHelpers,
  setupSeatedViewerLights,
  stripBench,
  stripEmbeddedGround,
  stripBenchLegs,
} from "./scene-utils.js";

const MODEL_URL = "/models/steinway.glb";
const MANIFEST_URL = "/models/steinway.keys.json";

const ui = {
  status: document.getElementById("status"),
  port: document.getElementById("midi-port"),
  btnStart: document.getElementById("btn-start"),
  btnStop: document.getElementById("btn-stop"),
  viewHero: document.getElementById("view-hero"),
  viewFront: document.getElementById("view-front"),
  viewTop: document.getElementById("view-top"),
  viewSeated: document.getElementById("view-seated"),
  menuToggle: document.getElementById("menu-toggle"),
  drawer: document.getElementById("drawer"),
  drawerClose: document.getElementById("drawer-close"),
};
const viewport = document.getElementById("viewport");

const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(
  38,
  window.innerWidth / window.innerHeight,
  0.05,
  50,
);
camera.position.set(...HERO_CAMERA_DEFAULTS.position);

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
controls.target.set(...HERO_CAMERA_DEFAULTS.target);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.minDistance = 1.0;
controls.maxDistance = 12;
controls.maxPolarAngle = Math.PI * 0.49;

const { lights, lightingConfig, syncViewerLight } = setupSeatedViewerLights(scene);
const lightHelpers = createLightHelpers(scene, lights);
const studioFloor = createStudioGround(scene);

let modelRoot = null;
let heroCameraDefaults = null;
/** @type {ReturnType<typeof createSceneDebugPanel> | null} */
let sceneDebug = null;

const loader = new GLTFLoader();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let piano = null;
let live = null;
/** @type {MIDIAccess | null} */
let midiAccess = null;
/** After intro; auto-start live MIDI when an input is available. */
let allowMidiAutoConnect = false;
let prevMidiPortCount = 0;
const pointerNotes = new Set();
// Sampled-grand sound engine for the no-MIDI play path (silent during live
// MIDI, where the hardware piano makes its own sound).
const audio = new PianoAudio();
let spaceSustainHeld = false;
let kbOctaveShift = 0;
/** event.code -> MIDI note currently sounding for that physical key. */
const kbHeldNotes = new Map();
let clock = new THREE.Clock();

// Computer-keyboard "musical typing" layout: physical keys (event.code) so it
// works on any layout. Home row = white keys from C4, upper row = the sharps;
// Z/X shift the octave. Lets visitors without a MIDI piano actually play.
const KEYBOARD_NOTE_OFFSETS = {
  KeyA: 0, KeyW: 1, KeyS: 2, KeyE: 3, KeyD: 4, KeyF: 5, KeyT: 6,
  KeyG: 7, KeyY: 8, KeyH: 9, KeyU: 10, KeyJ: 11, KeyK: 12,
  KeyO: 13, KeyL: 14, KeyP: 15, Semicolon: 16,
};
const KEYBOARD_BASE_NOTE = 60; // C4

function computerKeyToNote(code) {
  const offset = KEYBOARD_NOTE_OFFSETS[code];
  if (offset == null) return null;
  const note = KEYBOARD_BASE_NOTE + offset + kbOctaveShift * 12;
  return note >= MIDI_LOW && note <= MIDI_HIGH ? note : null;
}

/** Warm up the sampled grand for click/keyboard play when no MIDI is driving sound. */
function preloadAudioIfLocal() {
  if (PianoAudio.supported() && !live?.isRunning) audio.init();
}

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

/** 1–4 → preset id (matches drawer view button order). */
const VIEW_PRESET_BY_KEY = {
  1: "hero",
  2: "front",
  3: "top",
  4: "seated",
};

const viewPresetButtons = {
  hero: ui.viewHero,
  front: ui.viewFront,
  top: ui.viewTop,
  seated: ui.viewSeated,
};

let activeViewPreset = null;

function setActiveViewPreset(id) {
  activeViewPreset = id;
  for (const [presetId, btn] of Object.entries(viewPresetButtons)) {
    const on = presetId === id;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }
}

function clearActiveViewPreset() {
  if (!activeViewPreset) return;
  activeViewPreset = null;
  for (const btn of Object.values(viewPresetButtons)) {
    btn.classList.remove("is-active");
    btn.setAttribute("aria-pressed", "false");
  }
}

function isEditableFocusTarget(el) {
  if (!el || !(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "SELECT" ||
    tag === "TEXTAREA" ||
    el.isContentEditable
  );
}

function goToViewPreset(id, duration = 1.0) {
  setActiveViewPreset(id);
  animateCameraTo(CAMERA_PRESETS[id], duration);
}

function bindViewPresetClearOnUserInput() {
  controls.addEventListener("start", () => {
    if (!cameraTween.active) clearActiveViewPreset();
  });
  renderer.domElement.addEventListener(
    "wheel",
    () => {
      if (!cameraTween.active) clearActiveViewPreset();
    },
    { passive: true },
  );
}

/** Smoothly fly the camera to a pose ({position,target,fov} arrays or vec3s). */
function animateCameraTo(pose, duration = 1) {
  cameraTween.fromPos.copy(camera.position);
  cameraTween.fromTarget.copy(controls.target);
  cameraTween.fromFov = camera.fov;
  cameraTween.toPos.set(...pose.position);
  cameraTween.toTarget.set(...pose.target);
  cameraTween.toFov = pose.fov;
  if (pose.exposure != null) {
    renderer.toneMappingExposure = pose.exposure;
  }
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
    sceneDebug?.syncSlidersFromScene();
  }
}

let statusTimer = 0;
/** Transient toast — shows briefly then fades. Empty message hides it. */
function setStatus(msg) {
  clearTimeout(statusTimer);
  ui.status.textContent = msg ?? "";
  if (!msg) {
    ui.status.classList.remove("show");
    return;
  }
  ui.status.classList.add("show");
  statusTimer = setTimeout(() => ui.status.classList.remove("show"), 3500);
}

function openDrawer() {
  ui.drawer.classList.add("open");
  ui.drawer.setAttribute("aria-hidden", "false");
  ui.menuToggle.setAttribute("aria-expanded", "true");
  ui.menuToggle.classList.add("hidden");
}

function closeDrawer() {
  ui.drawer.classList.remove("open");
  ui.drawer.setAttribute("aria-hidden", "true");
  ui.menuToggle.setAttribute("aria-expanded", "false");
  ui.menuToggle.classList.remove("hidden");
}

function toggleDrawer() {
  if (ui.drawer.classList.contains("open")) closeDrawer();
  else openDrawer();
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

function maybeAutoConnectMidi() {
  if (!allowMidiAutoConnect || !midiAccess || !piano) return;
  const names = listInputPorts(midiAccess);
  if (!names.length) {
    if (live?.isRunning) onStop();
    return;
  }
  if (live?.isRunning) return;
  if (!ui.port.value) return;
  onStart();
}

function refreshMidiPorts() {
  if (!midiAccess) return;
  const names = listInputPorts(midiAccess);
  const count = names.length;
  const hotPlug = prevMidiPortCount === 0 && count > 0;
  prevMidiPortCount = count;
  fillPortList(names, ui.port.value);
  ui.btnStart.disabled = count === 0 || (live?.isRunning ?? false);
  if (!count) {
    if (live?.isRunning) onStop();
    else preloadAudioIfLocal();
    return;
  }
  if (live?.isRunning && live.portName && !names.includes(live.portName)) {
    onStop();
    return;
  }
  if (hotPlug) maybeAutoConnectMidi();
}

async function setupMidi() {
  if (!backendAvailable()) {
    setStatus("Web MIDI not supported in this browser");
    ui.btnStart.disabled = true;
    return;
  }
  try {
    midiAccess = await navigator.requestMIDIAccess({ sysex: false });
    refreshMidiPorts();
    midiAccess.onstatechange = refreshMidiPorts;
  } catch {
    setStatus("Web MIDI permission denied");
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
    // The hardware piano makes the sound now — silence any local web-audio play.
    releaseAllLocalNotes();
    audio.allOff();
    setTransportRunning(true);
    goToViewPreset("seated");
  } catch (err) {
    setStatus(String(err.message ?? err));
  }
}

function onStop() {
  const wasRunning = live?.isRunning;
  live?.stop();
  setTransportRunning(false);
  if (wasRunning) goToViewPreset("hero");
  preloadAudioIfLocal();
}

// --- Local (no-MIDI) play: drive the visual keys and the sampled-grand sound
// together. Callers gate on `!live.isRunning`, so audio never doubles the
// hardware piano during a live MIDI session. ---
function localNoteOn(note, velocity) {
  piano?.noteOn(note, velocity);
  audio.resume();
  audio.noteOn(note, velocity);
}

function localNoteOff(note) {
  piano?.noteOff(note);
  audio.noteOff(note);
}

function setLocalSustain(on) {
  piano?.setSustain(on);
  audio.setSustain(on);
}

/** Release every locally-held note + pedal (e.g. when a live MIDI session starts). */
function releaseAllLocalNotes() {
  for (const note of pointerNotes) localNoteOff(note);
  pointerNotes.clear();
  for (const note of kbHeldNotes.values()) localNoteOff(note);
  kbHeldNotes.clear();
  if (spaceSustainHeld) {
    spaceSustainHeld = false;
    setLocalSustain(false);
  }
}

function pointerDown(event) {
  if (!piano || live?.isRunning) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const note = piano.pick(raycaster);
  if (note == null) return;
  localNoteOn(note, 100);
  pointerNotes.add(note);
}

function pointerUp() {
  if (!pointerNotes.size) return;
  for (const note of pointerNotes) localNoteOff(note);
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
  modelRoot = model;
  stripEmbeddedGround(model);
  stripBench(model);
  stripBenchLegs(model);
  scene.add(model);
  frameModel(model);
  refineMaterials(model);
  setupShadows(model);
  createContactShadow(scene, model);
  const pose = fitCameraToModel(camera, controls, model);
  renderer.toneMappingExposure = pose.exposure;
  syncViewerLight(pose.viewerLightPosition);

  heroCameraDefaults = {
    position: pose.position.clone(),
    target: pose.target.clone(),
    fov: pose.fov,
    exposure: pose.exposure,
  };

  sceneDebug = createSceneDebugPanel({
    camera,
    controls,
    renderer,
    lights,
    lightingConfig,
    lightHelpers,
    onManualCameraChange: clearActiveViewPreset,
    mount: viewport,
    getCameraDefaults: () => {
      if (modelRoot) {
        const p = getHeroCameraPose(modelRoot);
        return {
          position: p.position,
          target: p.target,
          fov: p.fov,
          exposure: p.exposure,
        };
      }
      if (heroCameraDefaults) return heroCameraDefaults;
      return {
        position: new THREE.Vector3(...HERO_CAMERA_DEFAULTS.position),
        target: new THREE.Vector3(...HERO_CAMERA_DEFAULTS.target),
        fov: HERO_CAMERA_DEFAULTS.fov,
        exposure: HERO_CAMERA_DEFAULTS.exposure,
      };
    },
  });

  const defaults = manifest.defaults ?? {};
  feelSettings = {
    pressAngleDeg: defaults.press_angle_deg ?? 3.5,
    snappiness: defaults.snappiness ?? 1,
    velocitySensitivity: defaults.velocity_sensitivity ?? 1,
  };

  piano = new PianoController(model, manifest);
  piano.applySettings(feelSettings);

  const ready = piano.keyCount;

  live = new LiveSession(piano, {
    onStatus: setStatus,
    onRunningChange: setTransportRunning,
    getSettings: () => feelSettings,
  });

  if (ready >= 88) {
    setStatus(`Ready · ${ready} keys`);
  } else {
    setStatus(`Keys missing (${ready}/88) — re-export model`);
  }

  // Once the sampled grand is loaded, nudge no-MIDI visitors to play.
  audio.onLoaded = () => {
    if (!live?.isRunning) setStatus("No MIDI — play with your mouse or keyboard");
  };

  await setupMidi();

  ui.btnStart.addEventListener("click", onStart);
  ui.btnStop.addEventListener("click", onStop);
  ui.viewHero.addEventListener("click", () => goToViewPreset("hero"));
  ui.viewFront.addEventListener("click", () => goToViewPreset("front"));
  ui.viewTop.addEventListener("click", () => goToViewPreset("top"));
  ui.viewSeated.addEventListener("click", () => goToViewPreset("seated"));

  ui.menuToggle.addEventListener("click", toggleDrawer);
  ui.drawerClose.addEventListener("click", closeDrawer);

  window.addEventListener("keydown", (e) => {
    if (isEditableFocusTarget(document.activeElement)) return;

    const presetId = VIEW_PRESET_BY_KEY[e.key];
    if (presetId) {
      e.preventDefault();
      goToViewPreset(presetId);
      return;
    }

    if (e.key === "Escape") {
      if (ui.drawer.classList.contains("open")) closeDrawer();
      else if (live?.isRunning) onStop();
      return;
    }

    // Computer-keyboard piano — only when the hardware piano isn't driving the
    // sound, and never hijacking browser/OS shortcuts.
    if (live?.isRunning || e.metaKey || e.ctrlKey || e.altKey) return;

    if (e.code === "Space") {
      e.preventDefault();
      if (!spaceSustainHeld) {
        spaceSustainHeld = true;
        audio.resume();
        setLocalSustain(true);
      }
      return;
    }

    if (e.code === "KeyZ" || e.code === "KeyX") {
      if (!e.repeat) {
        kbOctaveShift = Math.max(
          -3,
          Math.min(3, kbOctaveShift + (e.code === "KeyZ" ? -1 : 1)),
        );
        setStatus(
          kbOctaveShift === 0
            ? "Octave: middle"
            : `Octave ${kbOctaveShift > 0 ? "+" : ""}${kbOctaveShift}`,
        );
      }
      return;
    }

    const note = computerKeyToNote(e.code);
    if (note == null) return;
    e.preventDefault();
    if (e.repeat || kbHeldNotes.has(e.code)) return;
    kbHeldNotes.set(e.code, note);
    localNoteOn(note, 96);
  });

  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") {
      if (spaceSustainHeld) {
        spaceSustainHeld = false;
        setLocalSustain(false);
      }
      return;
    }
    // Release by physical key (not note) so an octave shift mid-hold still lifts
    // the note that was actually struck.
    const note = kbHeldNotes.get(e.code);
    if (note == null) return;
    kbHeldNotes.delete(e.code);
    localNoteOff(note);
  });

  // Cinematic intro: reveal from a wide pose, then settle into the hero view.
  const start = new THREE.Vector3(...CAMERA_PRESETS.hero.position)
    .multiplyScalar(1.8)
    .setY(CAMERA_PRESETS.hero.position[1] + 1.2);
  camera.position.copy(start);
  goToViewPreset("hero", 2.2);
  setTimeout(() => {
    allowMidiAutoConnect = true;
    maybeAutoConnectMidi();
    preloadAudioIfLocal();
  }, 2300);
}

bindViewPresetClearOnUserInput();

renderer.domElement.addEventListener("pointerdown", pointerDown);
window.addEventListener("pointerup", pointerUp);

function onResize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  const dpr = Math.min(window.devicePixelRatio, 2);
  studioFloor.getRenderTarget().setSize(w * dpr, h * dpr);
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
  if (lightHelpers.group.visible) lightHelpers.update();
  renderer.render(scene, camera);
}

init().catch((err) => {
  console.error(err);
  setStatus(
    "Could not load model. Export first: Blender --background assets/steinway_grand_playable.blend --python scripts/export_glb.py",
  );
});

animate();