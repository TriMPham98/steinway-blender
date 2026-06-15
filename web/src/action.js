/**
 * Port of extension/steinway_midi_piano/build/action.py driver expressions.
 * Action parts export as separate glTF nodes with action_part / action_* extras.
 */

import { PEDAL_ANGLE } from "./anim.js";

/** Matches build/action.py (PRESS_ANGLE = 3.5 deg). */
export const ACTION_Q = 1 / ((3.5 * Math.PI) / 180);

const OMEGA = 0.00933 / 0.105;
const JACK_GAIN = (OMEGA * 0.167) / 0.013;
const JACK_Q0 = 0.85;
const LEVER_GAIN = (OMEGA * 0.193) / 0.048;
const LEVER_Q0 = 0.879;
const HAM_SLOPE = (OMEGA * 0.18) / 0.04;
const HAM_DROP = 0.026;
const HAM_IMPULSE = 0.45;
const DGAP = 0.0048;
const DPEDAL_LIFT = 0.0055;
const PEDAL_Q = 1 / PEDAL_ANGLE;

function extras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

function pressQ(keyRotX) {
  return Math.max(0, Math.min(1, keyRotX * ACTION_Q));
}

function hammerRot(q, h, lo, phiCap) {
  const ramp = 1 / Math.max(1 - lo, 0.05);
  const past = Math.max(q - lo, 0) * ramp;
  const raw =
    HAM_SLOPE * Math.min(q, lo) +
    HAM_DROP * Math.min(past, 1) +
    HAM_IMPULSE * h;
  return -Math.min(raw, phiCap);
}

/**
 * @param {THREE.Object3D} root
 * @param {Map<number, THREE.Object3D>} noteMap
 */
export function buildActionRig(root, noteMap) {
  /** @type {Map<number, { keyArm?: THREE.Object3D, wippen?: THREE.Object3D, jack?: THREE.Object3D, repLever?: THREE.Object3D, hammer?: THREE.Object3D, damper?: THREE.Object3D, damperLever?: THREE.Object3D, psi?: number, letoff?: number, phiCap?: number, liftA?: number, damperRestY?: number }>} */
  const units = new Map();
  let frame = null;
  let damperTray = null;
  let trayRestY = null;

  root.traverse((obj) => {
    const ex = extras(obj);
    const part = ex.action_part;
    const note = ex.action_note;
    if (!part) return;
    if (part === "frame") {
      frame = obj;
      return;
    }
    if (part === "damper_tray") {
      damperTray = obj;
      trayRestY = obj.position.y;
      return;
    }
    if (note == null || note < 0) return;
    const unit = units.get(note) ?? {};
    if (part === "key_arm") unit.keyArm = obj;
    if (part === "wippen") unit.wippen = obj;
    if (part === "jack") unit.jack = obj;
    if (part === "rep_lever") unit.repLever = obj;
    if (part === "hammer") unit.hammer = obj;
    if (part === "damper_head") {
      unit.damper = obj;
      // Blender location.z (up) exports as glTF/Three.js position.y.
      unit.damperRestY = obj.position.y;
    }
    if (part === "damper_lever") unit.damperLever = obj;
    if (ex.action_psi != null) unit.psi = ex.action_psi;
    if (ex.action_letoff != null) unit.letoff = ex.action_letoff;
    if (ex.action_phi_cap != null) unit.phiCap = ex.action_phi_cap;
    if (ex.action_lift_a != null) unit.liftA = ex.action_lift_a;
    units.set(note, unit);
  });

  return {
    partCount: units.size,
    hasFrame: frame != null,
    /**
     * @param {number} note
     * @param {number} keyRotX key rotation.x (radians)
     * @param {number} hammer strike channel 0..1
     * @param {number} pedalRotX pedal rotation.x (radians)
     */
    apply(note, keyRotX, hammer, pedalRotX) {
      const unit = units.get(note);
      if (!unit) return;
      const q = pressQ(keyRotX);
      const psi = unit.psi ?? 0;
      const lo = unit.letoff ?? 0.85;
      const phiCap = unit.phiCap ?? 1.2;

      if (unit.keyArm) unit.keyArm.rotation.x = psi * q;
      if (unit.wippen) unit.wippen.rotation.x = OMEGA * q;
      if (unit.jack) {
        unit.jack.rotation.x = -Math.max(JACK_GAIN * q - JACK_GAIN * JACK_Q0, 0);
      }
      if (unit.repLever) {
        unit.repLever.rotation.x = -Math.max(LEVER_GAIN * q - LEVER_GAIN * LEVER_Q0, 0);
      }
      if (unit.hammer) {
        unit.hammer.rotation.x = hammerRot(q, hammer, lo, phiCap);
      }

      const pedalQ = Math.max(0, Math.min(1, pedalRotX * PEDAL_Q));
      const keyLift = Math.max((unit.liftA ?? 0) * q - DGAP, 0) * 0.8182;
      const pedalLift = DPEDAL_LIFT * pedalQ;
      const lift = Math.max(keyLift, pedalLift);
      if (unit.damper && unit.damperRestY != null) {
        unit.damper.position.y = unit.damperRestY + lift;
      }
      const keyT = Math.max((unit.liftA ?? 0) * q - DGAP, 0) * 18.1818;
      const pedalT = (DPEDAL_LIFT / 0.045) * pedalQ;
      if (unit.damperLever) {
        unit.damperLever.rotation.x = -Math.max(keyT, pedalT);
      }
    },
    applyPedalTray(pedalRotX) {
      if (!damperTray || trayRestY == null) return;
      const pedalQ = Math.max(0, Math.min(1, pedalRotX * PEDAL_Q));
      damperTray.position.y = trayRestY + (DPEDAL_LIFT / 0.8182) * pedalQ;
    },
    reset() {
      for (const note of noteMap.keys()) {
        this.apply(note, 0, 0, 0);
      }
      this.applyPedalTray(0);
    },
  };
}