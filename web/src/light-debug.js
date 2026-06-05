import * as THREE from "three";
import { LIGHTING_DEFAULTS } from "./scene-utils.js";
import {
  compactSlider,
  debugGroup,
  debugToggle,
  fmt,
  mountSliders,
  vec3Group,
} from "./debug-ui.js";

/**
 * @param {{
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
 * }} opts
 */
export function createLightDebugPanel(opts) {
  const { lights, lightingConfig, lightHelpers, mount } = opts;

  const panel = document.createElement("details");
  panel.className = "scene-debug light-debug";

  const summary = document.createElement("summary");
  summary.textContent = "Lights";
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "scene-debug-body";
  panel.appendChild(body);

  const toolbar = document.createElement("div");
  toolbar.className = "debug-toolbar";
  const btnReset = document.createElement("button");
  btnReset.type = "button";
  btnReset.textContent = "↺ Lit";
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log";
  toolbar.append(btnReset, btnLog);
  body.appendChild(toolbar);

  const sliders = {};

  const lightWireframes = debugToggle(
    "Light wireframes",
    "debug-light-wireframes",
    false,
  );
  lightWireframes.input.addEventListener("change", () => {
    lightHelpers.setVisible(lightWireframes.input.checked);
    if (lightWireframes.input.checked) lightHelpers.update();
  });
  body.appendChild(lightWireframes.wrap);

  const ambGroup = debugGroup("Ambient", true);
  body.appendChild(ambGroup.details);
  mountSliders(
    ambGroup.body,
    [["Int", "lit-ambient", 0, 2, 0.02, lights.ambient.intensity]],
    sliders,
  );

  const hemiGroup = debugGroup("Hemisphere");
  body.appendChild(hemiGroup.details);
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
  body.appendChild(ceilGroup.details);
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
  body.appendChild(roomGroup.details);
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
  body.appendChild(viewerGroup.details);
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
  body.appendChild(keyGroup.details);
  mountSliders(
    keyGroup.body,
    [
      ["Int", "lit-key", 0, 8, 0.05, lights.keySpot.intensity],
      ["Dist", "lit-key-dist", 0, 30, 0.5, lights.keySpot.distance],
      [
        "Angle°",
        "lit-key-angle",
        5,
        90,
        1,
        THREE.MathUtils.radToDeg(lights.keySpot.angle),
      ],
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
    if (lightHelpers.group.visible) lightHelpers.update();
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

  function syncFromScene() {
    const pairs = [
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

  viewerFollow.input.addEventListener("change", () => {
    lightingConfig.viewerFollowCamera = viewerFollow.input.checked;
    updateLightFollowSections();
    applyLighting();
  });
  keyFollow.input.addEventListener("change", () => {
    lightingConfig.keySpotFollowCamera = keyFollow.input.checked;
    updateLightFollowSections();
    applyLighting();
  });
  updateLightFollowSections();

  for (const row of Object.values(sliders)) {
    row.input.addEventListener("input", () => {
      row.out.textContent = fmt(row.input.value);
      applyLighting();
    });
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
    syncFromScene();
    applyLighting();
  }

  btnReset.addEventListener("click", resetLights);
  btnLog.addEventListener("click", () => {
    console.info("[light-debug] paste into scene-utils.js", {
      LIGHTING_DEFAULTS: readLighting(),
    });
  });

  mount.appendChild(panel);

  return { panel, syncFromScene, resetLights, applyLighting };
}