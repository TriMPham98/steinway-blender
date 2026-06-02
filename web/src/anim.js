/**
 * Port of extension/steinway_midi_piano/anim.py — velocity spring-damper + sustain pedal.
 */

export const SETTLE = 1e-3;
export const PEDAL_ANGLE = (5 * Math.PI) / 180;
export const SUBSTEP = 0.005;
export const MAX_DT = 0.05;
export const RELEASE_DAMP = 0.8;
export const MIDI_LOW = 21;
export const MIDI_HIGH = 108;

/** @typedef {{ stiffness: number, pressDamping: number, releaseStiffness: number, velocityGain: number, gamma: number, pedalRate: number }} Feel */

export const DEFAULT_FEEL = {
  stiffness: 240,
  pressDamping: 6,
  releaseStiffness: 2500,
  velocityGain: 30,
  gamma: 0.6,
  pedalRate: 12,
};

/**
 * @param {{ snappiness?: number, velocitySensitivity?: number }} settings
 * @returns {Feel}
 */
export function feelFromSettings(settings) {
  const snap = Math.max(settings.snappiness ?? 1, 0.05);
  const sens = settings.velocitySensitivity ?? 1;
  return {
    stiffness: DEFAULT_FEEL.stiffness * snap,
    pressDamping: DEFAULT_FEEL.pressDamping,
    releaseStiffness: DEFAULT_FEEL.releaseStiffness * snap,
    velocityGain: DEFAULT_FEEL.velocityGain * sens,
    gamma: DEFAULT_FEEL.gamma,
    pedalRate: DEFAULT_FEEL.pedalRate,
  };
}

/**
 * @param {Map<number, object>} noteMap
 * @param {object | null} pedalObj
 * @param {Feel} feel
 */
export function createLiveState(noteMap, pedalObj, feel) {
  return {
    noteMap,
    feel,
    pos: new Map(),
    vel: new Map(),
    target: new Map(),
    active: new Set(),
    pedalObj,
    pedalTarget: 0,
    pedalCurrent: 0,
    pedalActive: false,
  };
}

/** @param {Feel} feel @param {number} velocity 0..127 */
function strikeSpeed(feel, velocity) {
  const v = Math.min(Math.max(velocity, 0), 127) / 127;
  return v ** feel.gamma * feel.velocityGain;
}

/** @param {ReturnType<createLiveState>} state @param {number} note @param {number} velocity */
export function setNote(state, note, velocity) {
  if (note < MIDI_LOW || note > MIDI_HIGH) return;
  if (!state.noteMap.has(note)) return;
  if (velocity > 0) {
    state.target.set(note, 1);
    const kick = strikeSpeed(state.feel, velocity);
    state.vel.set(note, Math.max(state.vel.get(note) ?? 0, kick));
  } else {
    state.target.set(note, 0);
  }
  state.active.add(note);
}

/** @param {ReturnType<createLiveState>} state @param {boolean} on */
export function setSustain(state, on) {
  state.pedalTarget = on ? 1 : 0;
  state.pedalActive = true;
}

/**
 * @param {ReturnType<createLiveState>} state
 * @param {number} pressAngle radians
 * @param {number} dt seconds
 * @param {(note: number, depth: number) => void} applyKey
 * @param {(depth: number) => void} [applyPedal]
 * @returns {boolean} still animating
 */
export function easeStep(state, pressAngle, dt, applyKey, applyPedal) {
  const feel = state.feel;
  let stepDt = Math.min(Math.max(dt, 0), MAX_DT);
  if (stepDt <= 0) {
    return state.active.size > 0 || state.pedalActive;
  }
  const n = Math.max(1, Math.ceil(stepDt / SUBSTEP));
  const h = stepDt / n;
  const pressK = feel.stiffness;
  const pressC = feel.pressDamping;
  const releaseK = feel.releaseStiffness;
  const releaseC = 2 * Math.sqrt(releaseK) * RELEASE_DAMP;

  for (const note of [...state.active]) {
    if (!state.noteMap.has(note)) {
      state.active.delete(note);
      continue;
    }
    let pos = state.pos.get(note) ?? 0;
    let vel = state.vel.get(note) ?? 0;
    const tgt = state.target.get(note) ?? 0;
    const k = tgt > 0.5 ? pressK : releaseK;
    const c = tgt > 0.5 ? pressC : releaseC;
    for (let i = 0; i < n; i++) {
      vel += (k * (tgt - pos) - c * vel) * h;
      pos += vel * h;
      if (pos >= 1) {
        pos = 1;
        vel = Math.min(vel, 0);
      } else if (pos <= 0) {
        pos = 0;
        vel = Math.max(vel, 0);
      }
    }
    if (Math.abs(tgt - pos) <= SETTLE && Math.abs(vel) <= SETTLE) {
      pos = tgt;
      vel = 0;
      state.active.delete(note);
    }
    state.pos.set(note, pos);
    state.vel.set(note, vel);
    applyKey(note, pos * pressAngle);
  }

  if (state.pedalActive && state.pedalObj && applyPedal) {
    const rate = Math.min(Math.max(feel.pedalRate * stepDt, 0), 1);
    let cur = state.pedalCurrent + (state.pedalTarget - state.pedalCurrent) * rate;
    if (Math.abs(state.pedalTarget - cur) <= SETTLE) {
      cur = state.pedalTarget;
      state.pedalActive = false;
    }
    state.pedalCurrent = cur;
    applyPedal(cur * PEDAL_ANGLE);
  }

  return state.active.size > 0 || state.pedalActive;
}

/**
 * @param {ReturnType<createLiveState>} state
 * @param {(note: number, angle: number) => void} applyKey
 * @param {(angle: number) => void} [applyPedal]
 */
export function reset(state, applyKey, applyPedal) {
  for (const note of state.noteMap.keys()) {
    applyKey(note, 0);
  }
  if (state.pedalObj && applyPedal) {
    applyPedal(0);
  }
  state.pos.clear();
  state.vel.clear();
  state.target.clear();
  state.active.clear();
  state.pedalTarget = 0;
  state.pedalCurrent = 0;
  state.pedalActive = false;
}