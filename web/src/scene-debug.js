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
 *   },
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
  const { camera, controls, renderer, lights, mount, getCameraDefaults } = opts;

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

  const litGroup = debugGroup("Lighting");
  body.appendChild(litGroup.details);

  for (const [label, id, min, max, step, initial] of [
    ["Amb", "lit-ambient", 0, 2, 0.02, lights.ambient.intensity],
    ["Hem", "lit-hemi", 0, 3, 0.02, lights.hemi.intensity],
    ["Ceil", "lit-ceiling", 0, 3, 0.02, lights.ceiling.intensity],
    ["Room", "lit-room", 0, 2, 0.02, lights.room.intensity],
    ["View", "lit-viewer", 0, 15, 0.1, lights.viewerLight.intensity],
    ["V dist", "lit-viewer-dist", 2, 30, 0.5, lights.viewerLight.distance],
    ["Spot", "lit-key", 0, 8, 0.05, lights.keySpot.intensity],
  ]) {
    const row = compactSlider(label, id, min, max, step, initial);
    sliders[id] = row;
    litGroup.body.appendChild(row.wrap);
  }

  const ceilPos = vec3Group(
    "Ceil",
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
  litGroup.body.appendChild(ceilPos.wrap);
  Object.assign(sliders, ceilPos.rows);

  const roomPos = vec3Group(
    "Room",
    ["lit-room-x", "lit-room-y", "lit-room-z"],
    [-8, 0, -8],
    [8, 12, 8],
    0.05,
    [lights.room.position.x, lights.room.position.y, lights.room.position.z],
  );
  litGroup.body.appendChild(roomPos.wrap);
  Object.assign(sliders, roomPos.rows);

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
    lights.keySpot.intensity = Number(sliders["lit-key"].input.value);
  }

  function readLighting() {
    return {
      ambientIntensity: lights.ambient.intensity,
      hemiIntensity: lights.hemi.intensity,
      ceilingIntensity: lights.ceiling.intensity,
      ceilingPosition: lights.ceiling.position.toArray(),
      roomIntensity: lights.room.intensity,
      roomPosition: lights.room.position.toArray(),
      viewerIntensity: lights.viewerLight.intensity,
      viewerDistance: lights.viewerLight.distance,
      viewerDecay: lights.viewerLight.decay,
      keySpotIntensity: lights.keySpot.intensity,
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
      ["lit-key", lights.keySpot.intensity],
    ];
    for (const [id, val] of pairs) {
      const row = sliders[id];
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
    lights.ceiling.intensity = d.ceilingIntensity;
    lights.ceiling.position.set(...d.ceilingPosition);
    lights.room.intensity = d.roomIntensity;
    lights.room.position.set(...d.roomPosition);
    lights.viewerLight.intensity = d.viewerIntensity;
    lights.viewerLight.distance = d.viewerDistance;
    lights.viewerLight.decay = d.viewerDecay;
    lights.keySpot.intensity = d.keySpotIntensity;
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