/**
 * Port of extension/steinway_midi_piano/build/case.py lid / fallboard drivers.
 * Expects moving case meshes exported separately (not joined into Piano_Static).
 *
 * Blender lid driver writes rotation_euler[1]; glTF maps that to Three.js rotation.z.
 */

const DEFAULTS = {
  lid_tilt: 0.27,
  fold_back: 3.05,
  fall_closed: 1.48,
  lid_open: 1,
  lid_flap_fold: 0,
  fallboard_open: 1,
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
    fallboard: cfg.nodes?.fallboard ?? "Fall Board",
  };

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
  const fallboard =
    byPart.get("fallboard") ?? byName.get(names.fallboard) ?? null;

  const rest = {
    lidBigZ: lidBig?.rotation.z ?? 0,
    foldX: foldHinge?.rotation.x ?? 0,
    fallX: fallboard?.rotation.x ?? 0,
  };

  return {
    available: !!(lidBig || fallboard),
    hasLid: !!lidBig,
    hasFold: !!foldHinge,
    hasFallboard: !!fallboard,
    /**
     * @param {{ lidOpen?: number, lidFlapFold?: number, fallboardOpen?: number }} pose
     *   lidOpen / fallboardOpen: 1 = open (as modeled), 0 = closed
     */
    apply(pose) {
      const lidOpen = pose.lidOpen ?? cfg.lid_open;
      const lidFlapFold = pose.lidFlapFold ?? cfg.lid_flap_fold;
      const fallboardOpen = pose.fallboardOpen ?? cfg.fallboard_open;

      if (lidBig) {
        lidBig.rotation.z =
          rest.lidBigZ - (1 - lidOpen) * cfg.lid_tilt;
      }
      if (foldHinge) {
        foldHinge.rotation.x = rest.foldX + lidFlapFold * cfg.fold_back;
      }
      if (fallboard) {
        fallboard.rotation.x =
          rest.fallX + (1 - fallboardOpen) * cfg.fall_closed;
      }
    },
    /** Snap to the exported open rest pose. */
    reset() {
      this.apply({
        lidOpen: cfg.lid_open,
        lidFlapFold: cfg.lid_flap_fold,
        fallboardOpen: cfg.fallboard_open,
      });
    },
  };
}

/** @param {object} [manifestDefaults] */
export function createCaseState(manifestDefaults) {
  const d = { ...DEFAULTS, ...manifestDefaults };
  const pose = {
    lidOpen: d.lid_open,
    lidFlapFold: d.lid_flap_fold,
    fallboardOpen: d.fallboard_open,
  };
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
  state.current.lidFlapFold = smoothStep(
    state.current.lidFlapFold,
    state.target.lidFlapFold,
    dt,
  );
  state.current.fallboardOpen = smoothStep(
    state.current.fallboardOpen,
    state.target.fallboardOpen,
    dt,
  );
  rig.apply(state.current);
  const settled =
    Math.abs(state.current.lidOpen - state.target.lidOpen) < 1e-3 &&
    Math.abs(state.current.lidFlapFold - state.target.lidFlapFold) < 1e-3 &&
    Math.abs(state.current.fallboardOpen - state.target.fallboardOpen) < 1e-3;
  return !settled;
}