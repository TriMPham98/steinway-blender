import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PianoController } from "./piano.js";
import { buildCaseRig, createCaseState, pickLidHit, stepCase } from "./case.js";
import { LiveSession } from "./live.js";
import { PianoAudio } from "./audio.js";
import { MIDI_HIGH, MIDI_LOW } from "./anim.js";
import { backendAvailable, findDefaultPort, listInputPorts } from "./midi.js";

import {
  CAMERA_PRESETS,
  KEYBOARD_RANGE_VIEW,
  createContactShadow,
  createStudioGround,
  fitCameraToModel,
  frameModel,
  getHeroCameraPose,
  refineMaterials,
  repairPianoStatic,
  dedupeSoundboardOverlay,
  prepHingeTrim,
  prepInteriorStack,
  HERO_CAMERA_DEFAULTS,
  setupEnvironment,
  setupShadows,
  createLightHelpers,
  setupSeatedViewerLights,
  stripBench,
  stripEmbeddedGround,
  stripBenchLegs,
  stripStrayCurves,
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
  caseControls: document.getElementById("case-controls"),
  lidToggle: document.getElementById("btn-lid-toggle"),
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

// logarithmicDepthBuffer: the near/far span (~0.01–52) gives the plain 24-bit
// depth buffer too little precision near the rim, so the interior gold frame
// z-fights through the thin black case ("brass pieces showing through the
// shell"). Log depth spreads precision evenly and clears it. The studio-floor
// Reflector shader already carries the <logdepthbuf_*> chunks for this path.
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  logarithmicDepthBuffer: true,
});
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
// Low enough that the close keyboard-range framing isn't clamped back out by
// controls.update() (which always re-enforces minDistance on the orbit radius).
controls.minDistance = 0.3;
controls.maxDistance = 12;
controls.maxPolarAngle = Math.PI * 0.49;

const { lights, lightingConfig, syncViewerLight } = setupSeatedViewerLights(scene);
const lightHelpers = createLightHelpers(scene, lights);
const studioFloor = createStudioGround(scene);

let modelRoot = null;
let heroCameraDefaults = null;
/** @type {{ syncSlidersFromScene: () => void } | null} */
let sceneDebug = null;
/** @type {{ syncFromScene: () => void } | null} */
let lightDebug = null;

const loader = new GLTFLoader();
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let piano = null;
let live = null;
/** @type {ReturnType<typeof buildCaseRig> | null} */
let caseRig = null;
/** @type {ReturnType<typeof createCaseState> | null} */
let caseState = null;
/** @type {MIDIAccess | null} */
let midiAccess = null;
/** After intro; auto-start live MIDI when an input is available. */
let allowMidiAutoConnect = false;
let prevMidiPortCount = 0;
const pointerNotes = new Set();
/** Click vs drag threshold (px) — lets OrbitControls keep the full pointer lifecycle. */
const POINTER_DRAG_PX = 5;
let pointerDownXY = null;
let pointerDragged = false;
let pendingLidClick = false;
let pendingPointerNote = null;
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
  Quote: 17, BracketRight: 18, Enter: 19,
};
const KEYBOARD_BASE_NOTE = 60; // C4, before octave shift
const KEYBOARD_SPAN = 19; // semitones from the base key (A) to the top key (Enter)
// Octave shifts move the whole window by a true octave (12 semitones), so a given
// letter key always plays the same pitch class. At the extremes the window runs
// off the 88-key piano and those keys go silent — A0 and C8 stay reachable, just
// not on the A key.
const OCTAVE_SHIFT_MIN = -4; // base C0 → H = A0 (A–G fall below the piano)
const OCTAVE_SHIFT_MAX = 3; //  base C7 → A = C7, K = C8 (keys above C8 go silent)

const NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
function noteName(midi) {
  return NOTE_NAMES[((midi % 12) + 12) % 12] + (Math.floor(midi / 12) - 1);
}

/** Window base note (the A key) for the current octave shift — true octaves. */
function keyboardBaseNote() {
  return KEYBOARD_BASE_NOTE + kbOctaveShift * 12;
}

function computerKeyToNote(code) {
  const offset = KEYBOARD_NOTE_OFFSETS[code];
  if (offset == null) return null;
  const note = keyboardBaseNote() + offset;
  // Keys that run off either end of the piano at the extreme octaves are silent.
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
  viewingKeyboardRange = false;
  setActiveViewPreset(id);
  animateCameraTo(CAMERA_PRESETS[id], duration);
}

// --- Computer-keyboard octave focus (no-MIDI mode) ---
// Whether the camera is currently framing the computer-keyboard octave range,
// and which octave shift that framing was built for (so we re-frame on shift).
let viewingKeyboardRange = false;
let focusedOctaveShift = 0;

// Hand-tuned reference framing (distance / angle / height) for the home octave
// range; the live view pans it to whatever keys are active.
const KB_VIEW_TARGET = new THREE.Vector3(...KEYBOARD_RANGE_VIEW.target);
const KB_VIEW_OFFSET = new THREE.Vector3(
  KEYBOARD_RANGE_VIEW.position[0] - KEYBOARD_RANGE_VIEW.target[0],
  KEYBOARD_RANGE_VIEW.position[1] - KEYBOARD_RANGE_VIEW.target[1],
  KEYBOARD_RANGE_VIEW.position[2] - KEYBOARD_RANGE_VIEW.target[2],
);
const KB_VIEW_DIST = KB_VIEW_OFFSET.length();
const KB_VIEW_DIR = KB_VIEW_OFFSET.clone().normalize();

/** Inclusive MIDI [lo, hi] of the *playable* keys (clamped to the piano). */
function keyboardRangeNotes() {
  const base = keyboardBaseNote();
  return [
    Math.max(base, MIDI_LOW),
    Math.min(base + KEYBOARD_SPAN, MIDI_HIGH),
  ];
}

/** Bounding-box center of the home (C4–E5) range, cached after the model loads. */
let homeRangeCenter = null;
function keyboardHomeCenter() {
  if (homeRangeCenter) return homeRangeCenter;
  const box = piano?.rangeBox(
    KEYBOARD_BASE_NOTE,
    KEYBOARD_BASE_NOTE + KEYBOARD_SPAN,
  );
  if (!box || box.isEmpty()) return null;
  homeRangeCenter = box.getCenter(new THREE.Vector3());
  return homeRangeCenter;
}

/** Camera pose framing the keys the computer keyboard plays, or null. */
function getKeyboardRangePose() {
  if (!piano) return null;
  const [lo, hi] = keyboardRangeNotes();
  const box = piano.rangeBox(lo, hi);
  if (!box || box.isEmpty()) return null;
  const home = keyboardHomeCenter();
  if (!home) return null;

  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());

  // Height/depth/distance/angle from the hand-tuned reference; lateral position
  // centered on the active keys so every octave is balanced in frame.
  const target = new THREE.Vector3(
    center.x,
    KB_VIEW_TARGET.y + (center.y - home.y),
    KB_VIEW_TARGET.z + (center.z - home.z),
  );

  // Hold the reference distance, but pull back if a narrow viewport can't fit
  // the ~17-key span at that distance.
  const vHalf = THREE.MathUtils.degToRad(KEYBOARD_RANGE_VIEW.fov) / 2;
  const hHalf = Math.atan(Math.tan(vHalf) * Math.max(camera.aspect, 0.0001));
  const fitDist = ((Math.max(size.x, 0.12) * 0.5) / Math.tan(hHalf)) * 1.05;
  const dist = Math.max(KB_VIEW_DIST, fitDist);

  const position = target.clone().addScaledVector(KB_VIEW_DIR, dist);
  return {
    position: [position.x, position.y, position.z],
    target: [target.x, target.y, target.z],
    fov: KEYBOARD_RANGE_VIEW.fov,
    exposure: KEYBOARD_RANGE_VIEW.exposure,
  };
}

/** Fly the camera to frame the computer-keyboard octave range. */
function focusKeyboardRange(duration = 0.85) {
  const pose = getKeyboardRangePose();
  if (!pose) return;
  clearActiveViewPreset();
  animateCameraTo(pose, duration);
  viewingKeyboardRange = true;
  focusedOctaveShift = kbOctaveShift;
}

/** Re-frame the keyboard range if we've drifted off it (e.g. after manual nav). */
function ensureKeyboardFocus() {
  if (!viewingKeyboardRange || focusedOctaveShift !== kbOctaveShift) {
    focusKeyboardRange();
  }
}

function cancelCameraTween() {
  if (!cameraTween.active) return;
  cameraTween.active = false;
}

function bindViewPresetClearOnUserInput() {
  const onManualInput = () => {
    cancelCameraTween();
    clearActiveViewPreset();
    viewingKeyboardRange = false;
  };
  controls.addEventListener("start", onManualInput);
  renderer.domElement.addEventListener("wheel", onManualInput, { passive: true });
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
}

function updateCameraTween(dt) {
  if (!cameraTween.active) return;
  // User orbit wins over preset / intro tweens — never fight the pointer.
  if (controls.state !== -1) {
    cancelCameraTween();
    return;
  }
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
    sceneDebug?.syncSlidersFromScene();
    lightDebug?.syncFromScene();
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

function syncLidToggleLabel() {
  if (!caseState || !ui.lidToggle) return;
  const open = caseState.target.lidOpen > 0.5;
  ui.lidToggle.textContent = open ? "Close lid" : "Open lid";
  ui.lidToggle.setAttribute("aria-pressed", open ? "true" : "false");
}

function toggleLid() {
  if (!caseState) return;
  const open = caseState.target.lidOpen > 0.5;
  caseState.target.lidOpen = open ? 0 : 1;
  syncLidToggleLabel();
}

function bindCaseControls() {
  ui.lidToggle?.addEventListener("click", toggleLid);
}

function setRaycasterFromClient(clientX, clientY) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
}

function pickKeyHit() {
  if (!piano || live?.isRunning) return null;
  const meshes = [];
  for (const obj of piano.noteMap.values()) {
    obj.traverse((child) => {
      if (child.isMesh) meshes.push(child);
    });
  }
  const hits = raycaster.intersectObjects(meshes, false);
  if (!hits.length) return null;
  const note = piano.pick(raycaster);
  return note != null ? { note, distance: hits[0].distance } : null;
}

/** Closest interactive target under the pointer (lid beats keys at equal depth). */
function pickPointerTarget(clientX, clientY) {
  setRaycasterFromClient(clientX, clientY);
  const lidHit = pickLidHit(caseRig, raycaster);
  const keyHit = pickKeyHit();
  if (lidHit && (!keyHit || lidHit.distance <= keyHit.distance)) {
    return { type: "lid" };
  }
  if (keyHit) return { type: "key", note: keyHit.note };
  return null;
}

function updateHoverCursor(clientX, clientY) {
  if (pointerDownXY != null) return;
  const target = pickPointerTarget(clientX, clientY);
  renderer.domElement.style.cursor = target?.type === "lid" ? "pointer" : "";
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

function onPointerDownCapture(event) {
  if (event.button !== 0) return;
  // Shift+click is reserved for the z-fight raycaster (dev probe).
  if (event.shiftKey) return;
  cancelCameraTween();
  pointerDownXY = [event.clientX, event.clientY];
  pointerDragged = false;
  pendingLidClick = false;
  pendingPointerNote = null;

  const target = pickPointerTarget(event.clientX, event.clientY);
  if (target?.type === "lid") {
    pendingLidClick = true;
    return;
  }
  if (target?.type === "key") {
    pendingPointerNote = target.note;
    // Play on press; if the user drags to orbit, onPointerMove releases the note.
    localNoteOn(pendingPointerNote, 100);
    pointerNotes.add(pendingPointerNote);
  }
}

function onPointerMove(event) {
  updateHoverCursor(event.clientX, event.clientY);
  if (pointerDownXY == null || pointerDragged) return;
  const dx = event.clientX - pointerDownXY[0];
  const dy = event.clientY - pointerDownXY[1];
  if (dx * dx + dy * dy <= POINTER_DRAG_PX * POINTER_DRAG_PX) return;
  pointerDragged = true;
  pendingPointerNote = null;
  pendingLidClick = false;
  renderer.domElement.style.cursor = "";
  if (pointerNotes.size) {
    for (const note of pointerNotes) localNoteOff(note);
    pointerNotes.clear();
  }
}

function onPointerUp(event) {
  if (!pointerDragged && pendingLidClick) {
    toggleLid();
  }
  if (pointerNotes.size) {
    for (const note of pointerNotes) localNoteOff(note);
    pointerNotes.clear();
  }
  pointerDownXY = null;
  pointerDragged = false;
  pendingPointerNote = null;
  pendingLidClick = false;
  updateHoverCursor(event.clientX, event.clientY);
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
  stripStrayCurves(model);
  scene.add(model);
  frameModel(model);
  const pruned = repairPianoStatic(model);
  if (pruned) console.info(`[steinway] pruned ${pruned} corrupt Piano_Static triangle(s)`);
  const dedup = dedupeSoundboardOverlay(model);
  if (dedup) console.info(`[steinway] dropped ${dedup} doubled soundboard triangle(s)`);
  refineMaterials(model);
  prepHingeTrim(model);
  prepInteriorStack(model);
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

  if (import.meta.env.DEV) {
    window.__cam = camera;
    window.__ctrl = controls;
    window.__model = model;

    const debugStack = document.createElement("div");
    debugStack.className = "debug-stack";
    viewport.appendChild(debugStack);

    const [
      { createSceneDebugPanel },
      { createLightDebugPanel },
      { createAudioDebugPanel },
      { createZfightProbe },
    ] = await Promise.all([
      import("./scene-debug.js"),
      import("./light-debug.js"),
      import("./audio-debug.js"),
      import("./zfight-probe.js"),
    ]);
    createZfightProbe({
      camera,
      renderer,
      scene,
      getModel: () => modelRoot,
      mount: debugStack,
    });
    // Bottom → top in the stack: Tone, Lights, Debug (see .debug-stack flex).
    createAudioDebugPanel({ audio, mount: debugStack });
    lightDebug = createLightDebugPanel({
      lights,
      lightingConfig,
      lightHelpers,
      mount: debugStack,
    });
    sceneDebug = createSceneDebugPanel({
      camera,
      controls,
      renderer,
      onManualCameraChange: clearActiveViewPreset,
      mount: debugStack,
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
  }

  const defaults = manifest.defaults ?? {};
  feelSettings = {
    pressAngleDeg: defaults.press_angle_deg ?? 3.5,
    snappiness: defaults.snappiness ?? 1,
    velocitySensitivity: defaults.velocity_sensitivity ?? 1,
  };

  piano = new PianoController(model, manifest);
  piano.applySettings(feelSettings);

  caseRig = buildCaseRig(model, manifest.case);
  if (caseRig.available) {
    const caseDefaults = manifest.case?.defaults ?? {};
    caseState = createCaseState(caseDefaults);
    caseRig.reset();
    ui.caseControls.hidden = false;
    bindCaseControls();
    syncLidToggleLabel();
  }

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
    // Bare 1–4 switch views; Cmd/Ctrl+number is reserved for the browser tab bar.
    if (presetId && !e.metaKey && !e.ctrlKey) {
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
        const next = THREE.MathUtils.clamp(
          kbOctaveShift + (e.code === "KeyZ" ? -1 : 1),
          OCTAVE_SHIFT_MIN,
          OCTAVE_SHIFT_MAX,
        );
        if (next !== kbOctaveShift) {
          kbOctaveShift = next;
          const [lo, hi] = keyboardRangeNotes();
          setStatus(`Keys ${noteName(lo)}–${noteName(hi)}`);
          if (viewingKeyboardRange) focusKeyboardRange(); // pan only after first keyboard play
        }
      }
      return;
    }

    const note = computerKeyToNote(e.code);
    if (note == null) return;
    e.preventDefault();
    if (e.repeat || kbHeldNotes.has(e.code)) return;
    kbHeldNotes.set(e.code, note);
    localNoteOn(note, 96);
    ensureKeyboardFocus(); // first keyboard note frames the playable octaves
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

renderer.domElement.addEventListener("pointerdown", onPointerDownCapture, {
  capture: true,
});
renderer.domElement.addEventListener("pointermove", onPointerMove);
renderer.domElement.addEventListener("pointerleave", () => {
  renderer.domElement.style.cursor = "";
});
window.addEventListener("pointerup", onPointerUp);
window.addEventListener("pointercancel", onPointerUp);

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
  if (caseRig && caseState) {
    stepCase(caseState, caseRig, dt);
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