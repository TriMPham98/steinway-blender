"""Headless retarget / verifier for an imported grand-piano .blend.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/SteinwayGrandPiano.blend --python scripts/prepare_model.py
    $B --background assets/SteinwayGrandPiano.blend --python scripts/prepare_model.py -- \
        --out assets/steinway_grand_playable.blend

Splits the model's joined ``White Keys`` / ``Black Keys`` meshes into 88
MIDI-mapped key objects, re-origins + tags the sustain pedal, asserts the mapping
is correct (88 keys, 52 white / 36 black, MIDI 21..108, pedal tagged), and with
``--out`` saves the derived, ready-to-play .blend. The source file passed to
Blender is opened read-only and never written back.
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import retarget
    from steinway_midi_piano import anim

    import bpy

    summary = retarget.prepare()

    keys = [o for o in bpy.data.objects if o.get("midi_note") is not None]
    notes = sorted(int(o["midi_note"]) for o in keys)
    whites = sum(1 for o in keys if o.get("key_color") == "white")
    blacks = sum(1 for o in keys if o.get("key_color") == "black")
    pedal = anim.find_pedal()

    print(f"[prepare] status     : {summary['status']}")
    print(f"[prepare] key objects: {len(keys)} (white={whites}, black={blacks})")
    print(f"[prepare] note range : {notes[0]}..{notes[-1]}")
    print(f"[prepare] reversed   : {summary.get('reversed')}")
    print(f"[prepare] pedal      : {pedal.name if pedal else None}")
    print(f"[prepare] logo dz    : {summary.get('logo_dz')}")
    print(f"[prepare] collection : {summary.get('collection')}")

    assert len(keys) == 88, f"expected 88 keys, got {len(keys)}"
    assert whites == 52, f"expected 52 white keys, got {whites}"
    assert blacks == 36, f"expected 36 black keys, got {blacks}"
    assert notes == list(range(21, 109)), "keys must map contiguously to MIDI 21..108"
    assert pedal is not None, "sustain pedal not found / tagged"

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        if not os.path.isabs(out):
            out = os.path.join(root, out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[prepare] saved {out}")

    print("[prepare] OK")


main()
