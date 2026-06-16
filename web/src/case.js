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

const CASE_TAU = 0.38;

function extras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

function smoothStep(current, target, dt, tau = CASE_TAU) {
  if (dt <= 0) return target;
  if (Math.abs(target - current) < 1e-4) return target;
  const alpha = 1 - Math.exp(-dt / tau);
  return current + (target - current) * alpha;
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
          rest.lidBigZ - (1 - lidOpen) * cfg.lid_tilt;
      }
      if (foldHinge) {
        foldHinge.rotation.x = rest.foldX;
      }

      // Fold the prop stick down onto the rim as the lid closes. Blender drives
      // its hinge Y; glTF maps that to Three.js rotation.z (same sign flip as
      // the lid). Prop + cup share the hinge pivot, so they fold together.
      const propAngle = (1 - lidOpen) * cfg.prop_fold;
      lidPropParts.forEach((part, i) => {
        part.rotation.z = rest.propZ[i] - propAngle;
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
  const pose = { lidOpen: d.lid_open };
  return {
    target: { ...pose },
    current: { ...pose },
  };
}

/**
 * @param {{ target: object, current: object }} state
 * @param {ReturnType<typeof buildCaseRig>} rig
 * @param {number} dt
 */
export function stepCase(state, rig, dt) {
  state.current.lidOpen = smoothStep(
    state.current.lidOpen,
    state.target.lidOpen,
    dt,
  );
  rig.apply(state.current);
  return Math.abs(state.current.lidOpen - state.target.lidOpen) >= 1e-3;
}