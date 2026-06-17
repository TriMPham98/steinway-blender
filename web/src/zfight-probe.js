import * as THREE from "three";
import { debugGroup, debugToggle } from "./debug-ui.js";

const COPLANAR_MM = 2;
const MAX_HITS = 12;
const MARKER_POOL = 8;

/**
 * Shift-click raycaster for z-fighting diagnosis. Logs and displays every mesh
 * under the cursor (front → back). Pairs with Δ < 2 mm are likely coplanar.
 *
 * @param {{
 *   camera: THREE.PerspectiveCamera,
 *   renderer: THREE.WebGLRenderer,
 *   scene: THREE.Scene,
 *   getModel: () => THREE.Object3D | null,
 *   mount: HTMLElement,
 * }} opts
 */
export function createZfightProbe(opts) {
  const { camera, renderer, scene, getModel, mount } = opts;

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();

  const panel = document.createElement("details");
  panel.className = "scene-debug zfight-probe";
  panel.open = true;

  const summary = document.createElement("summary");
  summary.textContent = "Z-fight probe";
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "scene-debug-body";
  panel.appendChild(body);

  const hint = document.createElement("p");
  hint.className = "zfight-probe-hint";
  hint.textContent = "Shift+click the canvas to raycast. Coplanar hits (Δ < 2 mm) highlight in amber.";
  body.appendChild(hint);

  const toolbar = document.createElement("div");
  toolbar.className = "debug-toolbar";
  const btnClear = document.createElement("button");
  btnClear.type = "button";
  btnClear.textContent = "Clear";
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log";
  toolbar.append(btnClear, btnLog);
  body.appendChild(toolbar);

  const markersToggle = debugToggle("Show hit markers", "zfight-markers", true);
  body.appendChild(markersToggle.wrap);

  const status = document.createElement("div");
  status.className = "zfight-probe-status";
  status.textContent = "No probe yet";
  body.appendChild(status);

  const tableWrap = document.createElement("div");
  tableWrap.className = "zfight-probe-table-wrap";
  const table = document.createElement("table");
  table.className = "zfight-probe-table";
  table.innerHTML = `<thead><tr>
    <th>#</th><th>obj</th><th>mat</th><th>dist</th><th>Δ</th>
  </tr></thead><tbody></tbody>`;
  tableWrap.appendChild(table);
  body.appendChild(tableWrap);

  const detailGroup = debugGroup("Last hit detail", false);
  body.appendChild(detailGroup.details);
  const detailPre = document.createElement("pre");
  detailPre.className = "zfight-probe-detail";
  detailGroup.body.appendChild(detailPre);

  mount.appendChild(panel);

  const markerRoot = new THREE.Group();
  markerRoot.name = "ZfightProbeMarkers";
  scene.add(markerRoot);

  const markerGeo = new THREE.SphereGeometry(0.004, 10, 10);
  const markerMats = Array.from({ length: MARKER_POOL }, (_, i) => {
    const hue = (i / MARKER_POOL) * 0.55 + 0.05;
    return new THREE.MeshBasicMaterial({
      color: new THREE.Color().setHSL(hue, 0.85, 0.55),
      depthTest: false,
      transparent: true,
      opacity: 0.92,
    });
  });
  const markers = Array.from({ length: MARKER_POOL }, (_, i) => {
    const m = new THREE.Mesh(markerGeo, markerMats[i]);
    m.visible = false;
    m.renderOrder = 9999;
    markerRoot.add(m);
    return m;
  });

  let lastRows = [];

  function hideMarkers() {
    for (const m of markers) m.visible = false;
  }

  function showMarkers(hits) {
    if (!markersToggle.input.checked) {
      hideMarkers();
      return;
    }
    hits.slice(0, MARKER_POOL).forEach((h, i) => {
      markers[i].position.copy(h.point);
      markers[i].visible = true;
    });
    for (let i = hits.length; i < MARKER_POOL; i++) markers[i].visible = false;
  }

  function materialLabel(hit) {
    const m = hit.object.material;
    if (Array.isArray(m)) {
      const idx = hit.face?.materialIndex ?? 0;
      return m[idx]?.name ?? m.map((x) => x?.name).join(",");
    }
    return m?.name ?? "—";
  }

  function probeAtNdc(ndcX, ndcY) {
    const model = getModel();
    if (!model) {
      status.textContent = "Model not loaded";
      return [];
    }

    pointer.set(ndcX, ndcY);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster
      .intersectObject(model, true)
      .filter((h) => h.object.visible && h.face != null)
      .slice(0, MAX_HITS);

    const rows = hits.map((h, i) => {
      const gapMm =
        i > 0 ? (h.distance - hits[i - 1].distance) * 1000 : null;
      const coplanar = gapMm != null && gapMm < COPLANAR_MM;
      return {
        i: i + 1,
        obj: h.object.name || h.object.type,
        mat: materialLabel(h),
        dist: h.distance,
        distFmt: h.distance.toFixed(4),
        gapMm,
        gapFmt: gapMm != null ? `${gapMm.toFixed(2)} mm` : "—",
        coplanar,
        point: h.point.clone(),
        normal: worldNormal(h),
        faceIndex: h.faceIndex,
        materialIndex: h.face?.materialIndex,
        uv: h.uv ? { u: h.uv.x, v: h.uv.y } : null,
      };
    });

    lastRows = rows;
    showMarkers(hits);

    const coplanarCount = rows.filter((r) => r.coplanar).length;
    if (!rows.length) {
      status.textContent = "No hits";
      status.className = "zfight-probe-status";
    } else if (coplanarCount) {
      status.textContent = `${rows.length} hit(s) — ${coplanarCount} coplanar pair(s) (Δ < ${COPLANAR_MM} mm)`;
      status.className = "zfight-probe-status zfight-probe-status--warn";
    } else {
      status.textContent = `${rows.length} hit(s) — no coplanar pairs in stack`;
      status.className = "zfight-probe-status zfight-probe-status--ok";
    }

    const tbody = table.querySelector("tbody");
    tbody.replaceChildren();
    for (const r of rows) {
      const tr = document.createElement("tr");
      if (r.coplanar) tr.className = "zfight-probe-coplanar";
      tr.innerHTML = `<td>${r.i}</td><td title="${r.obj}">${short(r.obj, 14)}</td>
        <td title="${r.mat}">${short(r.mat, 16)}</td>
        <td>${r.distFmt}</td><td>${r.gapFmt}</td>`;
      tr.title = `${r.obj} / ${r.mat}`;
      tbody.appendChild(tr);
    }

    const top = rows[0];
    if (top) {
      const p = top.point;
      const n = top.normal;
      detailPre.textContent = [
        `object: ${top.obj}`,
        `material: ${top.mat}`,
        `distance: ${top.distFmt} m`,
        `face: #${top.faceIndex}  matIdx: ${top.materialIndex ?? "—"}`,
        `point: ${fmt3(p)}`,
        `normal: ${fmt3(n)}`,
        top.uv ? `uv: ${top.uv.u.toFixed(4)}, ${top.uv.v.toFixed(4)}` : null,
      ]
        .filter(Boolean)
        .join("\n");
    } else {
      detailPre.textContent = "";
    }

    console.table(
      rows.map(({ i, obj, mat, distFmt, gapFmt, coplanar, point, normal }) => ({
        i,
        obj,
        mat,
        dist: distFmt,
        gap: gapFmt,
        coplanar,
        x: +point.x.toFixed(4),
        y: +point.y.toFixed(4),
        z: +point.z.toFixed(4),
        nx: +normal.x.toFixed(3),
        ny: +normal.y.toFixed(3),
        nz: +normal.z.toFixed(3),
      })),
    );

    return rows;
  }

  function probeFromClient(clientX, clientY) {
    const rect = renderer.domElement.getBoundingClientRect();
    return probeAtNdc(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1,
    );
  }

  function onShiftClick(event) {
    if (!event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    probeFromClient(event.clientX, event.clientY);
  }

  renderer.domElement.addEventListener("pointerdown", onShiftClick, {
    capture: true,
  });

  btnClear.addEventListener("click", () => {
    lastRows = [];
    hideMarkers();
    table.querySelector("tbody").replaceChildren();
    detailPre.textContent = "";
    status.textContent = "Cleared";
    status.className = "zfight-probe-status";
  });

  btnLog.addEventListener("click", () => {
    if (!lastRows.length) {
      console.info("[zfight-probe] no probe data — shift+click the canvas first");
      return;
    }
    console.info("[zfight-probe] last probe", lastRows);
  });

  markersToggle.input.addEventListener("change", () => {
    if (!markersToggle.input.checked) hideMarkers();
  });

  window.__probe = probeAtNdc;
  window.__probeClient = probeFromClient;

  return {
    probeAtNdc,
    probeFromClient,
    dispose() {
      renderer.domElement.removeEventListener("pointerdown", onShiftClick, {
        capture: true,
      });
      scene.remove(markerRoot);
      markerGeo.dispose();
      for (const mat of markerMats) mat.dispose();
      panel.remove();
      delete window.__probe;
      delete window.__probeClient;
    },
  };
}

const _normalMat = new THREE.Matrix3();

function worldNormal(hit) {
  if (hit.normal) return hit.normal.clone();
  const n = hit.face.normal.clone();
  _normalMat.getNormalMatrix(hit.object.matrixWorld);
  return n.applyMatrix3(_normalMat).normalize();
}

function short(s, n) {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}

function fmt3(v) {
  return `${v.x.toFixed(4)}, ${v.y.toFixed(4)}, ${v.z.toFixed(4)}`;
}