/**
 * Debug panel: sliders for camera position, orbit target, FOV, and exposure.
 */

function sliderRow(label, id, min, max, step, value) {
  const wrap = document.createElement("label");
  wrap.className = "field slider cam-slider";
  const span = document.createElement("span");
  const out = document.createElement("output");
  out.id = `${id}-out`;
  out.textContent = Number(value).toFixed(2);
  span.append(label, " ", out);
  const input = document.createElement("input");
  input.type = "range";
  input.id = id;
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(value);
  wrap.append(span, input);
  return { wrap, input, out };
}

/**
 * @param {{
 *   camera: import("three").PerspectiveCamera,
 *   controls: import("three/examples/jsm/controls/OrbitControls.js").OrbitControls,
 *   renderer: import("three").WebGLRenderer,
 *   mount: HTMLElement,
 *   getDefaults: () => {
 *     position: import("three").Vector3,
 *     target: import("three").Vector3,
 *     fov: number,
 *     exposure: number,
 *   },
 * }} opts
 */
export function createCameraDebugPanel(opts) {
  const { camera, controls, renderer, mount, getDefaults } = opts;

  const panel = document.createElement("details");
  panel.className = "camera-debug";
  panel.open = true;

  const summary = document.createElement("summary");
  summary.textContent = "Camera debug";
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "camera-debug-body";
  panel.appendChild(body);

  const defs = [
    ["Cam X", "cam-x", -4, 4, 0.01],
    ["Cam Y", "cam-y", 0.2, 3, 0.01],
    ["Cam Z", "cam-z", 0.2, 5, 0.01],
    ["Target X", "tgt-x", -2, 2, 0.01],
    ["Target Y", "tgt-y", 0.2, 2.5, 0.01],
    ["Target Z", "tgt-z", -2, 2, 0.01],
    ["FOV", "cam-fov", 20, 75, 0.5],
    ["Exposure", "cam-exposure", 0.5, 3.5, 0.02],
  ];

  const sliders = {};
  for (const [label, id, min, max, step] of defs) {
    let initial = 0;
    if (id === "cam-x") initial = camera.position.x;
    else if (id === "cam-y") initial = camera.position.y;
    else if (id === "cam-z") initial = camera.position.z;
    else if (id === "tgt-x") initial = controls.target.x;
    else if (id === "tgt-y") initial = controls.target.y;
    else if (id === "tgt-z") initial = controls.target.z;
    else if (id === "cam-fov") initial = camera.fov;
    else if (id === "cam-exposure") initial = renderer.toneMappingExposure;

    const row = sliderRow(label, id, min, max, step, initial);
    sliders[id] = row;
    body.appendChild(row.wrap);
  }

  const actions = document.createElement("div");
  actions.className = "camera-debug-actions";
  const btnReset = document.createElement("button");
  btnReset.type = "button";
  btnReset.textContent = "Reset seated";
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log to console";
  actions.append(btnReset, btnLog);
  body.appendChild(actions);

  let applying = false;

  function readSliders() {
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
    const s = readSliders();
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
      row.input.value = String(val);
      row.out.textContent = Number(val).toFixed(2);
    }
  }

  for (const row of Object.values(sliders)) {
    row.input.addEventListener("input", () => {
      row.out.textContent = Number(row.input.value).toFixed(2);
      applyToScene();
    });
  }

  controls.addEventListener("change", syncSlidersFromScene);
  controls.addEventListener("end", syncSlidersFromScene);

  btnReset.addEventListener("click", () => {
    const d = getDefaults();
    camera.position.copy(d.position);
    controls.target.copy(d.target);
    camera.fov = d.fov;
    camera.updateProjectionMatrix();
    renderer.toneMappingExposure = d.exposure;
    controls.update();
    syncSlidersFromScene();
  });

  btnLog.addEventListener("click", () => {
    const s = readSliders();
    console.info("[camera]", {
      position: [s.px, s.py, s.pz],
      target: [s.tx, s.ty, s.tz],
      fov: s.fov,
      exposure: s.exposure,
    });
  });

  mount.appendChild(panel);

  return { panel, syncSlidersFromScene, applyDefaults: () => btnReset.click() };
}