/** Debug sliders for the sampled-grand tone chain (dev only). */

import { compactSlider, debugGroup, fmt, mountSliders } from "./debug-ui.js";

/**
 * @param {{ audio: import("./audio.js").PianoAudio, mount: HTMLElement }} opts
 */
export function createAudioDebugPanel({ audio, mount }) {
  const panel = document.createElement("details");
  panel.className = "scene-debug audio-debug";

  const summary = document.createElement("summary");
  summary.textContent = "Tone";
  panel.appendChild(summary);

  const body = document.createElement("div");
  body.className = "scene-debug-body";
  panel.appendChild(body);

  const toolbar = document.createElement("div");
  toolbar.className = "debug-toolbar";
  const btnReset = document.createElement("button");
  btnReset.type = "button";
  btnReset.textContent = "↺ Tone";
  const btnLog = document.createElement("button");
  btnLog.type = "button";
  btnLog.textContent = "Log";
  toolbar.append(btnReset, btnLog);
  body.appendChild(toolbar);

  const sliders = {};
  const t = () => audio.tone;

  const eqGroup = debugGroup("EQ", true);
  body.appendChild(eqGroup.details);
  mountSliders(
    eqGroup.body,
    [
      ["Body Hz", "tone-body-hz", 80, 500, 5, t().bodyHz],
      ["Body dB", "tone-body-db", 0, 8, 0.1, t().bodyDb],
      ["Low Hz", "tone-low-hz", 200, 800, 5, t().lowMidHz],
      ["Low dB", "tone-low-db", 0, 6, 0.1, t().lowMidDb],
      ["Bite Hz", "tone-bite-hz", 1000, 6000, 50, t().biteHz],
      ["Bite dB", "tone-bite-db", -12, 0, 0.5, t().biteDb],
      ["Air Hz", "tone-air-hz", 1500, 8000, 50, t().airHz],
      ["Air dB", "tone-air-db", -18, 0, 0.5, t().airDb],
      ["Top Hz", "tone-top-hz", 2000, 12000, 50, t().topHz],
    ],
    sliders,
  );

  const roomGroup = debugGroup("Room", true);
  body.appendChild(roomGroup.details);
  mountSliders(
    roomGroup.body,
    [
      ["Wet", "tone-rev-wet", 0, 0.5, 0.01, t().reverbWet],
      ["BW", "tone-rev-bw", 0, 1, 0.02, t().reverbBandwidth],
      ["Damp", "tone-rev-damp", 0, 1, 0.02, t().reverbDamping],
      ["Decay", "tone-rev-decay", 0.1, 1.5, 0.02, t().reverbDecay],
    ],
    sliders,
  );

  const outGroup = debugGroup("Output", true);
  body.appendChild(outGroup.details);
  mountSliders(
    outGroup.body,
    [
      ["Master", "tone-out-gain", 0.5, 1.5, 0.02, t().outputGain],
      ["Sample", "tone-sample-vol", 0, 127, 1, audio.sampleVolume],
    ],
    sliders,
  );

  function readTone() {
    return {
      bodyHz: Number(sliders["tone-body-hz"].input.value),
      bodyDb: Number(sliders["tone-body-db"].input.value),
      lowMidHz: Number(sliders["tone-low-hz"].input.value),
      lowMidDb: Number(sliders["tone-low-db"].input.value),
      biteHz: Number(sliders["tone-bite-hz"].input.value),
      biteDb: Number(sliders["tone-bite-db"].input.value),
      airHz: Number(sliders["tone-air-hz"].input.value),
      airDb: Number(sliders["tone-air-db"].input.value),
      topHz: Number(sliders["tone-top-hz"].input.value),
      reverbWet: Number(sliders["tone-rev-wet"].input.value),
      reverbBandwidth: Number(sliders["tone-rev-bw"].input.value),
      reverbDamping: Number(sliders["tone-rev-damp"].input.value),
      reverbDecay: Number(sliders["tone-rev-decay"].input.value),
      outputGain: Number(sliders["tone-out-gain"].input.value),
    };
  }

  function applyFromSliders() {
    Object.assign(audio.tone, readTone());
    audio.sampleVolume = Number(sliders["tone-sample-vol"].input.value);
    audio.applyTone();
  }

  function syncSliders() {
    const tone = audio.tone;
    const pairs = [
      ["tone-body-hz", tone.bodyHz],
      ["tone-body-db", tone.bodyDb],
      ["tone-low-hz", tone.lowMidHz],
      ["tone-low-db", tone.lowMidDb],
      ["tone-bite-hz", tone.biteHz],
      ["tone-bite-db", tone.biteDb],
      ["tone-air-hz", tone.airHz],
      ["tone-air-db", tone.airDb],
      ["tone-top-hz", tone.topHz],
      ["tone-rev-wet", tone.reverbWet],
      ["tone-rev-bw", tone.reverbBandwidth],
      ["tone-rev-damp", tone.reverbDamping],
      ["tone-rev-decay", tone.reverbDecay],
      ["tone-out-gain", tone.outputGain],
      ["tone-sample-vol", audio.sampleVolume],
    ];
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
      applyFromSliders();
    });
  }

  btnReset.addEventListener("click", () => {
    audio.resetTone();
    syncSliders();
  });

  btnLog.addEventListener("click", () => {
    console.info("[audio-debug] paste into audio.js", {
      TONE_DEFAULTS: { ...audio.tone },
      sampleVolume: audio.sampleVolume,
    });
  });

  mount.appendChild(panel);

  return { panel, syncSliders, resetTone: () => btnReset.click() };
}