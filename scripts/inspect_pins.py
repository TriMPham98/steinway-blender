"""Find tuning pins floating above the plate pin field.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/inspect_pins.py
"""

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "extension"))

import bpy
from mathutils import Vector

from steinway_midi_piano.build import action as action_mod
from steinway_midi_piano.build import strings, harp

WEB_Z = harp.WEB_Z


def _pin_surface(bvh, px, py):
    """Mirror harp._make_pins surface probe."""
    down = Vector((0.0, 0.0, -1.0))
    if bvh is None:
        return 0.878, []
    origin = Vector((px, py, 0.95))
    raised = None
    hits = []
    for _ in range(12):
        hit = bvh.ray_cast(origin, down, 0.15)
        if hit[0] is None or hit[0].z < 0.84:
            break
        z = hit[0].z
        hits.append(z)
        if WEB_Z[0] <= z <= WEB_Z[1]:
            return z, hits
        raised = z
            origin = Vector((px, py, hit[0].z - 0.002))
    return (raised if raised is not None else 0.878), hits


def main():
    strings.build()
    harp.build()
    courses = strings.course_lines()
    bvh = strings._plate_bvh()

    rogue = []
    for c in courses:
        d = (c["R"] - c["F"])
        dirxy = Vector((d.x, d.y, 0.0)).normalized()
        for k, (F_k, _R_k) in enumerate(c["unisons"]):
            p = F_k - dirxy * strings.PIN_R
            surf, hits = _pin_surface(bvh, p.x, p.y)
            top = hits[0] if hits else surf
            gap = top - surf
            if gap > 0.003:
                rogue.append({
                    "note": c["note"], "k": k,
                    "x": round(p.x, 4), "y": round(p.y, 4),
                    "hits": [round(z, 4) for z in hits],
                    "surf": round(surf, 4),
                    "gap_mm": round(gap * 1000, 2),
                })

    rogue.sort(key=lambda r: -r["gap_mm"])
    print(f"rogue pins: {len(rogue)} / 225")
    for r in rogue:
        print(f"  note {r['note']:3d} u{r['k']} ({r['x']},{r['y']}) "
              f"hits={r['hits']} surf={r['surf']} gap={r['gap_mm']}mm")
    if rogue:
        raise SystemExit(1)
    print("[inspect_pins] OK")


main()