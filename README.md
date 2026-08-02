# Steinway MIDI Piano (Blender)

Play an **imported, high-detail Steinway grand** in Blender 5.x that you drive
**live** from a MIDI keyboard (built for a **Yamaha P515**). Press a key on your
piano and the matching key moves in the Blender viewport in real time — snapping
down faster the harder you strike — and the sustain pedal tips when you hold CC64.

- Drives a real, swappable model (`SteinwayGrandPiano.blend`): a one-time
  **Prepare** step splits its joined key meshes into 88 objects precisely mapped
  to MIDI notes 21–108, each pivoting at its rear hinge.
- A one-time **Build Double Escapement** step adds the full 88-note grand action
  behind the fallboard — wippens, jacks, repetition levers, drop screws, and felt
  hammers — driver-rigged to the keys, so hammers fly at the strings when you
  play (visible with the case/music shelf hidden or a camera inside).
- Live MIDI via `mido` + `python-rtmidi`, drained non-blocking each tick — no
  keyframes, low latency, `bpy` stays on the main thread.
- Packaged as a Blender **extension** with the native MIDI backend wheel bundled,
  so installing is one click on macOS arm64.

## Requirements

- Blender 4.2+ (developed on Blender 5.1, macOS 14 arm64).
- An imported grand-piano `.blend` whose keys are two joined meshes named
  `White Keys` (52 keys) and `Black Keys` (36 keys) — e.g. the
  `SteinwayGrandPiano.blend` this add-on was built against. A separate
  `Right Sustain Pedal` mesh is optional (enables the pedal tilt).
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
   This writes `extension/steinway_midi_piano-0.4.2.zip`.
3. In Blender: **Edit → Preferences → Get Extensions → ▾ → Install from Disk…**,
   pick that zip. Blender installs the bundled `python-rtmidi` wheel automatically.
   Enable **Steinway MIDI Piano**.

## Play

1. Open your Steinway model (`SteinwayGrandPiano.blend`, or a file already baked by
   `scripts/prepare_model.py`).
2. Open the **Steinway MIDI** tab in the 3D viewport sidebar (press `N`).
3. Click **Prepare Imported Keys** — this splits the joined key meshes into 88
   MIDI-mapped keys and tags the sustain pedal. (An already-prepared file shows
   *Keys ready* and skips this.)
   Then (optional) click **Build Double Escapement** to add the 88-note hammer
   action inside the case — once built the panel shows *Action ready*. Hide the
   `Music Shelf` (or put a camera in the cavity) to watch it work.
4. Plug in your P515, then set **Port** to your piano (shows as “P-515” / a digital
   piano / USB-MIDI device).
5. Click **Start** ▶ and play — keys move live and the pedal tips when you hold
   sustain. **Stop** (or `Esc`) ends and releases the port.
6. Tune the feel with **Press Angle** (depth), **Snappiness** (key speed), and
   **Velocity Sensitivity** (how much dynamics affect the motion).

## How it works

| File | Role |
|---|---|
| `build/retarget.py` | splits the imported `White Keys`/`Black Keys` meshes into 88 objects `Key.021…Key.108` (origins at the rear hinge, tagged `midi_note`/`key_color`); re-origins + tags `Right Sustain Pedal`; centers the logo + tidies collection names |
| `build/action.py` | builds the 88-note **double-escapement action** (`Steinway_Action` collection): measures string/damper fronts per note, fits the action line, cuts the soundboard's belly-rail gap, and rigs key arms → wippens → jacks/repetition levers → hammers with simple-expression drivers off each key's rotation (plus a `Key["hammer"]` strike channel) |
| `build/strings.py` | replaces the model's 51 stand-in strings with the **full 88-course set** (`Strings_Full`: wound mono/bichords + steel trichords on the model's own fan — a Steinway Model O footprint) and re-seats the decorative damper units on the new courses |
| `build/harp.py` | opens the plate's **bays** at the capo line (the imported plate was solid under the strike band) and fits **one tuning pin per string** + per-course hitch pins |
| `build/case.py` | adds the missing **nameboard**, hinges the **fallboard**, and rigs the **lid** (spine + front-flap fold); controls: scene props `fallboard_open` / `lid_open` / `lid_flap_fold` |
| `build/_geom.py` | collection helpers used by the retarget step |
| `midi.py` | `mido` wrapper; drains note on/off + CC64 non-blocking via `iter_pending()` |
| `anim.py` | per-key velocity-driven spring-damper about local +X (hard strikes snap down fast, crisp key-bed bottom-out, snappy release); fires the hammer strike impulse as a struck key sweeps down; tips the tagged pedal on sustain |
| `operators.py` | Prepare operator + modal operator + ~100 Hz timer gluing MIDI → key/pedal rotation |
| `props.py`, `panel.py` | the N-panel and its settings |

Note-on **velocity** sets how fast the key snaps down (every note still travels
the full depth); velocity 0 is treated as note-off; notes outside 21–108 are
ignored. CC64 ≥ 64 tips the sustain pedal; keys follow your fingers only (the
pedal does not hold keys down yet — damper/hammer action is planned).

## Headless / dev

```bash
B=/Applications/Blender.app/Contents/MacOS/Blender
# split + verify an imported model (88 keys, 52/36, MIDI 21..108, pedal tagged):
$B --background assets/SteinwayGrandPiano.blend --python scripts/prepare_model.py
# also bake a ready-to-play file (the source is opened read-only):
$B --background assets/SteinwayGrandPiano.blend --python scripts/prepare_model.py -- \
   --out assets/steinway_grand_playable.blend
# complete the model in one shot (strings -> harp/pins -> action+dampers -> case):
$B --background assets/steinway_grand_playable.blend --python scripts/build_all.py -- \
   --out assets/steinway_grand_playable.blend
# (scripts/build_strings.py and scripts/build_action.py run individual steps)
# hermetic splitter + anim self-test, no hardware or model needed:
$B --background --python scripts/selftest.py
bash scripts/build_wheel.sh                                  # (re)build the python-rtmidi wheel
```

> `assets/*.blend` is git-ignored — the ~103 MB source model and the baked playable
> file stay local and are never committed.

## Scope / roadmap

v0.7 drives **velocity-sensitive keys, the full double-escapement hammer
action, and the damper action**: keys follow your fingers with a spring-damper
whose attack speed tracks how hard you play; each key's
wippen/jack/repetition-lever/hammer train follows it kinematically — hammers
fly through the opened plate bays to the strings, drop to the check, the jack
escapes at let-off — and each key lifts its own damper, with **CC64 lifting
them all** (sustain you can see). Still planned: velocity-driven glow and
keyframe recording for rendered video.

## Troubleshooting

- **“MIDI backend missing”** — install the extension (it bundles the wheel), or use
  the panel’s *Install MIDI Backend* button. On non-macOS-arm64, rebuild the wheel.
- **No ports / piano not listed** — connect the piano first, then reopen the Port
  dropdown.
- **“Joined key meshes not found”** — open a model that has `White Keys` and
  `Black Keys` meshes before clicking *Prepare Imported Keys*.
- **Keys don’t move** — click *Prepare Imported Keys* first and make sure *Start* is
  active.
- **Bass/treble reversed** — `retarget.split_keys` auto-detects orientation from the
  white/black pattern; if a non-standard model trips the check, the error says so.
