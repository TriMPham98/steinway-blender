"""Find tuning pins whose cylinders clip into raised plate struts.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/inspect_pin_clip.py

Uses the same clearance rules as ``strings._nudge_pin_off_struts`` so a green
result means rebuild + pin placement will leave no pin shaft in the brass.
"""

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "extension"))

from steinway_midi_piano.build import strings

NEED = strings.PIN_R + strings.PIN_CLEAR_MARGIN


def main():
    # Rebuild course geometry (applies plate cut + strut nudges).
    courses = strings.course_lines()
    bvh = strings._plate_bvh()
    if bvh is None:
        raise SystemExit("plate missing")

    clips = []
    for c in courses:
        d = c["R"] - c["F"]
        from mathutils import Vector
        dirxy = Vector((d.x, d.y, 0.0)).normalized()
        for k, (F_k, _R_k) in enumerate(c["unisons"]):
            cyl = F_k - dirxy * strings.PIN_R
            cl, _n = strings._pin_side_clear(bvh, cyl.x, cyl.y)
            on_web = strings._pin_footprint_on_web(bvh, cyl.x, cyl.y)
            if cl < NEED or not on_web:
                clips.append({
                    "note": c["note"],
                    "k": k,
                    "x": round(cyl.x, 4),
                    "y": round(cyl.y, 4),
                    "clear_mm": round(cl * 1000, 2),
                    "on_web": on_web,
                })

    print(f"clipping pins: {len(clips)} / 225")
    for r in clips:
        print(
            f"  note {r['note']:3d} u{r['k']} ({r['x']},{r['y']}) "
            f"clear={r['clear_mm']}mm on_web={r['on_web']}"
        )
    if clips:
        raise SystemExit(1)
    print("[inspect_pin_clip] OK")


main()
