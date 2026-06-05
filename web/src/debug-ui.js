/** Shared DOM helpers for dev debug panels. */

export function fmt(v) {
  const n = Number(v);
  return Math.abs(n) >= 10 ? n.toFixed(1) : n.toFixed(2);
}

export function compactSlider(label, id, min, max, step, value) {
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

export function debugToggle(label, id, checked = false) {
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

export function debugGroup(title, open = false) {
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

export function vec3Group(groupLabel, ids, mins, maxes, step, vec) {
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

export function mountSliders(body, specs, sliders) {
  for (const [label, id, min, max, step, initial] of specs) {
    const row = compactSlider(label, id, min, max, step, initial);
    sliders[id] = row;
    body.appendChild(row.wrap);
  }
}