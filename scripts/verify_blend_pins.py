"""Verify Tuning_Pins bases sit on the flat pin field in the saved .blend.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/verify_blend_pins.py
"""

import bpy

WEB_Z = (0.868, 0.882)
VERTS_PER_PIN = 32


def main():
    obj = bpy.data.objects.get("Tuning_Pins")
    if obj is None:
        raise SystemExit("Tuning_Pins missing - run build_all.py --out first")
    mw = obj.matrix_world
    zs = [((mw @ v.co).z) for v in obj.data.vertices]
    n_pins = len(zs) // VERTS_PER_PIN
    bases = []
    for i in range(n_pins):
        chunk = zs[i * VERTS_PER_PIN:(i + 1) * VERTS_PER_PIN]
        bases.append(min(chunk))
    rogue = [round(z, 4) for z in bases if z > WEB_Z[1] + 0.002]
    print(f"Tuning_Pins: {n_pins} pins, base z {min(bases):.4f}..{max(bases):.4f}")
    if rogue:
        print(f"rogue bases ({len(rogue)}): {sorted(set(rogue))}")
        raise SystemExit(1)
    print("[verify_blend_pins] OK")


main()