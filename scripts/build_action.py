"""Headless double-escapement builder for the prepared playable .blend.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/build_action.py
    $B --background assets/steinway_grand_playable.blend --python scripts/build_action.py -- \
        --out assets/steinway_grand_playable.blend

Builds the full 88-note grand action (key arms, wippens, jacks, repetition
levers, hammers, rails) into the ``Steinway_Action`` collection, rigged with
drivers off each key's rotation (see ``steinway_midi_piano.build.action``).
Without ``--out`` it is a dry run: the file is opened, built, verified, and
nothing is written back.
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import action

    import bpy

    summary = action.build()

    print(f"[action] notes        : {summary['notes']}")
    print(f"[action] objects      : {summary['objects']}")
    print(f"[action] soundboard   : {summary['soundboard']}")
    print(f"[action] action line  : y = {summary['action_line'][0]} "
          f"+ {summary['action_line'][1]} * x")
    print(f"[action] strike z     : {summary['strike_z'][0]} .. {summary['strike_z'][1]}")
    print(f"[action] shank length : {summary['shank'][0]} .. {summary['shank'][1]}")
    print(f"[action] heel-capstan max err : {summary['heel_err']} m")
    print(f"[action] strike max err      : {summary['strike_err']} m")
    if summary["low_clearance_notes"]:
        print(f"[action] low-clearance notes : {summary['low_clearance_notes']}")

    assert summary["notes"] == 88, "expected an action for every key"
    assert summary["heel_err"] < 0.002, "wippen heel drifted off the capstan"
    assert summary["strike_err"] < 0.002, "hammer crown missed its strike height"

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        if not os.path.isabs(out):
            out = os.path.join(root, out)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[action] saved {out}")
    else:
        print("[action] dry run (no --out): nothing written")

    print("[action] OK")


main()
