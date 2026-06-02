"""Headless animation self-test - no MIDI hardware required.

    blender --background --python scripts/selftest.py

Builds the keyboard, then drives the same anim state machine the live operator
uses with synthetic note on/off events, asserting the right key tips down and
returns while its neighbour stays put.
"""

import math
import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import keyboard
    from steinway_midi_piano import anim

    keyboard.build()
    state = anim.LiveState(note_map=anim.build_note_map())
    assert len(state.note_map) == 88, f"note map has {len(state.note_map)} keys"
    assert 21 in state.note_map and 108 in state.note_map

    press_angle = math.radians(3.5)
    note = 60  # middle C

    anim.set_note(state, note, True)
    for _ in range(60):
        anim.ease_step(state, press_angle, 0.5)
    down = state.note_map[note].rotation_euler.x
    print(f"[selftest] pressed rotation.x = {down:.4f} (target {press_angle:.4f})")
    assert down > press_angle * 0.9, "pressed key did not tip down"
    assert abs(state.note_map[61].rotation_euler.x) < 1e-6, "neighbour key moved"

    anim.set_note(state, note, False)
    for _ in range(60):
        anim.ease_step(state, press_angle, 0.5)
    up = state.note_map[note].rotation_euler.x
    print(f"[selftest] released rotation.x = {up:.6f}")
    assert abs(up) < 1e-3, "released key did not return flat"

    # Sustain pedal: a released note stays down until the pedal lifts.
    anim.set_sustain(state, True)
    anim.set_note(state, 64, True)
    for _ in range(60):
        anim.ease_step(state, press_angle, 0.5)
    anim.set_note(state, 64, False)   # finger up, pedal still down
    for _ in range(60):
        anim.ease_step(state, press_angle, 0.5)
    held = state.note_map[64].rotation_euler.x
    print(f"[selftest] sustained rotation.x = {held:.4f}")
    assert held > press_angle * 0.9, "sustained key should stay down while pedal held"

    anim.set_sustain(state, False)
    for _ in range(60):
        anim.ease_step(state, press_angle, 0.5)
    assert abs(state.note_map[64].rotation_euler.x) < 1e-3, "key should lift when pedal releases"
    print("[selftest] sustain OK")

    print("[selftest] OK")


main()
