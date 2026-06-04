/**
 * Sampled-grand sound engine for the no-MIDI play path.
 *
 * When a real MIDI piano is connected the hardware makes its own sound, so the
 * web app stays silent and only mirrors the key motion. With no MIDI hardware,
 * this plays a real sampled acoustic grand — smplr's `SplendidGrandPiano`,
 * streamed from its CDN — for pointer- and computer-keyboard-driven notes.
 *
 * Damper behaviour mirrors the visual pipeline: releasing a key normally damps
 * its voice, but with the sustain pedal down the voice rings on until the pedal
 * lifts (or a still-held key keeps it ringing).
 */
import { Reverb, SplendidGrandPiano } from "smplr";

const DEFAULT_VELOCITY = 90;

export class PianoAudio {
  constructor() {
    /** @type {AudioContext | null} */
    this.context = null;
    /** @type {ReturnType<typeof SplendidGrandPiano> | null} */
    this.piano = null;
    /** Samples decoded and ready to play. */
    this.loaded = false;
    /** Master enable; turning off mutes and releases everything. */
    this.enabled = true;
    /** Sustain pedal held (CC64 / spacebar). */
    this.sustain = false;
    /** @type {Promise<unknown> | null} */
    this._loadPromise = null;
    /** note -> StopFn for currently sounding voices. @type {Map<number, (time?: number) => void>} */
    this._voices = new Map();
    /** Notes whose key/pointer is physically held down. @type {Set<number>} */
    this._held = new Set();
    /** Fired when sample loading begins (e.g. to show a toast). @type {(() => void) | null} */
    this.onLoading = null;
    /** Fired once when samples finish loading. @type {(() => void) | null} */
    this.onLoaded = null;
  }

  /** Whether Web Audio is available in this browser. */
  static supported() {
    return (
      typeof window !== "undefined" &&
      !!(window.AudioContext || window.webkitAudioContext)
    );
  }

  /**
   * Create the AudioContext and begin downloading samples. Idempotent and safe
   * to call before any user gesture — the context starts suspended (decoding
   * still works) and is woken later by {@link resume}.
   * @returns {Promise<unknown>}
   */
  init() {
    if (this._loadPromise) return this._loadPromise;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) {
      this._loadPromise = Promise.reject(new Error("Web Audio unsupported"));
      return this._loadPromise;
    }
    this.context = new Ctx({ latencyHint: "interactive" });
    this.piano = SplendidGrandPiano(this.context, { volume: 110 });
    try {
      this.piano.output.addEffect("reverb", Reverb(this.context), 0.16);
    } catch {
      /* reverb is a nicety — ignore if the effect chain rejects it */
    }
    this.onLoading?.();
    this._loadPromise = this.piano.ready
      .then(() => {
        this.loaded = true;
        this.onLoaded?.();
      })
      .catch((err) => {
        console.warn("Piano samples failed to load:", err);
      });
    return this._loadPromise;
  }

  /**
   * Resume audio from within a user gesture (browsers require a gesture before
   * sound will play). Kicks off {@link init} if needed.
   * @returns {Promise<unknown> | null}
   */
  resume() {
    this.init();
    if (this.context && this.context.state === "suspended") {
      this.context.resume().catch(() => {});
    }
    return this._loadPromise;
  }

  /** @param {boolean} on */
  setEnabled(on) {
    this.enabled = on;
    if (!on) this.allOff();
  }

  /**
   * Strike a note.
   * @param {number} note MIDI note number
   * @param {number} [velocity] 0–127
   */
  noteOn(note, velocity = DEFAULT_VELOCITY) {
    if (!this.enabled || !this.loaded || !this.piano) return;
    this._held.add(note);
    // Damp any still-ringing voice for this note before re-striking it, so
    // trills/repeats reset the string the way a real damper would.
    this._stopVoice(note);
    this._voices.set(note, this.piano.start({ note, velocity }));
  }

  /**
   * Release a note. With the sustain pedal down the voice rings on until the
   * pedal lifts.
   * @param {number} note
   */
  noteOff(note) {
    this._held.delete(note);
    if (this.sustain) return;
    this._stopVoice(note);
  }

  /** @param {boolean} on */
  setSustain(on) {
    this.sustain = on;
    if (on) return;
    // Pedal up: damp every sounding note that isn't still physically held.
    for (const note of [...this._voices.keys()]) {
      if (!this._held.has(note)) this._stopVoice(note);
    }
  }

  /** Silence everything immediately (e.g. when a live MIDI session takes over). */
  allOff() {
    for (const note of [...this._voices.keys()]) this._stopVoice(note);
    this._held.clear();
    this.sustain = false;
    this.piano?.stop();
  }

  /** @param {number} note */
  _stopVoice(note) {
    const stop = this._voices.get(note);
    if (!stop) return;
    this._voices.delete(note);
    try {
      stop();
    } catch {
      /* voice already stopped/disposed */
    }
  }
}
