"""Dump scene structure of the playable blend for action-mechanism planning.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/inspect_scene.py
"""

import bpy
import mathutils


def _bbox_world(obj):
    pts = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def main():
    print("=== collections ===")
    for coll in bpy.data.collections:
        print(f"  {coll.name}: {len(coll.objects)} objects")

    print("=== non-key objects (name, type, world bbox lo->hi) ===")
    for obj in sorted(bpy.data.objects, key=lambda o: o.name):
        if obj.name.startswith("Key."):
            continue
        if obj.type not in ("MESH", "CURVE", "EMPTY"):
            print(f"  {obj.name} [{obj.type}]")
            continue
        try:
            lo, hi = _bbox_world(obj)
            print(
                f"  {obj.name} [{obj.type}] "
                f"lo=({lo.x:.3f},{lo.y:.3f},{lo.z:.3f}) hi=({hi.x:.3f},{hi.y:.3f},{hi.z:.3f})"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {obj.name} [{obj.type}] (bbox failed: {exc})")

    print("=== key sample (first, middle-C 60, last) ===")
    for note in (21, 60, 108):
        obj = bpy.data.objects.get(f"Key.{note:03d}")
        if obj is None:
            print(f"  Key.{note:03d}: MISSING")
            continue
        lo, hi = _bbox_world(obj)
        print(
            f"  {obj.name}: origin=({obj.location.x:.4f},{obj.location.y:.4f},{obj.location.z:.4f}) "
            f"dims=({obj.dimensions.x:.4f},{obj.dimensions.y:.4f},{obj.dimensions.z:.4f}) "
            f"color={obj.get('key_color')}"
        )
        print(
            f"    bbox lo=({lo.x:.4f},{lo.y:.4f},{lo.z:.4f}) hi=({hi.x:.4f},{hi.y:.4f},{hi.z:.4f})"
        )

    keys = [o for o in bpy.data.objects if o.get("midi_note") is not None]
    los = [_bbox_world(o)[0] for o in keys]
    his = [_bbox_world(o)[1] for o in keys]
    print("=== full keyboard bbox ===")
    print(
        f"  lo=({min(v.x for v in los):.4f},{min(v.y for v in los):.4f},{min(v.z for v in los):.4f})"
    )
    print(
        f"  hi=({max(v.x for v in his):.4f},{max(v.y for v in his):.4f},{max(v.z for v in his):.4f})"
    )

    print("=== string/interior candidates ===")
    for obj in bpy.data.objects:
        ln = obj.name.lower()
        if any(k in ln for k in ("string", "frame", "plate", "soundboard", "bridge",
                                 "tuning", "pin", "damper", "hammer", "harp", "lid")):
            print(f"  {obj.name} [{obj.type}]")

    print("=== scene units ===")
    s = bpy.context.scene
    print(f"  unit system={s.unit_settings.system} scale={s.unit_settings.scale_length}")
    print("[inspect] OK")


main()
