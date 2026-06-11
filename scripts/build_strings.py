"""Headless full-string-set builder for the prepared playable .blend.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/build_strings.py
    $B --background assets/steinway_grand_playable.blend --python scripts/build_strings.py -- \
        --out assets/steinway_grand_playable.blend

Replaces the model's 51 stand-in strings with the full 88-course set
(``Strings_Full``: wound mono/bichords + steel trichords following the model's
own fan; see ``steinway_midi_piano.build.strings``) and re-seats the decorative
damper units on the new courses. Without ``--out`` it is a dry run.
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import strings

    import bpy

    summary = strings.build()

    print(f"[strings] courses      : {summary['courses']}")
    print(f"[strings] strings      : {summary['strings']} "
          f"(mono={summary['mono']} bi={summary['bi']} tri={summary['tri']})")
    print(f"[strings] fan samples  : bass={summary['bass_fan']} main={summary['main_fan']}")
    print(f"[strings] dampers      : {summary['dampers']}")

    assert summary["courses"] == 88, "expected a course for every note"
    assert summary["strings"] >= 200, "a full set should have 200+ strings"
    assert summary["dampers"] and summary["dampers"]["units"] >= 50, "damper re-seat failed"

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        if not os.path.isabs(out):
            out = os.path.join(root, out)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[strings] saved {out}")
    else:
        print("[strings] dry run (no --out): nothing written")

    print("[strings] OK")


main()
