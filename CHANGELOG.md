# Changelog

All notable changes to **Steinway MIDI Piano** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The version here tracks `version` in
`extension/steinway_midi_piano/blender_manifest.toml`.

## [0.7.6] - 2026-06-15

### Fixed
- **Action dampers use the imported shape on the fitted row.** Each
  ``Damper.NNN`` now clones the nearest decorative unit mesh (the model's own
  top + felt geometry) but seats it on the action-line position with plate
  clearance and lift drivers - not the old box primitives or a second static
  copy welded into ``Piano_Static``.
- **Web damper lift uses the vertical axis.** Sustain pedal and key travel now
  raise dampers on glTF ``position.y`` (Blender ``location.z``), not
  ``position.z`` — which had been sliding them back and forth along the piano.

## [0.7.5] - 2026-06-15

### Fixed
- **No more double dampers on the web viewer.** The imported decorative
  ``Dampers Tops``/``Bottoms`` stand-ins are now tagged ``steinway_replaced``
  once the per-note action dampers are built, so ``--with-action`` exports only
  the action heads (not the old rectangles welded into ``Piano_Static``).

## [0.7.4] - 2026-06-15

### Added
- **Web viewer ships the full action + fixed pin field.** Export with
  `--with-action` keeps hammers, wippens, jacks, dampers, strings, and tuning
  pins in `steinway.glb`; the web app now drives the same driver math as Blender
  (key arms, escapement, hammer strike impulse, damper lift on key/pedal).

## [0.7.3] - 2026-06-15

### Fixed
- **Six tuning pins no longer float above the pin field.** The damper-lip slab
  no longer cantilevers over the pin ranks (plate cut v4), and the per-pin
  surface probe peels through any remaining overlay by dropping straight below
  each spot instead of drifting on sloped hits. Before, six treble pins sat on
  the slab underside ~0.91 with no web below, ~37-39 mm above their neighbors.

## [0.7.2] - 2026-06-11

### Fixed
- **Tuning pins form a real Steinway pin field.** Pins now stand on four
  straight ranks parallel to the strike line (25 mm pitch, 30-105 mm in front
  of it), with the rank cycling pin-to-pin in spatial order - the classic
  diagonal lattice. Before, each pin sat a per-string distance from its
  course's (ragged) front end, and a "slide along the string until the spot
  reads flat" search pushed unlucky pins up to 64 mm out of line - the
  wandering pins. The search is gone: rank assignment is deterministic
  (same-rank neighbors stay >= 13 mm apart center-to-center for 6.4 mm pins),
  and the few spots over a raised plate bar simply stand on the bar, which
  the per-pin surface probe from 0.7.1 already handles.

## [0.7.1] - 2026-06-11

### Fixed
- **Tuning pins no longer clip the plate.** The plate is a closed ~28 mm slab:
  its visible top surface sits at z ≈ 0.872-0.878, not the 0.850 underside
  sheet the pins were seated on (burying them). Each pin now stands on its
  probed local surface, and the pin-stagger search (in `strings.course_lines`)
  slides along the string until the spot reads as flat field - pins that can't
  find flat field stand *on* the raised bar instead of inside it.
- **Damper heads no longer clip the plate bars, and the row is even.** The
  clearance test now only counts plate geometry passing *through* the head's
  z-range (the gold top skin below the felts was a false positive that made
  the dodge shuffle heads pointlessly - the unevenness). Head depths taper
  like a real grand's (45 mm bass -> 28 mm treble), which also lets the treble
  heads fit between the hammer line and the bays' rear border bar; the dodge
  is footprint-aware, never slides into the hammer's strike zone, and the
  builder reports any residual contact (currently none).

## [0.7.0] - 2026-06-11

### Added
- **Real strikes on real strings.** `build/harp.py` opens the plate's bays: the
  imported `Brass_Sound_Works.002` modeled its front section as one solid n-gon
  reaching under the whole strike and damper bands; it is now bisected along
  the capo line (just in front of the strike line) so hammers fly through open
  air to the strings, exactly like the real plate. The hammer stack rose back
  to full height (~45 mm blow) and the strike line moved to a true ~1/8
  speaking-length setback instead of hugging the string fronts (the "backwards
  hammers" look). Per-note let-off still stops just short of each string.
- **Per-note damper action with sustain.** Notes 21-88 get a damper head riding
  its own course (felt seated on the strings, dodging plate struts along the
  course), a wire cranked back over the shanks and down behind the hammershank
  rail, and (notes 21-81) an underlever lifted by the key arm's tail - the
  treble bridge sits too close for the wire slot above that, so the top heads
  ride stub wires. A pressed key lifts its damper from ~40% travel; the
  **sustain pedal (CC64) lifts them all** plus the lift tray, with no animator
  changes (drivers read the pedal's rotation). The 51 decorative damper units
  stay hidden for the web export.
- **Full pin set.** One tuning pin per string (225, staggered rows, with every
  string's front extended to its pin) and one hitch pin per course (88);
  the old 51-string pin field is hidden and tagged replaced.
- **Functional case.** `build/case.py` adds the missing **nameboard** behind
  the fallboard, re-origins the **fallboard** onto its hinge, and rigs the
  **lid** (spine hinge + front-flap fold empties). Controls are scene
  properties (`fallboard_open`, `lid_open`, `lid_flap_fold`) - scene-level
  because self-prop drivers are dependency cycles that evaluate
  nondeterministically. `scripts/build_all.py` runs everything in order.

### Changed
- Even rows: hammers and dampers sit exactly on the fitted action line
  (per-note measurement jitter no longer staggers them), key-arm slabs fill
  the keybed to neighbor midpoints with 0.5 mm kerfs, and every arm tail ends
  on one line.
- The deeper soundboard slot for the damper wires is an L-shaped carve
  (versioned `steinway_action_cut = 2`), bounded at x = 0.428 where the treble
  bridge approaches.
- Builders no longer rely on `matrix_world` of hidden stand-ins (it reads as
  identity for depsgraph-excluded objects on a fresh load) and hide retired
  meshes with the eye flag instead of the viewport-disable flag.

## [0.6.0] - 2026-06-10

### Added
- **Full 88-course string set.** The imported model carried only 51 identical
  ~3.2 mm copper stand-in strings (one per decorative damper). `build/strings.py`
  replaces them with a complete scale that follows the model's own fan (each new
  course interpolates the originals' pin-end/hitch-end geometry, so it lands on
  the same pin field and hitch line): 10 wound copper monochords (A0–F#1),
  19 wound bichords up to the model's physical section break at C#3, and 59
  plain-steel trichords above it — 225 strings, every course anchored at its
  key's x on the strike line so each hammer sits under its own unisons.
  Dimensionally the piano measures 1.77 m × 1.50 m — a **Steinway Model O**
  ("Living Room Grand", 5′10¾″) footprint — and is strung accordingly.
  Headless: `scripts/build_strings.py` (`--out` saves; dry run verifies).
- **Damper re-seating.** The 51 decorative damper units (clustered from the
  joined `Dampers Tops`/`Bottoms` meshes) are snapped sideways onto their
  nearest new course and dropped/raised so the felt grazes the actual string
  top — seating on the *highest* course under the footprint so nothing sinks
  through the upper layer at the overstrung crossing.

### Changed
- The 51 stand-in strings stay in the .blend (hidden, tagged
  `steinway_replaced`) as the measurement source of truth;
  `scripts/export_glb.py` strips tagged stand-ins so only `Strings_Full`
  reaches the web GLB (where it joins `Piano_Static` as usual).
- The action builder's strike-height raycast now also includes `Strings_Full`
  when present.

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
