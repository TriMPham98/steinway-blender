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

/** build/action.py lift_exprs geometry gains. */
const HEAD_LIFT_GAIN = 0.8182;
const LEVER_ROT_GAIN = 18.1818;
const PEDAL_LEVER_GAIN = DPEDAL_LIFT / 0.045;

/** Damper head felt block (~5–12 g by register). */
const HEAD_MASS_LO = 0.012;
const HEAD_MASS_HI = 0.005;
const HEAD_SPRING = 2600;
const HEAD_DAMP_LIFT = 2 * Math.sqrt(HEAD_SPRING * HEAD_MASS_LO) * 0.92;
const HEAD_DAMP_DROP = HEAD_DAMP_LIFT * 0.55;

/** Underlever (~12 g effective at pivot) — stiffer, leads the head via the wire. */
const LEVER_MASS = 0.012;
const LEVER_SPRING = 5200;
const LEVER_DAMP = 2 * Math.sqrt(LEVER_SPRING * LEVER_MASS) * 0.95;

/** Wire pulls head when the lever outruns it (stiff steel, slight compliance). */
const WIRE_K = 2200;

/** Sustain tray + underlever backs (~90 g). */
const TRAY_MASS = 0.09;
const TRAY_SPRING = 1100;
const TRAY_DAMP = 2 * Math.sqrt(TRAY_SPRING * TRAY_MASS) * 0.93;

const GRAVITY = 9.81;
const PHYS_SUBSTEP = 0.004;

/** Exact Blender driver targets for one damper note. */
function damperDriverTargets(liftA, q, pedalQ) {
  const keyTravel = Math.max(liftA * q - DGAP, 0);
  const keyLift = keyTravel * HEAD_LIFT_GAIN;
  const keyTorque = keyTravel * LEVER_ROT_GAIN;
  const pedalLift = DPEDAL_LIFT * pedalQ;
  const pedalTorque = PEDAL_LEVER_GAIN * pedalQ;
  return {
    lift: Math.max(keyLift, pedalLift),
    lever: -Math.max(keyTorque, pedalTorque),
  };
}

function headMassForNote(note) {
  const t = Math.max(0, Math.min(1, (note - 21) / 67));
  return HEAD_MASS_LO + (HEAD_MASS_HI - HEAD_MASS_LO) * t;
}

function liftFromLeverAngle(leverRad) {
  return Math.max((-leverRad / LEVER_ROT_GAIN) * HEAD_LIFT_GAIN, 0);
}

function integrateSpring(pos, vel, target, k, c, m, dt, extraForce = 0) {
  if (dt <= 0) return { pos: target, vel: 0 };
  const n = Math.max(1, Math.ceil(dt / PHYS_SUBSTEP));
  const h = dt / n;
  let p = pos;
  let v = vel;
  for (let i = 0; i < n; i++) {
    const a = (k * (target - p) - c * v + extraForce) / m;
    v += a * h;
    p += v * h;
    if (p < 0) {
      p = 0;
      v = Math.max(v, 0);
    }
  }
  return { pos: p, vel: v };
}

/** Head follows driver + wire tension; drops with gravity when the wire goes slack. */
function integrateDamperHead(pos, vel, driverTarget, leverRad, m, dt) {
  if (dt <= 0) return { pos: driverTarget, vel: 0 };
  const n = Math.max(1, Math.ceil(dt / PHYS_SUBSTEP));
  const h = dt / n;
  let p = pos;
  let v = vel;
  for (let i = 0; i < n; i++) {
    const wireLift = liftFromLeverAngle(leverRad);
    const wireTension = wireLift > p + 1e-6;
    const tgt = wireTension ? Math.max(driverTarget, wireLift) : driverTarget;
    const dropping = tgt < p - 1e-6 || (!wireTension && v < 0);
    const c = dropping ? HEAD_DAMP_DROP : HEAD_DAMP_LIFT;
    const gravity = dropping ? -GRAVITY * m * 0.85 : 0;
    const wirePull = wireTension ? WIRE_K * (wireLift - p) : 0;
    const a = (HEAD_SPRING * (tgt - p) - c * v + wirePull + gravity) / m;
    v += a * h;
    p += v * h;
    if (p < 0) {
      p = 0;
      v = Math.max(v, 0);
    }
  }
  return { pos: p, vel: v };
}

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
  /** @type {Map<number, { keyArm?: THREE.Object3D, wippen?: THREE.Object3D, jack?: THREE.Object3D, repLever?: THREE.Object3D, hammer?: THREE.Object3D, damper?: THREE.Object3D, damperLever?: THREE.Object3D, psi?: number, letoff?: number, phiCap?: number, liftA?: number, damperRestY?: number, liftPos?: number, liftVel?: number, leverPos?: number, leverVel?: number }>} */
  const units = new Map();
  let frame = null;
  let damperTray = null;
  let trayRestY = null;
  let trayPos = 0;
  let trayVel = 0;

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
     * @param {number} [dt] frame dt for damper dynamics (seconds)
     */
    apply(note, keyRotX, hammer, pedalRotX, dt = 0) {
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
      const { lift: targetLift, lever: targetLever } = damperDriverTargets(
        unit.liftA ?? 0,
        q,
        pedalQ,
      );

      let leverRad = unit.leverPos ?? 0;
      if (unit.damperLever) {
        const leverStep = integrateSpring(
          leverRad,
          unit.leverVel ?? 0,
          targetLever,
          LEVER_SPRING,
          LEVER_DAMP,
          LEVER_MASS,
          dt,
        );
        unit.leverPos = leverStep.pos;
        unit.leverVel = leverStep.vel;
        leverRad = unit.leverPos;
        unit.damperLever.rotation.x = leverRad;
      }

      if (unit.damper && unit.damperRestY != null) {
        const headStep = integrateDamperHead(
          unit.liftPos ?? 0,
          unit.liftVel ?? 0,
          targetLift,
          leverRad,
          headMassForNote(note),
          dt,
        );
        unit.liftPos = headStep.pos;
        unit.liftVel = headStep.vel;
        unit.damper.position.y = unit.damperRestY + unit.liftPos;
      }
    },
    applyPedalTray(pedalRotX, dt = 0) {
      if (!damperTray || trayRestY == null) return;
      const pedalQ = Math.max(0, Math.min(1, pedalRotX * PEDAL_Q));
      const targetOffset = (DPEDAL_LIFT / HEAD_LIFT_GAIN) * pedalQ;
      const step = integrateSpring(
        trayPos,
        trayVel,
        targetOffset,
        TRAY_SPRING,
        TRAY_DAMP,
        TRAY_MASS,
        dt,
      );
      trayPos = step.pos;
      trayVel = step.vel;
      damperTray.position.y = trayRestY + trayPos;
    },
    reset() {
      trayPos = 0;
      trayVel = 0;
      for (const unit of units.values()) {
        unit.liftPos = 0;
        unit.liftVel = 0;
        unit.leverPos = 0;
        unit.leverVel = 0;
      }
      for (const note of noteMap.keys()) {
        this.apply(note, 0, 0, 0, 0);
      }
      this.applyPedalTray(0, 0);
    },
  };
}