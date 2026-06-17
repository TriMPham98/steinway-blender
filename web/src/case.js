/**
 * Port of extension/steinway_midi_piano/build/case.py lid drivers.
 * Expects moving case meshes exported separately (not joined into Piano_Static).
 *
 * Blender lid driver writes rotation_euler[1]; glTF maps that to Three.js rotation.z.
 */

// Only the prop stick folds. The cup rides the lid (parented to it in the
// glTF), and the hinge hardware stays put in the static mesh.
const DEFAULT_LID_PROP_PARTS = ["Lid Support Prop"];

const DEFAULTS = {
  lid_tilt: 0.27,
  prop_fold: -1.0245,
  lid_open: 1,
};

// Seconds for a full open or close. The lid moves on a time-based eased tween
// (not exponential smoothing) so it glides at a stately, even pace.
const LID_ANIM_DURATION = 2.3;

// Phased open/close so the prop clears the lid instead of clipping through it.
// Closing (lidOpen 1 -> 0): the lid first lifts slightly past its open angle to
// raise the cup off the prop tip, holds there while the prop folds flat, then
// lowers all the way shut. Opening reverses it. Every segment uses smoothstep
// so the lid/prop velocity is continuous across the phase boundaries (no jerk).
const LID_OVEREXTEND = 0.12; // rad the lid rises above its open rest pose
const LIFT_T = 0.86; // lidOpen in [LIFT_T,1]: lid lifting off the prop
const FOLD_T = 0.4; // lidOpen in [FOLD_T,LIFT_T]: prop folds; below: lid descends
// The measured lid tilt lands the closed lid ~1cm proud and slightly bent-side
// high. A touch more rotation levels it on the rim, then a small drop seats it.
const LID_CLOSE_EXTRA = 0.008; // extra close rotation (rad) to land the lid level
const LID_SEAT_DROP = 0.009; // metres the lid lowers onto the rim once shut

function lerp(a, b, u) {
  return a + (b - a) * u;
}
function clamp01(u) {
  return u < 0 ? 0 : u > 1 ? 1 : u;
}
// Smoothstep: zero slope at both ends, so segments meet without a velocity jump.
function smoothstep(u) {
  u = clamp01(u);
  return u * u * (3 - 2 * u);
}
// Ease-in-out for the overall tween so it starts and stops gently.
function easeInOut(u) {
  u = clamp01(u);
  return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
}

// Lid rotation offset from its open rest pose: negative = lifted above open,
// positive = rotated down toward shut (up to lidTilt = flat/closed).
function lidCloseOffset(t, lidTilt) {
  if (t >= LIFT_T) return -LID_OVEREXTEND * smoothstep((1 - t) / (1 - LIFT_T));
  if (t >= FOLD_T) return -LID_OVEREXTEND;
  return lerp(-LID_OVEREXTEND, lidTilt + LID_CLOSE_EXTRA, smoothstep((FOLD_T - t) / FOLD_T));
}

// Prop fold: 0 = upright, 1 = flat. Only folds once the lid has lifted clear.
function propFoldFrac(t) {
  return smoothstep((LIFT_T - t) / (LIFT_T - FOLD_T));
}

// Seat drop: 0 until the lid starts its final descent, 1 fully shut. Tracks the
// descent phase so the lid lowers onto the rim exactly as it rotates flat.
function lidSeatFrac(t) {
  return smoothstep((FOLD_T - t) / FOLD_T);
}

function extras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

/**
 * @param {THREE.Object3D} root
 * @param {object} [manifestCase]
 */
export function buildCaseRig(root, manifestCase) {
  const cfg = { ...DEFAULTS, ...manifestCase };
  const names = {
    lid_big: cfg.nodes?.lid_big ?? "Large Lid Section",
    lid_fold_hinge: cfg.nodes?.lid_fold_hinge ?? "Lid Fold Hinge",
  };
  const lidPropNames = cfg.nodes?.lid_prop ?? DEFAULT_LID_PROP_PARTS;

  const byName = new Map();
  /** @type {Map<string, THREE.Object3D>} */
  const byPart = new Map();
  root.traverse((obj) => {
    if (obj.name) byName.set(obj.name, obj);
    const part = extras(obj).case_part;
    if (part) byPart.set(part, obj);
  });

  const lidBig =
    byPart.get("lid_big") ?? byName.get(names.lid_big) ?? null;
  const foldHinge =
    byPart.get("lid_fold_hinge") ??
    byName.get(names.lid_fold_hinge) ??
    null;
  // Prefer the case_part tag: glTF/three.js rewrites node names ("Lid Support
  // Prop" -> "Lid_Support_Prop"), so a raw manifest-name lookup misses.
  const lidPropParts = [];
  const taggedProp = byPart.get("lid_prop");
  if (taggedProp) {
    lidPropParts.push(taggedProp);
  } else {
    for (const name of lidPropNames) {
      const obj = byName.get(name) ?? byName.get(name.replace(/[\s.]/g, "_"));
      if (obj) lidPropParts.push(obj);
    }
  }

  const rest = {
    lidBigZ: lidBig?.rotation.z ?? 0,
    lidBigY: lidBig?.position.y ?? 0,
    foldX: foldHinge?.rotation.x ?? 0,
    propZ: lidPropParts.map((p) => p.rotation.z),
  };

  return {
    available: !!lidBig,
    hasLid: !!lidBig,
    hasLidProp: lidPropParts.length > 0,
    hasFold: !!foldHinge,
    /**
     * @param {{ lidOpen?: number }} pose
     *   lidOpen: 1 = open (as modeled), 0 = closed
     */
    apply(pose) {
      const lidOpen = pose.lidOpen ?? cfg.lid_open;

      if (lidBig) {
        lidBig.rotation.z =
          rest.lidBigZ - lidCloseOffset(lidOpen, cfg.lid_tilt);
        // Rotating about the spine alone leaves the closed lid hovering ~1cm
        // above the rim, so drop it onto the body during the final descent.
        lidBig.position.y = rest.lidBigY - LID_SEAT_DROP * lidSeatFrac(lidOpen);
      }
      if (foldHinge) {
        foldHinge.rotation.x = rest.foldX;
      }

      // Fold the prop stick down onto the rim, but only after the lid has lifted
      // off it (see lidCloseOffset). Blender drives the prop's hinge Y; glTF
      // maps that to Three.js rotation.z (same sign flip as the lid).
      const fold = propFoldFrac(lidOpen);
      lidPropParts.forEach((part, i) => {
        part.rotation.z = rest.propZ[i] - fold * cfg.prop_fold;
      });
    },
    /** Snap to the exported open rest pose. */
    reset() {
      this.apply({ lidOpen: cfg.lid_open });
    },
  };
}

/** @param {object} [manifestDefaults] */
export function createCaseState(manifestDefaults) {
  const d = { ...DEFAULTS, ...manifestDefaults };
  const v = d.lid_open;
  return {
    target: { lidOpen: v },
    current: { lidOpen: v },
    from: v,
    animTo: v,
    elapsed: 0,
  };
}

/**
 * Drive the lid on a fixed-duration eased tween toward `target.lidOpen`.
 * @param {{ target: object, current: object, from: number, animTo: number, elapsed: number }} state
 * @param {ReturnType<typeof buildCaseRig>} rig
 * @param {number} dt seconds
 */
export function stepCase(state, rig, dt) {
  // A new target restarts the tween from wherever the lid currently is.
  if (state.target.lidOpen !== state.animTo) {
    state.from = state.current.lidOpen;
    state.animTo = state.target.lidOpen;
    state.elapsed = 0;
  }
  const animating = state.from !== state.animTo && state.elapsed < LID_ANIM_DURATION;
  if (animating) {
    // Clamp dt so a frame hitch (or a backgrounded tab) can't snap the lid.
    state.elapsed += Math.min(dt, 0.05);
    const u = clamp01(state.elapsed / LID_ANIM_DURATION);
    state.current.lidOpen = lerp(state.from, state.animTo, easeInOut(u));
  } else {
    state.current.lidOpen = state.animTo;
  }
  rig.apply(state.current);
  return animating;
}