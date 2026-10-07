import * as THREE from "three";

/**
 * Removable music desk. On a real Steinway the desk lifts out so a technician
 * can reach the action and dampers; here it slides toward the player, rises
 * and fades, revealing the hammers, dampers and repetition action beneath.
 *
 * The desk parts export as separate nodes tagged `case_part: "music_desk"`
 * (scripts/export_glb.py). They are kept out of the BatchedMesh (`noBatch`) and
 * get their own material copies, so fading them never touches the case
 * lacquer they share materials with.
 */

const SLIDE = 0.24; // metres toward the player (glTF +Z = Blender -Y)
const LIFT = 0.07; // metres up
const DURATION = 1.1; // seconds per remove/replace

function extras(obj) {
  return obj.userData?.extras ?? obj.userData ?? {};
}

function smoothstep(u) {
  const t = u < 0 ? 0 : u > 1 ? 1 : u;
  return t * t * (3 - 2 * t);
}

/** @param {THREE.Object3D} root */
export function buildMusicDesk(root) {
  /** @type {THREE.Object3D[]} */
  const parts = [];
  root.traverse((obj) => {
    if (extras(obj).case_part === "music_desk") parts.push(obj);
  });

  const materials = new Map();
  for (const part of parts) {
    part.traverse((child) => {
      child.userData.noBatch = true;
      if (!child.isMesh) return;
      const own = (m) => {
        if (!materials.has(m.uuid)) materials.set(m.uuid, m.clone());
        return materials.get(m.uuid);
      };
      child.material = Array.isArray(child.material)
        ? child.material.map(own)
        : own(child.material);
    });
  }
  const rest = parts.map((p) => p.position.clone());
  let shown = -1;

  return {
    available: parts.length > 0,
    /** @param {number} removed 0 = in place, 1 = taken off */
    apply(removed) {
      if (removed === shown) return;
      shown = removed;
      const slide = smoothstep(removed);
      const fade = 1 - smoothstep((removed - 0.35) / 0.65);
      parts.forEach((part, i) => {
        part.position.set(rest[i].x, rest[i].y + LIFT * slide, rest[i].z + SLIDE * slide);
        part.visible = fade > 0.001;
      });
      const transparent = fade < 0.999;
      for (const m of materials.values()) {
        if (m.transparent !== transparent) {
          m.transparent = transparent;
          m.depthWrite = !transparent;
          m.needsUpdate = true;
        }
        m.opacity = fade;
      }
    },
  };
}

/** @param {boolean} [removed] */
export function createDeskState(removed = false) {
  const v = removed ? 1 : 0;
  return { target: v, current: v, from: v, to: v, elapsed: 0 };
}

/**
 * Eased tween toward `state.target`.
 * @returns {boolean} still animating
 */
export function stepDesk(state, desk, dt) {
  if (state.target !== state.to) {
    state.from = state.current;
    state.to = state.target;
    state.elapsed = 0;
  }
  if (state.current === state.to) return false;
  state.elapsed += Math.min(dt, 0.05);
  const span = Math.abs(state.to - state.from) * DURATION;
  const u = span > 0 ? Math.min(state.elapsed / span, 1) : 1;
  state.current = THREE.MathUtils.lerp(state.from, state.to, u);
  desk.apply(state.current);
  return true;
}
