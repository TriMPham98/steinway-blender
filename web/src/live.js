import { parseMidiMessage } from "./midi.js";

/**
 * Live MIDI session — mirrors STEINWAY_OT_live modal loop.
 */
export class LiveSession {
  /**
   * @param {import('./piano.js').PianoController} piano
   * @param {{
   *   onStatus?: (msg: string) => void,
   *   onRunningChange?: (running: boolean) => void,
   *   getSettings?: () => { pressAngleDeg?: number, snappiness?: number, velocitySensitivity?: number },
   * }} hooks
   */
  constructor(piano, hooks = {}) {
    this.piano = piano;
    this.hooks = hooks;
    this.running = false;
    /** @type {MIDIAccess | null} */
    this.access = null;
    /** @type {MIDIInput | null} */
    this.input = null;
    this._lastT = 0;
    this._raf = 0;
    this._boundMidi = (e) => this._onMidi(e);
  }

  get isRunning() {
    return this.running;
  }

  /**
   * @param {MIDIAccess} access
   * @param {string} portName
   */
  start(access, portName) {
    if (this.running) return;
    const input = [...access.inputs.values()].find((i) => i.name === portName);
    if (!input) {
      throw new Error(`MIDI port not found: ${portName}`);
    }
    this.access = access;
    this.input = input;
    input.onmidimessage = this._boundMidi;
    this.running = true;
    this._lastT = performance.now() / 1000;
    this._tick();
    this.hooks.onRunningChange?.(true);
    this.hooks.onStatus?.(`Live: ${portName}`);
  }

  stop() {
    if (!this.running) return;
    if (this.input) {
      this.input.onmidimessage = null;
      this.input = null;
    }
    this.running = false;
    cancelAnimationFrame(this._raf);
    this._raf = 0;
    this.piano.resetKeys();
    this.hooks.onRunningChange?.(false);
    this.hooks.onStatus?.("Stopped");
  }

  _onMidi(event) {
    if (!this.running) return;
    for (const ev of parseMidiMessage(event)) {
      if (ev[0] === "note") {
        this.piano.noteOn(ev[1], ev[2]);
      } else if (ev[0] === "sustain") {
        this.piano.setSustain(ev[1]);
      }
    }
  }

  _tick() {
    if (!this.running) return;
    const now = performance.now() / 1000;
    const dt = this._lastT ? now - this._lastT : 0.01;
    this._lastT = now;
    if (this.hooks.getSettings) {
      this.piano.applySettings(this.hooks.getSettings());
    }
    this.piano.step(dt);
    this._raf = requestAnimationFrame(() => this._tick());
  }
}