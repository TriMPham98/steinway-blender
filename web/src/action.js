/**
 * Port of extension/steinway_midi_piano/build/action.py driver expressions.
 *
 * Action parts export as separate glTF nodes tagged with `action_part` /
 * `action_note` extras, and every gain the Blender drivers use is exported
 * alongside as `action_*` extras — so this rig reads its constants from the
 * model instead of duplicating them.
 *
 * Real Steinway layout (player at the front): the key stick lifts the wippen
 * by its heel; the wippen (pinned at the rear) raises the jack, which pushes
 * the hammer's knuckle until the jack tender meets the let-off button and the
 * jack escapes; the repetition lever is stopped by the drop screw; the hammer
 * flies to the string on the live strike channel and falls back onto the
 * backcheck. The key end picks up the damper underlever (wire + head ride
 * it); the sustain pedal raises every underlever via the tray.
 */

import { PEDAL_ANGLE } from "./anim.js";

/** Matches build/action.py (PRESS_ANGLE = 3.5 deg). */
export const ACTION_Q = 1 / ((3.5 * Math.PI) / 180);
const PEDAL_Q = 1 / PEDAL_ANGLE;

/** Monotonic lift/drop — exponential approach cannot ring at equilibrium. */
const DAMPER_RISE_TAU = 0.02;
const DAMPER_DROP_TAU = 0.013;
const TRAY_RISE_TAU = 0.055;
const TRAY_DROP_TAU = 0.04;
const DAMPER_EPS = 5e-5;

/** Critically damped exponential — smooth lift, faster drop, no oscillation. */
function smoothDamper(pos, target, dt, riseTau, dropTau) {
  if (dt <= 0) return target;
  const err = target - pos;
  if (Math.abs(err) <= DAMPER_EPS) return target;
  const tau = err > 0 ? riseTau : dropTau;
  const next = pos + err * (1 - Math.exp(-dt / tau));
  return Math.max(0, next);
}

function extras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

/**
 * @typedef {{
 *   keyArm?: import('three').Object3D, psi: number,
 *   wippen?: import('three').Object3D, omega: number,
 *   jack?: import('three').Object3D, jackGain: number,
 *   repLever?: import('three').Object3D, leverGain: number,
 *   hammer?: import('three').Object3D,
 *   rest: number, slope: number, letoff: number, drop: number, cap: number,
 *   impulse: number, ramp: number,
 *   damper?: import('three').Object3D, damperRestY: number,
 *   liftA: number, liftG: number, liftK: number, pedalLift: number,
 *   damperLever?: import('three').Object3D, leverArm: number, pedalRot: number,
 *   liftPos: number,
 *   lastQ: number, lastH: number, lastP: number, lastPedal: number,
 * }} Unit
 */

/** @returns {Unit} */
function emptyUnit() {
  return {
    psi: 0,
    omega: 0,
    jackGain: 0,
    leverGain: 0,
    rest: 0,
    slope: 0,
    letoff: 0.88,
    drop: 0,
    cap: 0.35,
    impulse: 0.3,
    ramp: 8,
    damperRestY: 0,
    liftA: 0,
    liftG: 0,
    liftK: 0,
    pedalLift: 0,
    leverArm: 0.12,
    pedalRot: 0,
    liftPos: 0,
    lastQ: NaN,
    lastH: NaN,
    lastP: NaN,
    lastPedal: NaN,
  };
}

/** Batch group for every action mesh (see batching.js `batchGroup`). */
export const ACTION_BATCH_GROUP = "action";

/**
 * Parts that stay drawn even with the music desk on: from high angles they
 * show through the gap behind the nameboard (key frame, key sticks) or past
 * the desk's ends (damper heads on their wires). Cheap — the cost of the
 * action is the ~800 hammers/wippens/levers hidden under the plate.
 */
const ALWAYS_DRAWN = new Set(["frame", "key_arm", "damper_head", "damper_wire"]);

/**
 * Tag the hidden action's meshes so the batcher keeps them in their own draws,
 * which the viewer culls while the music desk covers them. Call before
 * batchMeshes().
 * @param {import('three').Object3D} root
 * @returns {number} meshes tagged
 */
export function tagActionMeshes(root) {
  let tagged = 0;
  root.traverse((obj) => {
    const part = extras(obj).action_part;
    // The static frame stays drawn: its key frame shows between the keys.
    if (!part || ALWAYS_DRAWN.has(part)) return;
    obj.traverse((child) => {
      if (child.isMesh && child.userData.batchGroup !== ACTION_BATCH_GROUP) {
        child.userData.batchGroup = ACTION_BATCH_GROUP;
        tagged++;
      }
    });
  });
  return tagged;
}

/**
 * @param {import('three').Object3D} root
 * @param {Map<number, import('three').Object3D>} noteMap
 */
export function buildActionRig(root, noteMap) {
  /** @type {Map<number, Unit>} */
  const units = new Map();
  let frames = 0;
  let damperTray = null;
  let trayRestY = 0;
  let trayGain = 0;
  let trayPos = 0;

  root.traverse((obj) => {
    const ex = extras(obj);
    const part = ex.action_part;
    if (!part) return;
    if (part === "frame") {
      frames++;
      return;
    }
    if (part === "damper_tray") {
      damperTray = obj;
      trayRestY = obj.position.y;
      trayGain = ex.action_gain ?? 0;
      return;
    }
    const note = ex.action_note;
    if (note == null || note < 0) return;
    let unit = units.get(note);
    if (!unit) {
      unit = emptyUnit();
      units.set(note, unit);
    }
    switch (part) {
      case "key_arm":
        unit.keyArm = obj;
        unit.psi = ex.action_psi ?? 0;
        break;
      case "wippen":
        unit.wippen = obj;
        unit.omega = ex.action_omega ?? 0;
        break;
      case "jack":
        unit.jack = obj;
        unit.jackGain = ex.action_gain ?? 0;
        break;
      case "rep_lever":
        unit.repLever = obj;
        unit.leverGain = ex.action_gain ?? 0;
        break;
      case "hammer":
        unit.hammer = obj;
        unit.rest = ex.action_rest ?? obj.rotation.x;
        unit.slope = ex.action_slope ?? 0;
        unit.letoff = ex.action_letoff ?? 0.88;
        unit.drop = ex.action_drop ?? 0;
        unit.cap = ex.action_cap ?? 0.35;
        unit.impulse = ex.action_impulse ?? 0.3;
        unit.ramp = ex.action_ramp ?? 1 / Math.max(1 - unit.letoff, 0.05);
        break;
      case "damper_head":
        unit.damper = obj;
        // Blender location.z (up) exports as glTF/Three.js position.y.
        unit.damperRestY = obj.position.y;
        unit.liftA = ex.action_lift_a ?? 0;
        unit.liftG = ex.action_lift_g ?? 0;
        unit.liftK = ex.action_lift_k ?? 0;
        unit.pedalLift = ex.action_pedal_lift ?? 0;
        break;
      case "damper_lever":
        unit.damperLever = obj;
        unit.leverArm = ex.action_arm ?? 0.12;
        unit.pedalRot = ex.action_pedal_rot ?? 0;
        if (!unit.liftA) unit.liftA = ex.action_lift_a ?? 0;
        if (!unit.liftG) unit.liftG = ex.action_lift_g ?? 0;
        break;
      default:
        break; // damper_wire rides its head as a glTF child
    }
  });

  /**
   * Pose one note. Rigid parts only change when their inputs do, so a held
   * chord costs nothing per frame; only the eased damper head keeps moving.
   * @returns {boolean} damper still easing toward its target
   */
  function apply(unit, keyRotX, hammer, pedalRotX, dt) {
    const qRaw = keyRotX * ACTION_Q;
    const pedalQ = clamp01(pedalRotX * PEDAL_Q);
    const qc = Math.min(qRaw, 1);
    const keyTravel = Math.max(unit.liftA * qc - unit.liftG, 0);

    if (qRaw !== unit.lastQ || hammer !== unit.lastH) {
      const q = clamp01(qRaw);
      const lo = unit.letoff;
      if (unit.keyArm) unit.keyArm.rotation.x = unit.psi * q;
      if (unit.wippen) unit.wippen.rotation.x = -unit.omega * q;
      const escape = Math.max(qc - lo, 0);
      if (unit.jack) unit.jack.rotation.x = unit.jackGain * escape;
      if (unit.repLever) unit.repLever.rotation.x = unit.leverGain * escape;
      if (unit.hammer) {
        const raw =
          unit.slope * Math.min(q, lo) -
          unit.drop * Math.min(escape * unit.ramp, 1) +
          unit.impulse * hammer;
        unit.hammer.rotation.x = unit.rest + Math.min(raw, unit.cap);
      }
      unit.lastQ = qRaw;
      unit.lastH = hammer;
    }

    if (unit.damperLever && (qRaw !== unit.lastP || pedalRotX !== unit.lastPedal)) {
      unit.damperLever.rotation.x = -Math.max(
        keyTravel / unit.leverArm,
        unit.pedalRot * pedalQ,
      );
      unit.lastP = qRaw;
      unit.lastPedal = pedalRotX;
    }

    if (!unit.damper) return false;
    const target = Math.max(keyTravel * unit.liftK, unit.pedalLift * pedalQ);
    const next = smoothDamper(unit.liftPos, target, dt, DAMPER_RISE_TAU, DAMPER_DROP_TAU);
    if (next !== unit.liftPos) {
      unit.liftPos = next;
      unit.damper.position.y = unit.damperRestY + next;
    }
    return next !== target;
  }

  return {
    partCount: units.size,
    hasFrame: frames > 0,
    /**
     * @param {number} note
     * @param {number} keyRotX key rotation.x (radians)
     * @param {number} hammer strike channel 0..1
     * @param {number} pedalRotX pedal rotation.x (radians)
     * @param {number} [dt] frame dt for damper dynamics (seconds)
     * @returns {boolean} damper still easing
     */
    apply(note, keyRotX, hammer, pedalRotX, dt = 0) {
      const unit = units.get(note);
      return unit ? apply(unit, keyRotX, hammer, pedalRotX, dt) : false;
    },
    /** @returns {boolean} tray still easing */
    applyPedalTray(pedalRotX, dt = 0) {
      if (!damperTray) return false;
      const target = trayGain * clamp01(pedalRotX * PEDAL_Q);
      const next = smoothDamper(trayPos, target, dt, TRAY_RISE_TAU, TRAY_DROP_TAU);
      if (next !== trayPos) {
        trayPos = next;
        damperTray.position.y = trayRestY + next;
      }
      return next !== target;
    },
    reset() {
      trayPos = 0;
      if (damperTray) damperTray.position.y = trayRestY;
      for (const unit of units.values()) {
        unit.liftPos = 0;
        unit.lastQ = NaN;
        unit.lastP = NaN;
        unit.lastPedal = NaN;
        if (unit.damper) unit.damper.position.y = unit.damperRestY;
        apply(unit, 0, 0, 0, 0);
      }
    },
  };
}
