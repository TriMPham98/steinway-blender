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

/**
 * Damper release time (seconds) for smplr's ampRelease / decayTime.
 * Short felt-damper seat with a little body ring after key-up — long enough
 * to avoid a hard cut, short enough that released notes don't wash together.
 */
const DAMPER_RELEASE_SEC = 0.425;

// Warm-grand voicing knobs (Bösendorfer-leaning, less bright/Yamaha). The
// SplendidGrandPiano samples are fairly bright, so we voice them darker:
// add weight, notch out the hammer-attack bite, roll off the top, and sit the
// piano in a darker, slightly longer room. Tweak these to taste — lower the
// `air`/`top` cuts for more sparkle, raise them for an even mellower tone.
export const TONE_DEFAULTS = {
  bodyHz: 240,
  bodyDb: 3.5,
  lowMidHz: 360,
  lowMidDb: 2.5,
  biteHz: 2400,
  biteDb: -6,
  airHz: 2800,
  airDb: -10.5,
  topHz: 3000,
  reverbWet: 0.12,
  reverbBandwidth: 0.4,
  reverbDamping: 0.84,
  reverbDecay: 0.7,
  outputGain: 0.9,
};

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
    /** Live tone/EQ/reverb params (see {@link TONE_DEFAULTS}). */
    this.tone = { ...TONE_DEFAULTS };
    /** smplr instrument volume (0–127). */
    this.sampleVolume = 110;
    /** @type {ToneChain | null} */
    this._toneChain = null;
  }

  /** Push {@link tone} and {@link sampleVolume} to the active audio graph. */
  applyTone() {
    const chain = this._toneChain;
    if (!chain) return;
    const t = this.tone;
    chain.body.frequency.value = t.bodyHz;
    chain.body.gain.value = t.bodyDb;
    chain.lowMid.frequency.value = t.lowMidHz;
    chain.lowMid.gain.value = t.lowMidDb;
    chain.bite.frequency.value = t.biteHz;
    chain.bite.gain.value = t.biteDb;
    chain.air.frequency.value = t.airHz;
    chain.air.gain.value = t.airDb;
    chain.top.frequency.value = t.topHz;
    chain.output.gain.value = t.outputGain;
    chain.wet.gain.value = t.reverbWet;
    if (chain.reverb) {
      setReverbParam(chain.reverb, "bandwidth", t.reverbBandwidth);
      setReverbParam(chain.reverb, "damping", t.reverbDamping);
      setReverbParam(chain.reverb, "decay", t.reverbDecay);
    }
    if (this.piano) this.piano.volume = this.sampleVolume;
  }

  /** Restore shipped defaults and apply them. */
  resetTone() {
    this.tone = { ...TONE_DEFAULTS };
    this.sampleVolume = 110;
    this.applyTone();
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
    // Route the bright sampled grand through a warm tone chain so it reads more
    // Bösendorfer than Yamaha (see TONE_DEFAULTS).
    this._toneChain = buildWarmToneChain(this.context, this.tone);
    this._toneChain.output.connect(this.context.destination);
    this.piano = SplendidGrandPiano(this.context, {
      volume: this.sampleVolume,
      destination: this._toneChain.input,
      // Maps to ampRelease: key-up / damper-down fade (not sustain-pedal hold).
      decayTime: DAMPER_RELEASE_SEC,
    });
    this.applyTone();
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

/**
 * Build the warm "Viennese-grand" tone chain (see {@link TONE}): a body/low-mid
 * lift, a notch off the hammer-attack bite, a rolled-off top, and a darker room
 * reverb mixed in behind the dry signal. The piano feeds `input`; `output` goes
 * on to the speakers.
 * @param {AudioContext} ctx
 * @param {typeof TONE_DEFAULTS} tone
 * @returns {ToneChain}
 */
function buildWarmToneChain(ctx, tone) {
  const input = ctx.createGain();
  const output = ctx.createGain();
  output.gain.value = tone.outputGain;

  const body = ctx.createBiquadFilter();
  body.type = "lowshelf";
  body.frequency.value = tone.bodyHz;
  body.gain.value = tone.bodyDb;

  const lowMid = ctx.createBiquadFilter();
  lowMid.type = "peaking";
  lowMid.frequency.value = tone.lowMidHz;
  lowMid.Q.value = 0.9;
  lowMid.gain.value = tone.lowMidDb;

  const bite = ctx.createBiquadFilter();
  bite.type = "peaking";
  bite.frequency.value = tone.biteHz;
  bite.Q.value = 1.1;
  bite.gain.value = tone.biteDb;

  const air = ctx.createBiquadFilter();
  air.type = "highshelf";
  air.frequency.value = tone.airHz;
  air.gain.value = tone.airDb;

  const top = ctx.createBiquadFilter();
  top.type = "lowpass";
  top.frequency.value = tone.topHz;
  top.Q.value = 0.5;

  // Dry path: input → EQ → output.
  input.connect(body);
  body.connect(lowMid);
  lowMid.connect(bite);
  bite.connect(air);
  air.connect(top);
  top.connect(output);

  const wet = ctx.createGain();
  wet.gain.value = tone.reverbWet;
  wet.connect(output);

  let reverb = null;
  try {
    reverb = Reverb(ctx);
    const wire = () => {
      setReverbParam(reverb, "bandwidth", tone.reverbBandwidth);
      setReverbParam(reverb, "damping", tone.reverbDamping);
      setReverbParam(reverb, "decay", tone.reverbDecay);
      top.connect(reverb.input);
      reverb.connect(wet);
    };
    if (typeof reverb.ready === "function") {
      reverb.ready().then(wire).catch(() => {});
    } else {
      wire();
    }
  } catch {
    /* reverb optional — the dry warm chain still sounds */
  }

  return { input, output, body, lowMid, bite, air, top, wet, reverb };
}

/**
 * @typedef {typeof TONE_DEFAULTS} ToneParams
 * @typedef {{
 *   input: GainNode,
 *   output: GainNode,
 *   body: BiquadFilterNode,
 *   lowMid: BiquadFilterNode,
 *   bite: BiquadFilterNode,
 *   air: BiquadFilterNode,
 *   top: BiquadFilterNode,
 *   wet: GainNode,
 *   reverb: { getParam?: (name: string) => AudioParam | undefined, input?: AudioNode } | null,
 * }} ToneChain
 */

/**
 * Set one smplr-Reverb parameter by name, if present.
 * @param {{ getParam?: (name: string) => AudioParam | undefined }} reverb
 * @param {string} name
 * @param {number} value
 */
function setReverbParam(reverb, name, value) {
  const param = reverb.getParam?.(name);
  if (param) param.value = value;
}
