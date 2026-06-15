"""Verify damper export state in the playable blend / GLB pipeline.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/inspect_dampers.py
"""

import bpy

dec = []
for name in ("Dampers Tops", "Dampers Bottoms"):
    obj = bpy.data.objects.get(name)
    if obj:
        dec.append((name, obj.hide_get(), obj.get("steinway_replaced")))

action = [o.name for o in bpy.data.objects if o.get("action_part") == "damper_head"]
print(f"decorative: {dec}")
print(f"action heads: {len(action)}")
if dec and any(not r for _, _, r in dec) and action:
    raise SystemExit("decorative dampers not tagged replaced while action exists")
print("[inspect_dampers] OK")