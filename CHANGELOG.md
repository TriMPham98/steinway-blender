# Changelog

All notable changes to **Steinway MIDI Piano** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The version here tracks `version` in
`extension/steinway_midi_piano/blender_manifest.toml`.

## [0.5.0] - 2026-06-10

### Added
- **Double-escapement (repetition) action.** `build/action.py` measures the model
  (per-note string fronts, damper fronts, overhead clearance via BVH raycasts),
  fits the diagonal action line, and builds the full 88-note grand action behind
  the fallboard: hidden seesaw **key arms** (brass capstan + leather backcheck),
  **wippens** on a support rail, L-shaped **jacks** whose toes ride felted
  **let-off buttons**, slotted **repetition levers** (knuckle saddle, button
  window, brass spring) stopped by **drop screws**, and felt-and-walnut
  **hammers** with leather knuckles on a shank rail. Everything is rigged with
  drivers off each key's `rotation_euler.x` using Blender's trusted
  simple-expression subset (no script auto-run needed), with physically
  consistent gains: the heel rides the capstan, the toe pins on the button so the
  jack escapes near full press, the drop screw checks the lever, and the falling
  knuckle lands back on the saddle — the double escapement. New **Build Double
  Escapement** panel button, plus `scripts/build_action.py` for headless builds
  (`--out` saves; dry run verifies contact errors < 2 mm and prints a summary).
- **Live hammer strikes.** `anim.py` now drives a per-key `Key["hammer"]`
  impulse the hammer drivers read: when a struck key sweeps past 55% depth the
  hammer flies to its per-note strike height (raycast just under the plate web /
  string band) and decays back to the check over ~45 ms. Keys without the
  channel are skipped, so plain models behave as before.
- The model's imported soundboard slab extended under the strike zone where a
  real piano has the action gap; the builder cuts its front edge back along the
  action line (hidden under the Music Shelf, marked idempotent, and the playable
  .blend stays fully regenerable from the source model).

### Changed
- `scripts/export_glb.py` strips the (case-hidden) action parts from the web GLB
  by default — they would add ~440 draw calls for nothing; pass `--with-action`
  to keep them as separate rest-pose nodes (they are excluded from the static
  join either way).

## [0.4.2] - 2026-06-01

### Changed
- **Snappier key release.** The return-to-rest now uses a separate, stiffer,
  lightly under-damped spring (`Feel.release_stiffness`, scaled by Snappiness), so
  keys pop back up in ~90 ms instead of floating (~260 ms); the velocity-carried
  attack is unchanged.
- The Prepare step now also **renames the imported `BABY GRAN PIANO` collection to
  `STEINWAY GRAND PIANO`** (`retarget.rename_piano_collection`; idempotent no-op
  otherwise), and **parks the 3D cursor at the world origin** (the model had left
  it floating up by the logo).

## [0.4.1] - 2026-06-01

### Changed
- The Prepare step now **vertically centers the Steinway & Sons logo/wordmark on
  the fallboard** (`retarget.center_logo`, folded into `prepare()`): it was sitting
  ~33 mm high. Computed from geometry, idempotent, and a no-op on models without
  that logo collection.

## [0.4.0] - 2026-06-01

### Added
- **Velocity-sensitive key motion.** Each key is now a per-key **spring-damper**
  driven by MIDI note velocity: hard strikes snap down fast, soft notes ease in,
  with a **crisp key-bed bottom-out** (hard clamp at full depth) and a smooth,
  near-critically-damped float-back on release. Depth is fixed (speed-only
  dynamics) — every note still travels the full `press_angle`. `midi.drain` now
  carries velocity (`('note', note, velocity)`), and the live operator integrates
  with real frame `dt` (`time.perf_counter`, clamped + sub-stepped for stability).

### Changed
- Panel knobs: **Press Angle** kept; **Smoothing** replaced by **Snappiness**
  (spring stiffness → descent/return speed) and **Velocity Sensitivity** (how much
  dynamics affect motion; 0 = uniform). The sustain pedal now eases via an internal
  dt-rate.
- `anim.set_note` takes a `velocity:int` (0 = release) instead of a `pressed:bool`.

## [0.3.1] - 2026-06-01

### Changed
- Sustain pedal (CC64) now **only tips the pedal object** — it no longer holds keys
  down. A key follows the fingers (note on/off) alone; true damper hold will return
  with the planned hammer/damper action. `anim.LiveState` simplified accordingly
  (dropped the `sustained` / `sustain_on` state).

## [0.3.0] - 2026-06-01

Pivot from a fully procedural model to driving an **imported, high-detail Steinway
grand** (`SteinwayGrandPiano.blend`). The imported model ships its keys as two
joined meshes, so the live MIDI → key-rotation pipeline is now fed by a one-time
**split-and-tag** step instead of procedural geometry.

### Added
- `build/retarget.py` — splits the imported `White Keys` (52) and `Black Keys`
  (36) meshes into 88 individually-pivotable `Key.NNN` objects: connected
  components via union-find, stray fragments dropped, each origin placed at the
  **rear hinge edge**, tagged with `midi_note` / `key_color`, with bass→treble
  orientation auto-detected from the white/black interleave.
- **Prepare Imported Keys** operator (`steinway.prepare`) + N-panel button and a
  "Keys ready" indicator that replaces the old build button.
- **Sustain-pedal tilt** — CC64 now visibly tips the `Right Sustain Pedal` object
  down while held (in addition to holding keys), via `anim.PEDAL_ANGLE`,
  `anim.find_pedal`, and the pedal fields on `LiveState`.
- `scripts/prepare_model.py` — headless bake that splits/tags an imported model,
  asserts the 88-key mapping (52/36, MIDI 21..108, pedal tagged), and with
  `--out` writes a ready-to-play `.blend` (the source is opened read-only).

### Changed
- `scripts/selftest.py` is now hermetic: it builds tiny synthetic meshes to test
  the splitter and the anim/sustain/pedal path, needing neither MIDI hardware nor
  the 103 MB model.
- README rewritten for the imported-model workflow (open model → Prepare Imported
  Keys → Start); `build/_geom.py` trimmed to the collection helpers `retarget`
  reuses.

### Removed
- The procedural geometry path: `build/keyboard.py`, `build/case.py`,
  `scripts/generate_piano.py`, the `steinway.build` "Build Piano" operator, and
  the procedural mesh/material helpers in `build/_geom.py`.

### Migration
- Open `SteinwayGrandPiano.blend` (or a file baked by `prepare_model.py`), open
  the **Steinway MIDI** sidebar tab, click **Prepare Imported Keys**, then
  **Start**. The large source/derived `.blend` files live under `assets/` and are
  git-ignored.

## [0.2.0] - 2026-05-31

### Added
- Sustain pedal (CC64) support: a released note stays down while the damper pedal
  is held and lifts when the pedal releases (`anim.set_sustain`, CC64 handling in
  `midi.drain`).

## [0.1.0] - 2026-05-31

### Added
- Initial release: a procedural **Steinway Model D** with 88 keys
  (`Key.021…Key.108`) precisely mapped to MIDI notes 21–108 plus a swappable
  case; live MIDI input via `mido` + a bundled `python-rtmidi` wheel; a modal
  operator driving key rotation at ~100 Hz on the main thread; an N-panel with
  **Press Angle** / **Smoothing**; packaged as a one-click Blender extension for
  macOS arm64.

[0.4.2]: #042---2026-06-01
[0.4.1]: #041---2026-06-01
[0.4.0]: #040---2026-06-01
[0.3.1]: #031---2026-06-01
[0.3.0]: #030---2026-06-01
[0.2.0]: #020---2026-05-31
[0.1.0]: #010---2026-05-31
