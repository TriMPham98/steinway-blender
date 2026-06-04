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

// Warm-grand voicing knobs (Bösendorfer-leaning, less bright/Yamaha). The
// SplendidGrandPiano samples are fairly bright, so we voice them darker:
// add weight, notch out the hammer-attack bite, roll off the top, and sit the
// piano in a darker, slightly longer room. Tweak these to taste — lower the
// `air`/`top` cuts for more sparkle, raise them for an even mellower tone.
const TONE = {
  bodyHz: 240, bodyDb: 3.5, //        low-shelf: low-end weight / warmth
  lowMidHz: 360, lowMidDb: 2.5, //    peak: woody body (keeps it warm, not thin)
  biteHz: 2400, biteDb: -6, //        peak cut: tame the percussive hammer attack
  airHz: 2800, airDb: -10.5, //       high-shelf: deep brightness rolloff
  topHz: 4300, //                     low-pass: ~as dark as it gets — sits just
  //                                  above C8's 4186 Hz fundamental so the top
  //                                  octave still speaks; lower = muffled.
  reverbWet: 0.38, //                 reverb send level (dry stays at unity)
  reverbBandwidth: 0.4, //            dark signal into the reverb
  reverbDamping: 0.84, //             dark reverb tail
  reverbDecay: 0.7, //                long, roomy tail
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
    // Bösendorfer than Yamaha (see TONE).
    const tone = buildWarmToneChain(this.context);
    tone.output.connect(this.context.destination);
    this.piano = SplendidGrandPiano(this.context, {
      volume: 110,
      destination: tone.input,
    });
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
 * @returns {{ input: GainNode, output: GainNode }}
 */
function buildWarmToneChain(ctx) {
  const input = ctx.createGain();
  const output = ctx.createGain();
  // A little headroom: the low-shelf adds weight, so back off to stay clear of
  // clipping on dense bass chords.
  output.gain.value = 0.9;

  const body = ctx.createBiquadFilter();
  body.type = "lowshelf";
  body.frequency.value = TONE.bodyHz;
  body.gain.value = TONE.bodyDb;

  const lowMid = ctx.createBiquadFilter();
  lowMid.type = "peaking";
  lowMid.frequency.value = TONE.lowMidHz;
  lowMid.Q.value = 0.9;
  lowMid.gain.value = TONE.lowMidDb;

  const bite = ctx.createBiquadFilter();
  bite.type = "peaking";
  bite.frequency.value = TONE.biteHz;
  bite.Q.value = 1.1;
  bite.gain.value = TONE.biteDb;

  const air = ctx.createBiquadFilter();
  air.type = "highshelf";
  air.frequency.value = TONE.airHz;
  air.gain.value = TONE.airDb;

  const top = ctx.createBiquadFilter();
  top.type = "lowpass";
  top.frequency.value = TONE.topHz;
  top.Q.value = 0.5;

  // Dry path: input → EQ → output.
  input.connect(body);
  body.connect(lowMid);
  lowMid.connect(bite);
  bite.connect(air);
  air.connect(top);
  top.connect(output);

  // Warm room: a darker, slightly longer reverb tail mixed in behind the dry
  // signal. Wired once the reverb reports ready (it may spin up a worklet).
  try {
    const reverb = Reverb(ctx);
    const wet = ctx.createGain();
    wet.gain.value = TONE.reverbWet;
    wet.connect(output);
    const wire = () => {
      setReverbParam(reverb, "bandwidth", TONE.reverbBandwidth);
      setReverbParam(reverb, "damping", TONE.reverbDamping);
      setReverbParam(reverb, "decay", TONE.reverbDecay);
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

  return { input, output };
}

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
