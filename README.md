# Steinway MIDI Piano (Blender)

A procedural **Steinway Model D** grand piano for Blender 5.x that you play **live**
from a MIDI keyboard (built for a **Yamaha P515**). Press a key on your piano and the
matching key moves in the Blender viewport in real time.

- Fully scripted model: an 88-key keyboard precisely mapped to MIDI notes 21–108,
  plus a recognizable, swappable Model D case.
- Live MIDI via `mido` + `python-rtmidi`, drained non-blocking each tick — no
  keyframes, low latency, `bpy` stays on the main thread.
- Packaged as a Blender **extension** with the native MIDI backend wheel bundled,
  so installing is one click on macOS arm64.

## Requirements

- Blender 4.2+ (developed on Blender 5.1, macOS 14 arm64).
- A class-compliant USB-MIDI keyboard (e.g. Yamaha P515) connected over USB.
- The bundled wheel is **macOS arm64 / CPython 3.13**. On other platforms, rebuild
  it with `scripts/build_wheel.sh` (needs a CPython 3.13 with dev headers).

> macOS Blender binary: `/Applications/Blender.app/Contents/MacOS/Blender`

## Install

1. Ensure the MIDI backend wheel exists (already built in this repo):
   ```bash
   bash scripts/build_wheel.sh
   ```
2. Package the extension with Blender's own builder (this puts `blender_manifest.toml`
   at the zip root, which the Extensions installer requires — a plain `zip` of the
   folder nests it one level down and will not install):
   ```bash
   /Applications/Blender.app/Contents/MacOS/Blender --command extension build \
     --source-dir extension/steinway_midi_piano --output-dir extension/
   ```
   This writes `extension/steinway_midi_piano-0.1.0.zip`.
3. In Blender: **Edit → Preferences → Get Extensions → ▾ → Install from Disk…**,
   pick `extension/steinway_midi_piano-0.1.0.zip`. Blender installs the bundled
   `python-rtmidi` wheel automatically. Enable **Steinway MIDI Piano**.

## Play

1. Open the **Steinway MIDI** tab in the 3D viewport sidebar (press `N`).
2. Click **Build Piano** to generate the model.
3. Plug in your P515, then set **Port** to your piano (shows as “P-515” / a digital
   piano / USB-MIDI device).
4. Click **Start** ▶ and play — keys move live. **Stop** (or `Esc`) ends and
   releases the port.
5. Tune the feel with **Press Angle** and **Smoothing**.

## How it works

| File | Role |
|---|---|
| `build/keyboard.py` | 88 keys as objects `Key.021…Key.108`, origins at the rear hinge, tagged with a `midi_note` property |
| `build/case.py` | procedural Model D body (own collection, swappable) |
| `build/_geom.py` | shared bmesh/material helpers |
| `midi.py` | `mido` wrapper; drains note on/off non-blocking via `iter_pending()` |
| `anim.py` | eases each pressed key toward `current * press_angle` about local +X |
| `operators.py` | modal operator + ~100 Hz timer gluing MIDI → key rotation |
| `props.py`, `panel.py` | the N-panel and its settings |

MIDI note-on with velocity 0 is treated as note-off; notes outside 21–108 are ignored.

## Headless / dev

```bash
B=/Applications/Blender.app/Contents/MacOS/Blender
$B --background --python scripts/generate_piano.py          # build + verify (88 keys)
$B --background --python scripts/generate_piano.py -- --save # also write assets/steinway_d.blend
$B --background --python scripts/selftest.py                 # animation self-test, no hardware
bash scripts/build_wheel.sh                                  # (re)build the python-rtmidi wheel
```

## Scope / roadmap

v1 is **keys-only** (clean press/release). Designed-in extension points for later:
velocity-driven motion/glow, sustain pedal (CC64), hammers & dampers action,
keyframe recording for rendered video, and swapping the procedural case for an
imported high-detail body.

## Troubleshooting

- **“MIDI backend missing”** — install the extension (it bundles the wheel), or use
  the panel’s *Install MIDI Backend* button. On non-macOS-arm64, rebuild the wheel.
- **No ports / piano not listed** — connect the piano first, then reopen the Port
  dropdown.
- **Keys don’t move** — click *Build Piano* first and make sure *Start* is active.
