import * as THREE from "three";
import { LIGHTING_DEFAULTS } from "./scene-utils.js";

/** Single-line slider: short label · value · track */
function compactSlider(label, id, min, max, step, value) {
  const wrap = document.createElement("label");
  wrap.className = "debug-row";
  const lbl = document.createElement("span");
  lbl.className = "debug-row-label";
  lbl.textContent = label;
  const out = document.createElement("output");
  out.id = `${id}-out`;
  out.textContent = fmt(value);
  const input = document.createElement("input");
  input.type = "range";
  input.id = id;
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  wrap.append(lbl, out, input);
  return { wrap, input, out };
}

function fmt(v) {
  const n = Number(v);
  return Math.abs(n) >= 10 ? n.toFixed(1) : n.toFixed(2);
}

/** Full-viewport 3×3 grid (pointer-events none). */
function createRuleOfThirdsOverlay(container) {
  const overlay = document.createElement("div");
  overlay.className = "rule-thirds";
  overlay.setAttribute("aria-hidden", "true");
  for (const axis of ["v1", "v2", "h1", "h2"]) {
    const line = document.createElement("span");
    line.className = `rule-thirds-line rule-thirds-line--${axis}`;
    overlay.append(line);
  }
  container.appendChild(overlay);
  return {
    setVisible(on) {
      overlay.classList.toggle("is-on", on);
      overlay.setAttribute("aria-hidden", on ? "false" : "true");
    },
  };
}

function debugToggle(label, id, checked = false) {
  const wrap = document.createElement("label");
  wrap.className = "debug-toggle";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = id;
  input.checked = checked;
  const span = document.createElement("span");
  span.textContent = label;
  wrap.append(input, span);
  return { wrap, input };
}

function debugGroup(title, open = false) {
  const details = document.createElement("details");
  details.className = "debug-group";
  if (open) details.open = true;
  const summary = document.createElement("summary");
  summary.textContent = title;
  const body = document.createElement("div");
  body.className = "debug-group-body";
  details.append(summary, body);
  return { details, body };
}

/** X / Y / Z sliders under one group label */
function vec3Group(groupLabel, ids, mins, maxes, step, vec) {
  const wrap = document.createElement("div");
  wrap.className = "debug-vec3";
  const g = document.createElement("span");
  g.className = "debug-vec3-label";
  g.textContent = groupLabel;
  const axes = document.createElement("div");
  axes.className = "debug-vec3-axes";
  const rows = {};
  const axesLbl = ["X", "Y", "Z"];
  for (let i = 0; i < 3; i++) {
    const row = compactSlider(axesLbl[i], ids[i], mins[i], maxes[i], step, vec[i]);
    rows[ids[i]] = row;
    axes.appendChild(row.wrap);
  }
  wrap.append(g, axes);
  return { wrap, rows };
}

function mountSliders(body, specs, sliders) {
  for (const [label, id, min, max, step, initial] of specs) {
    const row = compactSlider(label, id, min, max, step, initial);
    sliders[id] = row;
    body.appendChild(row.wrap);
  }
}

/**
 * @param {{
 *   camera: import("three").PerspectiveCamera,
 *   controls: import("three/examples/jsm/controls/OrbitControls.js").OrbitControls,
 *   renderer: import("three").WebGLRenderer,
 *   lights: {
 *     ambient: import("three").AmbientLight,
 *     hemi: import("three").HemisphereLight,
 *     ceiling: import("three").DirectionalLight,
 *     room: import("three").DirectionalLight,
 *     viewerLight: import("three").PointLight,
 *     keySpot: import("three").SpotLight,
 *     keySpotTarget: import("three").Object3D,
 *   },
 *   lightingConfig: {
 *     viewerFollowCamera: boolean,
 *     viewerOffset: import("three").Vector3,
 *     keySpotFollowCamera: boolean,
 *     keySpotCamX: number,
 *     keySpotCamY: number,
 *     keySpotCamZMul: number,
 *     keySpotCamZAdd: number,
 *   },
 *   lightHelpers: { setVisible: (visible: boolean) => void, update: () => void },
 *   mount: HTMLElement,
 *   getCameraDefaults: () => {
 *     position: import("three").Vector3,
 *     target: import("three").Vector3,
 *     fov: number,
 *     exposure: number,
 *   },
 * }} opts
 */
export function createSceneDebugPanel(opts) {
  const { camera, controls, renderer, lights, lightingConfig, lightHelpers, mount, getCameraDefaults } =
    opts;

  const panel = document.createElement("details");
  panel.className = "scene-debug";

  const summary = document.createElement("summary");
  summary.textContent = "Debug";
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "scene-debug-body";
  panel.appendChild(body);

  const toolbar = document.createElement("div");
  toolbar.className = "debug-toolbar";
  const btnResetCam = document.createElement("button");
  btnResetCam.type = "button";
  btnResetCam.textContent = "↺ Hero";
  const btnResetLights = document.createElement("button");
  btnResetLights.type = "button";
  btnResetLights.textContent = "↺ Lit";
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log";
  toolbar.append(btnResetCam, btnResetLights, btnLog);
  body.appendChild(toolbar);

  const sliders = {};
  const ruleOfThirds = createRuleOfThirdsOverlay(mount);

  const camGroup = debugGroup("Camera", true);
  body.appendChild(camGroup.details);

  const thirdsToggle = debugToggle("Rule of thirds", "debug-thirds", false);
  thirdsToggle.input.addEventListener("change", () => {
    ruleOfThirds.setVisible(thirdsToggle.input.checked);
  });
  camGroup.body.appendChild(thirdsToggle.wrap);

  const pos = vec3Group(
    "Pos",
    ["cam-x", "cam-y", "cam-z"],
    [-4, 0.2, 0.2],
    [4, 3, 5],
    0.01,
    [camera.position.x, camera.position.y, camera.position.z],
  );
  camGroup.body.appendChild(pos.wrap);
  Object.assign(sliders, pos.rows);

  const tgt = vec3Group(
    "Tgt",
    ["tgt-x", "tgt-y", "tgt-z"],
    [-2, 0.2, -2],
    [2, 2.5, 2],
    0.01,
    [controls.target.x, controls.target.y, controls.target.z],
  );
  camGroup.body.appendChild(tgt.wrap);
  Object.assign(sliders, tgt.rows);

  for (const [label, id, min, max, step, initial] of [
    ["FOV", "cam-fov", 20, 75, 0.5, camera.fov],
    ["Exp", "cam-exposure", 0.5, 3.5, 0.02, renderer.toneMappingExposure],
  ]) {
    const row = compactSlider(label, id, min, max, step, initial);
    sliders[id] = row;
    camGroup.body.appendChild(row.wrap);
  }

  const litGroup = debugGroup("Lighting", true);
  body.appendChild(litGroup.details);

  const lightWireframes = debugToggle("Light wireframes", "debug-light-wireframes", false);
  lightWireframes.input.addEventListener("change", () => {
    lightHelpers.setVisible(lightWireframes.input.checked);
    if (lightWireframes.input.checked) lightHelpers.update();
  });
  litGroup.body.appendChild(lightWireframes.wrap);

  const ambGroup = debugGroup("Ambient");
  litGroup.body.appendChild(ambGroup.details);
  mountSliders(
    ambGroup.body,
    [["Int", "lit-ambient", 0, 2, 0.02, lights.ambient.intensity]],
    sliders,
  );

  const hemiGroup = debugGroup("Hemisphere");
  litGroup.body.appendChild(hemiGroup.details);
  mountSliders(
    hemiGroup.body,
    [["Int", "lit-hemi", 0, 3, 0.02, lights.hemi.intensity]],
    sliders,
  );
  const hemiPos = vec3Group(
    "Pos",
    ["lit-hemi-x", "lit-hemi-y", "lit-hemi-z"],
    [-8, 0, -8],
    [8, 12, 8],
    0.05,
    [lights.hemi.position.x, lights.hemi.position.y, lights.hemi.position.z],
  );
  hemiGroup.body.appendChild(hemiPos.wrap);
  Object.assign(sliders, hemiPos.rows);

  const ceilGroup = debugGroup("Ceiling");
  litGroup.body.appendChild(ceilGroup.details);
  mountSliders(
    ceilGroup.body,
    [["Int", "lit-ceiling", 0, 3, 0.02, lights.ceiling.intensity]],
    sliders,
  );
  const ceilPos = vec3Group(
    "Pos",
    ["lit-ceiling-x", "lit-ceiling-y", "lit-ceiling-z"],
    [-8, 0, -8],
    [8, 12, 8],
    0.05,
    [
      lights.ceiling.position.x,
      lights.ceiling.position.y,
      lights.ceiling.position.z,
    ],
  );
  ceilGroup.body.appendChild(ceilPos.wrap);
  Object.assign(sliders, ceilPos.rows);

  const roomGroup = debugGroup("Room");
  litGroup.body.appendChild(roomGroup.details);
  mountSliders(
    roomGroup.body,
    [["Int", "lit-room", 0, 2, 0.02, lights.room.intensity]],
    sliders,
  );
  const roomPos = vec3Group(
    "Pos",
    ["lit-room-x", "lit-room-y", "lit-room-z"],
    [-8, 0, -8],
    [8, 12, 8],
    0.05,
    [lights.room.position.x, lights.room.position.y, lights.room.position.z],
  );
  roomGroup.body.appendChild(roomPos.wrap);
  Object.assign(sliders, roomPos.rows);

  const viewerGroup = debugGroup("Viewer (point)");
  litGroup.body.appendChild(viewerGroup.details);
  mountSliders(
    viewerGroup.body,
    [
      ["Int", "lit-viewer", 0, 15, 0.1, lights.viewerLight.intensity],
      ["Dist", "lit-viewer-dist", 0, 30, 0.5, lights.viewerLight.distance],
      ["Decay", "lit-viewer-decay", 0, 3, 0.05, lights.viewerLight.decay],
    ],
    sliders,
  );
  const viewerFollow = debugToggle(
    "Follow camera",
    "lit-viewer-follow",
    lightingConfig.viewerFollowCamera,
  );
  viewerGroup.body.appendChild(viewerFollow.wrap);
  const viewerOffset = vec3Group(
    "Offset",
    ["lit-viewer-ox", "lit-viewer-oy", "lit-viewer-oz"],
    [-2, -2, -2],
    [2, 2, 2],
    0.01,
    [
      lightingConfig.viewerOffset.x,
      lightingConfig.viewerOffset.y,
      lightingConfig.viewerOffset.z,
    ],
  );
  viewerOffset.wrap.dataset.litFollowSection = "viewer-offset";
  viewerGroup.body.appendChild(viewerOffset.wrap);
  Object.assign(sliders, viewerOffset.rows);
  const viewerPos = vec3Group(
    "Pos",
    ["lit-viewer-x", "lit-viewer-y", "lit-viewer-z"],
    [-4, 0, -4],
    [4, 4, 4],
    0.01,
    [
      lights.viewerLight.position.x,
      lights.viewerLight.position.y,
      lights.viewerLight.position.z,
    ],
  );
  viewerPos.wrap.dataset.litFollowSection = "viewer-pos";
  viewerGroup.body.appendChild(viewerPos.wrap);
  Object.assign(sliders, viewerPos.rows);

  const keyGroup = debugGroup("Key spot");
  litGroup.body.appendChild(keyGroup.details);
  mountSliders(
    keyGroup.body,
    [
      ["Int", "lit-key", 0, 8, 0.05, lights.keySpot.intensity],
      ["Dist", "lit-key-dist", 0, 30, 0.5, lights.keySpot.distance],
      ["Angle°", "lit-key-angle", 5, 90, 1, THREE.MathUtils.radToDeg(lights.keySpot.angle)],
      ["Pen", "lit-key-pen", 0, 1, 0.01, lights.keySpot.penumbra],
      ["Decay", "lit-key-decay", 0, 3, 0.05, lights.keySpot.decay],
    ],
    sliders,
  );
  const keyFollow = debugToggle(
    "Follow camera",
    "lit-key-follow",
    lightingConfig.keySpotFollowCamera,
  );
  keyGroup.body.appendChild(keyFollow.wrap);
  const keyCamWrap = document.createElement("div");
  keyCamWrap.dataset.litFollowSection = "key-cam";
  mountSliders(
    keyCamWrap,
    [
      ["Cam X×", "lit-key-cam-x", -1, 1, 0.01, lightingConfig.keySpotCamX],
      ["Cam Y+", "lit-key-cam-y", -2, 4, 0.05, lightingConfig.keySpotCamY],
      ["Cam Z×", "lit-key-cam-zmul", -1, 1, 0.01, lightingConfig.keySpotCamZMul],
      ["Cam Z+", "lit-key-cam-zadd", -2, 4, 0.05, lightingConfig.keySpotCamZAdd],
    ],
    sliders,
  );
  keyGroup.body.appendChild(keyCamWrap);

  const keyPos = vec3Group(
    "Pos",
    ["lit-key-x", "lit-key-y", "lit-key-z"],
    [-4, 0, -4],
    [4, 6, 4],
    0.01,
    [lights.keySpot.position.x, lights.keySpot.position.y, lights.keySpot.position.z],
  );
  keyPos.wrap.dataset.litFollowSection = "key-pos";
  keyGroup.body.appendChild(keyPos.wrap);
  Object.assign(sliders, keyPos.rows);

  const keyTgt = vec3Group(
    "Tgt",
    ["lit-key-tx", "lit-key-ty", "lit-key-tz"],
    [-2, 0, -2],
    [2, 2.5, 2],
    0.01,
    [
      lights.keySpotTarget.position.x,
      lights.keySpotTarget.position.y,
      lights.keySpotTarget.position.z,
    ],
  );
  keyTgt.wrap.dataset.litFollowSection = "key-pos";
  keyGroup.body.appendChild(keyTgt.wrap);
  Object.assign(sliders, keyTgt.rows);

  function updateLightFollowSections() {
    const viewerOn = viewerFollow.input.checked;
    viewerOffset.wrap.hidden = !viewerOn;
    viewerPos.wrap.hidden = viewerOn;
    const keyOn = keyFollow.input.checked;
    keyCamWrap.hidden = !keyOn;
    keyPos.wrap.hidden = keyOn;
    keyTgt.wrap.hidden = keyOn;
  }
  viewerFollow.input.addEventListener("change", () => {
    lightingConfig.viewerFollowCamera = viewerFollow.input.checked;
    updateLightFollowSections();
    applyToScene();
  });
  keyFollow.input.addEventListener("change", () => {
    lightingConfig.keySpotFollowCamera = keyFollow.input.checked;
    updateLightFollowSections();
    applyToScene();
  });
  updateLightFollowSections();

  let applying = false;

  function readCamera() {
    return {
      px: Number(sliders["cam-x"].input.value),
      py: Number(sliders["cam-y"].input.value),
      pz: Number(sliders["cam-z"].input.value),
      tx: Number(sliders["tgt-x"].input.value),
      ty: Number(sliders["tgt-y"].input.value),
      tz: Number(sliders["tgt-z"].input.value),
      fov: Number(sliders["cam-fov"].input.value),
      exposure: Number(sliders["cam-exposure"].input.value),
    };
  }

  function applyLighting() {
    lights.ambient.intensity = Number(sliders["lit-ambient"].input.value);

    lights.hemi.intensity = Number(sliders["lit-hemi"].input.value);
    lights.hemi.position.set(
      Number(sliders["lit-hemi-x"].input.value),
      Number(sliders["lit-hemi-y"].input.value),
      Number(sliders["lit-hemi-z"].input.value),
    );

    lights.ceiling.intensity = Number(sliders["lit-ceiling"].input.value);
    lights.ceiling.position.set(
      Number(sliders["lit-ceiling-x"].input.value),
      Number(sliders["lit-ceiling-y"].input.value),
      Number(sliders["lit-ceiling-z"].input.value),
    );

    lights.room.intensity = Number(sliders["lit-room"].input.value);
    lights.room.position.set(
      Number(sliders["lit-room-x"].input.value),
      Number(sliders["lit-room-y"].input.value),
      Number(sliders["lit-room-z"].input.value),
    );

    lights.viewerLight.intensity = Number(sliders["lit-viewer"].input.value);
    lights.viewerLight.distance = Number(sliders["lit-viewer-dist"].input.value);
    lights.viewerLight.decay = Number(sliders["lit-viewer-decay"].input.value);
    lightingConfig.viewerFollowCamera = viewerFollow.input.checked;
    lightingConfig.viewerOffset.set(
      Number(sliders["lit-viewer-ox"].input.value),
      Number(sliders["lit-viewer-oy"].input.value),
      Number(sliders["lit-viewer-oz"].input.value),
    );
    if (!lightingConfig.viewerFollowCamera) {
      lights.viewerLight.position.set(
        Number(sliders["lit-viewer-x"].input.value),
        Number(sliders["lit-viewer-y"].input.value),
        Number(sliders["lit-viewer-z"].input.value),
      );
    }

    lights.keySpot.intensity = Number(sliders["lit-key"].input.value);
    lights.keySpot.distance = Number(sliders["lit-key-dist"].input.value);
    lights.keySpot.angle = THREE.MathUtils.degToRad(
      Number(sliders["lit-key-angle"].input.value),
    );
    lights.keySpot.penumbra = Number(sliders["lit-key-pen"].input.value);
    lights.keySpot.decay = Number(sliders["lit-key-decay"].input.value);
    lightingConfig.keySpotFollowCamera = keyFollow.input.checked;
    lightingConfig.keySpotCamX = Number(sliders["lit-key-cam-x"].input.value);
    lightingConfig.keySpotCamY = Number(sliders["lit-key-cam-y"].input.value);
    lightingConfig.keySpotCamZMul = Number(sliders["lit-key-cam-zmul"].input.value);
    lightingConfig.keySpotCamZAdd = Number(sliders["lit-key-cam-zadd"].input.value);
    if (!lightingConfig.keySpotFollowCamera) {
      lights.keySpot.position.set(
        Number(sliders["lit-key-x"].input.value),
        Number(sliders["lit-key-y"].input.value),
        Number(sliders["lit-key-z"].input.value),
      );
      lights.keySpotTarget.position.set(
        Number(sliders["lit-key-tx"].input.value),
        Number(sliders["lit-key-ty"].input.value),
        Number(sliders["lit-key-tz"].input.value),
      );
    }
  }

  function readLighting() {
    return {
      ambientIntensity: lights.ambient.intensity,
      hemiIntensity: lights.hemi.intensity,
      hemiPosition: lights.hemi.position.toArray(),
      ceilingIntensity: lights.ceiling.intensity,
      ceilingPosition: lights.ceiling.position.toArray(),
      roomIntensity: lights.room.intensity,
      roomPosition: lights.room.position.toArray(),
      viewerIntensity: lights.viewerLight.intensity,
      viewerDistance: lights.viewerLight.distance,
      viewerDecay: lights.viewerLight.decay,
      viewerFollowCamera: lightingConfig.viewerFollowCamera,
      viewerOffset: lightingConfig.viewerOffset.toArray(),
      viewerPosition: lights.viewerLight.position.toArray(),
      keySpotIntensity: lights.keySpot.intensity,
      keySpotDistance: lights.keySpot.distance,
      keySpotAngleDeg: THREE.MathUtils.radToDeg(lights.keySpot.angle),
      keySpotPenumbra: lights.keySpot.penumbra,
      keySpotDecay: lights.keySpot.decay,
      keySpotFollowCamera: lightingConfig.keySpotFollowCamera,
      keySpotPosition: lights.keySpot.position.toArray(),
      keySpotTarget: lights.keySpotTarget.position.toArray(),
      keySpotCamX: lightingConfig.keySpotCamX,
      keySpotCamY: lightingConfig.keySpotCamY,
      keySpotCamZMul: lightingConfig.keySpotCamZMul,
      keySpotCamZAdd: lightingConfig.keySpotCamZAdd,
    };
  }

  function applyToScene() {
    applying = true;
    const s = readCamera();
    camera.position.set(s.px, s.py, s.pz);
    controls.target.set(s.tx, s.ty, s.tz);
    camera.fov = s.fov;
    camera.updateProjectionMatrix();
    renderer.toneMappingExposure = s.exposure;
    applyLighting();
    controls.update();
    applying = false;
  }

  function syncSlidersFromScene() {
    if (applying) return;
    const pairs = [
      ["cam-x", camera.position.x],
      ["cam-y", camera.position.y],
      ["cam-z", camera.position.z],
      ["tgt-x", controls.target.x],
      ["tgt-y", controls.target.y],
      ["tgt-z", controls.target.z],
      ["cam-fov", camera.fov],
      ["cam-exposure", renderer.toneMappingExposure],
      ["lit-ambient", lights.ambient.intensity],
      ["lit-hemi", lights.hemi.intensity],
      ["lit-hemi-x", lights.hemi.position.x],
      ["lit-hemi-y", lights.hemi.position.y],
      ["lit-hemi-z", lights.hemi.position.z],
      ["lit-ceiling", lights.ceiling.intensity],
      ["lit-ceiling-x", lights.ceiling.position.x],
      ["lit-ceiling-y", lights.ceiling.position.y],
      ["lit-ceiling-z", lights.ceiling.position.z],
      ["lit-room", lights.room.intensity],
      ["lit-room-x", lights.room.position.x],
      ["lit-room-y", lights.room.position.y],
      ["lit-room-z", lights.room.position.z],
      ["lit-viewer", lights.viewerLight.intensity],
      ["lit-viewer-dist", lights.viewerLight.distance],
      ["lit-viewer-decay", lights.viewerLight.decay],
      ["lit-viewer-ox", lightingConfig.viewerOffset.x],
      ["lit-viewer-oy", lightingConfig.viewerOffset.y],
      ["lit-viewer-oz", lightingConfig.viewerOffset.z],
      ["lit-viewer-x", lights.viewerLight.position.x],
      ["lit-viewer-y", lights.viewerLight.position.y],
      ["lit-viewer-z", lights.viewerLight.position.z],
      ["lit-key", lights.keySpot.intensity],
      ["lit-key-dist", lights.keySpot.distance],
      ["lit-key-angle", THREE.MathUtils.radToDeg(lights.keySpot.angle)],
      ["lit-key-pen", lights.keySpot.penumbra],
      ["lit-key-decay", lights.keySpot.decay],
      ["lit-key-cam-x", lightingConfig.keySpotCamX],
      ["lit-key-cam-y", lightingConfig.keySpotCamY],
      ["lit-key-cam-zmul", lightingConfig.keySpotCamZMul],
      ["lit-key-cam-zadd", lightingConfig.keySpotCamZAdd],
      ["lit-key-x", lights.keySpot.position.x],
      ["lit-key-y", lights.keySpot.position.y],
      ["lit-key-z", lights.keySpot.position.z],
      ["lit-key-tx", lights.keySpotTarget.position.x],
      ["lit-key-ty", lights.keySpotTarget.position.y],
      ["lit-key-tz", lights.keySpotTarget.position.z],
    ];
    viewerFollow.input.checked = lightingConfig.viewerFollowCamera;
    keyFollow.input.checked = lightingConfig.keySpotFollowCamera;
    updateLightFollowSections();
    for (const [id, val] of pairs) {
      const row = sliders[id];
      if (!row) continue;
      row.input.value = String(val);
      row.out.textContent = fmt(val);
    }
  }

  for (const row of Object.values(sliders)) {
    row.input.addEventListener("input", () => {
      row.out.textContent = fmt(row.input.value);
      applyToScene();
    });
  }

  controls.addEventListener("change", syncSlidersFromScene);
  controls.addEventListener("end", syncSlidersFromScene);

  function resetCamera() {
    const d = getCameraDefaults();
    camera.position.copy(d.position);
    controls.target.copy(d.target);
    camera.fov = d.fov;
    camera.updateProjectionMatrix();
    renderer.toneMappingExposure = d.exposure;
    controls.update();
    syncSlidersFromScene();
  }

  function resetLights() {
    const d = LIGHTING_DEFAULTS;
    lights.ambient.intensity = d.ambientIntensity;
    lights.hemi.intensity = d.hemiIntensity;
    lights.hemi.position.set(...d.hemiPosition);
    lights.ceiling.intensity = d.ceilingIntensity;
    lights.ceiling.position.set(...d.ceilingPosition);
    lights.room.intensity = d.roomIntensity;
    lights.room.position.set(...d.roomPosition);
    lights.viewerLight.intensity = d.viewerIntensity;
    lights.viewerLight.distance = d.viewerDistance;
    lights.viewerLight.decay = d.viewerDecay;
    lights.viewerLight.position.set(...d.viewerPosition);
    lightingConfig.viewerFollowCamera = d.viewerFollowCamera;
    lightingConfig.viewerOffset.set(...d.viewerOffset);
    lights.keySpot.intensity = d.keySpotIntensity;
    lights.keySpot.distance = d.keySpotDistance;
    lights.keySpot.angle = THREE.MathUtils.degToRad(d.keySpotAngleDeg);
    lights.keySpot.penumbra = d.keySpotPenumbra;
    lights.keySpot.decay = d.keySpotDecay;
    lights.keySpot.position.set(...d.keySpotPosition);
    lights.keySpotTarget.position.set(...d.keySpotTarget);
    lightingConfig.keySpotFollowCamera = d.keySpotFollowCamera;
    lightingConfig.keySpotCamX = d.keySpotCamX;
    lightingConfig.keySpotCamY = d.keySpotCamY;
    lightingConfig.keySpotCamZMul = d.keySpotCamZMul;
    lightingConfig.keySpotCamZAdd = d.keySpotCamZAdd;
    syncSlidersFromScene();
  }

  btnResetCam.addEventListener("click", resetCamera);
  btnResetLights.addEventListener("click", resetLights);

  btnLog.addEventListener("click", () => {
    const c = readCamera();
    console.info("[scene-debug] paste into scene-utils.js", {
      HERO_CAMERA_DEFAULTS: {
        position: [c.px, c.py, c.pz],
        target: [c.tx, c.ty, c.tz],
        fov: c.fov,
        exposure: c.exposure,
      },
      LIGHTING_DEFAULTS: readLighting(),
    });
  });

  mount.appendChild(panel);

  return {
    panel,
    syncSlidersFromScene,
    resetCamera,
    resetLights,
    applyCameraDefaults: resetCamera,
  };
}