"""One-shot model completion: strings -> harp -> action -> case.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/build_all.py -- \
        --out assets/steinway_grand_playable.blend

Runs every builder in dependency order on a prepared playable .blend:

1. ``build/strings.py`` - full 88-course string set (+ re-seat decorative dampers)
2. ``build/harp.py``    - open the plate bays at the capo line, full pin set
3. ``build/action.py``  - double-escapement action + per-note damper action
4. ``build/case.py``    - nameboard, fallboard hinge, lid rig

Without ``--out`` it is a dry run (build + verify, nothing written).
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import strings, harp, action, case

    import bpy

    s = strings.build()
    print(f"[all] strings : {s['strings']} strings / {s['courses']} courses "
          f"(mono={s['mono']} bi={s['bi']} tri={s['tri']}), dampers {s['dampers']}")
    h = harp.build()
    print(f"[all] harp    : plate {h['plate']}, {h['tuning_pins']} tuning pins, "
          f"{h['hitch_pins']} hitch pins")
    a = action.build()
    print(f"[all] action  : {a['notes']} notes, {a['objects']} parts, "
          f"soundboard {a['soundboard']}, {a['dampers']} dampers")
    print(f"[all] action  : strike z {a['strike_z'][0]}..{a['strike_z'][1]}, "
          f"heel err {a['heel_err']}, strike err {a['strike_err']}, "
          f"damper err {a['damper_err']}")
    if a["low_clearance_notes"]:
        print(f"[all] action  : low clearance notes {a['low_clearance_notes']}")
    c = case.build()
    print(f"[all] case    : nameboard {c['nameboard']}, fallboard {c['fallboard']}, "
          f"lid {c['lid']}")

    assert s["strings"] >= 200 and s["courses"] == 88
    assert h["tuning_pins"] == s["strings"], "one tuning pin per string"
    assert a["notes"] == 88 and a["dampers"] >= 60
    assert a["heel_err"] < 0.002, "wippen heel drifted off the capstan"
    assert a["strike_err"] < 0.002, "hammer crown missed its strike height"
    assert a["damper_err"] < 0.002, "damper lift failed"

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
        if not os.path.isabs(out):
            out = os.path.join(root, out)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[all] saved {out}")
    else:
        print("[all] dry run (no --out): nothing written")
    print("[all] OK")


main()
