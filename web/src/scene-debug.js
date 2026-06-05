import {
  compactSlider,
  debugGroup,
  debugToggle,
  fmt,
  vec3Group,
} from "./debug-ui.js";

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

/**
 * @param {{
 *   camera: import("three").PerspectiveCamera,
 *   controls: import("three/examples/jsm/controls/OrbitControls.js").OrbitControls,
 *   renderer: import("three").WebGLRenderer,
 *   onManualCameraChange?: () => void,
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
  const {
    camera,
    controls,
    renderer,
    onManualCameraChange,
    mount,
    getCameraDefaults,
  } = opts;

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
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log";
  toolbar.append(btnResetCam, btnLog);
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

  function applyToScene() {
    applying = true;
    const s = readCamera();
    camera.position.set(s.px, s.py, s.pz);
    controls.target.set(s.tx, s.ty, s.tz);
    camera.fov = s.fov;
    camera.updateProjectionMatrix();
    renderer.toneMappingExposure = s.exposure;
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
    ];
    for (const [id, val] of pairs) {
      const row = sliders[id];
      if (!row) continue;
      row.input.value = String(val);
      row.out.textContent = fmt(val);
    }
  }

  const isCameraControl = (id) =>
    id.startsWith("cam-") || id.startsWith("tgt-");

  for (const row of Object.values(sliders)) {
    row.input.addEventListener("input", () => {
      row.out.textContent = fmt(row.input.value);
      applyToScene();
      if (isCameraControl(row.input.id)) onManualCameraChange?.();
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
    onManualCameraChange?.();
  }

  btnResetCam.addEventListener("click", resetCamera);

  btnLog.addEventListener("click", () => {
    const c = readCamera();
    console.info("[scene-debug] paste into scene-utils.js", {
      HERO_CAMERA_DEFAULTS: {
        position: [c.px, c.py, c.pz],
        target: [c.tx, c.ty, c.tz],
        fov: c.fov,
        exposure: c.exposure,
      },
    });
  });

  mount.appendChild(panel);

  return {
    panel,
    syncSlidersFromScene,
    resetCamera,
    applyCameraDefaults: resetCamera,
  };
}