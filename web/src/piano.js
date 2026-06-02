import * as THREE from "three";
import {
  createLiveState,
  easeStep,
  feelFromSettings,
  MIDI_HIGH,
  MIDI_LOW,
  reset,
  setNote,
  setSustain,
} from "./anim.js";

/**
 * Three.js bridge for the Blender live anim pipeline.
 */
export class PianoController {
  /**
   * @param {THREE.Object3D} root
   * @param {import('./anim.js').Feel} [initialFeel]
   * @param {{ keys: { note: number, name: string }[], pedal: string | null, press_angle_deg?: number }} manifest
   */
  constructor(root, manifest, initialFeel) {
    this.root = root;
    /** @type {Map<number, THREE.Object3D>} */
    this.noteMap = new Map();
    this.pedalObj = null;

    const byName = new Map();
    root.traverse((obj) => {
      if (obj.name) byName.set(obj.name, obj);
    });

    for (const { note, name } of manifest.keys ?? []) {
      const obj = byName.get(name);
      if (obj) this.noteMap.set(note, obj);
    }

    if (manifest.pedal) {
      this.pedalObj = byName.get(manifest.pedal) ?? null;
    }

    if (this.noteMap.size === 0) {
      root.traverse((obj) => {
        const raw = obj.userData?.midi_note ?? obj.userData?.extras?.midi_note;
        if (raw != null) this.noteMap.set(Number(raw), obj);
        if (obj.userData?.steinway_role === "sustain_pedal") {
          this.pedalObj = obj;
        }
      });
    }

    this.pressAngleDeg = manifest.press_angle_deg ?? 3.5;
    this.settings = {
      snappiness: 1,
      velocitySensitivity: 1,
    };
    this.state = createLiveState(
      this.noteMap,
      this.pedalObj,
      initialFeel ?? feelFromSettings(this.settings),
    );
  }

  get keyCount() {
    return this.noteMap.size;
  }

  get pressAngle() {
    return THREE.MathUtils.degToRad(this.pressAngleDeg);
  }

  /** @param {{ snappiness?: number, velocitySensitivity?: number, pressAngleDeg?: number }} next */
  applySettings(next) {
    if (next.pressAngleDeg != null) this.pressAngleDeg = next.pressAngleDeg;
    if (next.snappiness != null) this.settings.snappiness = next.snappiness;
    if (next.velocitySensitivity != null) {
      this.settings.velocitySensitivity = next.velocitySensitivity;
    }
    this.state.feel = feelFromSettings(this.settings);
  }

  noteOn(note, velocity = 100) {
    setNote(this.state, note, velocity);
  }

  noteOff(note) {
    setNote(this.state, note, 0);
  }

  setSustain(on) {
    setSustain(this.state, on);
  }

  /** @param {number} dt */
  step(dt) {
    return easeStep(
      this.state,
      this.pressAngle,
      dt,
      (note, angle) => {
        const obj = this.noteMap.get(note);
        if (obj) obj.rotation.x = angle;
      },
      (angle) => {
        if (this.pedalObj) this.pedalObj.rotation.x = angle;
      },
    );
  }

  resetKeys() {
    reset(
      this.state,
      (note, angle) => {
        const obj = this.noteMap.get(note);
        if (obj) obj.rotation.x = angle;
      },
      (angle) => {
        if (this.pedalObj) this.pedalObj.rotation.x = angle;
      },
    );
  }

  pick(raycaster) {
    const meshes = [];
    for (const obj of this.noteMap.values()) {
      obj.traverse((child) => {
        if (child.isMesh) meshes.push(child);
      });
    }
    const hits = raycaster.intersectObjects(meshes, false);
    if (!hits.length) return null;
    let o = hits[0].object;
    while (o) {
      for (const [note, key] of this.noteMap) {
        if (o === key && note >= MIDI_LOW && note <= MIDI_HIGH) return note;
      }
      o = o.parent;
    }
    return null;
  }
}