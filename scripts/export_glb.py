"""Export the prepared Steinway .blend to a web-ready GLB (+ key manifest).

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py -- \\
        --out web/public/models/steinway.glb

Joins all non-key / non-pedal meshes into a single ``Piano_Static`` object so the
glTF export finishes in reasonable time (~90 objects instead of ~150). Keys stay
separate ``Key.NNN`` objects with ``midi_note`` in glTF extras; the sustain pedal
stays separate with ``steinway_role``.

Writes ``steinway.keys.json`` next to the GLB listing note -> node name.
"""

from __future__ import annotations

import json
import os
import sys
import time


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _argv_after_double_dash():
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _parse_out(root):
    argv = _argv_after_double_dash()
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    else:
        out = os.path.join(root, "web", "public", "models", "steinway.glb")
    if not os.path.isabs(out):
        out = os.path.join(root, out)
    return out


def _is_key(obj):
    return obj.type == "MESH" and obj.name.startswith("Key.")


def _is_pedal(obj):
    return obj.get("steinway_role") == "sustain_pedal"


def _strip_lid_hinge():
    """Remove leftover 0.5.x lid rig so the glTF scene root is not Key Lid Hinge."""
    import bpy

    hinge = bpy.data.objects.get("Key Lid Hinge")
    if hinge is None:
        return
    for child in list(hinge.children):
        child.parent = None
        for sub in child.children:
            sub.parent = None
    bpy.data.objects.remove(hinge, do_unlink=True)


def _join_static():
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if _is_key(obj) or _is_pedal(obj):
            continue
        obj.select_set(True)
        targets.append(obj)
    if len(targets) < 2:
        if len(targets) == 1:
            targets[0].name = "Piano_Static"
        return len(targets)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.join()
    bpy.context.active_object.name = "Piano_Static"
    return len(targets)


def _key_manifest():
    import bpy

    keys = []
    for obj in bpy.data.objects:
        note = obj.get("midi_note")
        if note is None:
            continue
        keys.append(
            {
                "note": int(note),
                "name": obj.name,
                "color": obj.get("key_color"),
            }
        )
    keys.sort(key=lambda k: k["note"])
    pedal = None
    for obj in bpy.data.objects:
        if _is_pedal(obj):
            pedal = obj.name
            break
    return {
        "keys": keys,
        "pedal": pedal,
        "press_angle_deg": 3.5,
        "defaults": {
            "press_angle_deg": 3.5,
            "snappiness": 1.0,
            "velocity_sensitivity": 1.0,
            "pedal_angle_deg": 5.0,
        },
    }


def main():
    import bpy

    root = _repo_root()
    out_glb = _parse_out(root)
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    manifest_path = os.path.splitext(out_glb)[0] + ".keys.json"

    t0 = time.time()
    _strip_lid_hinge()
    merged = _join_static()
    manifest = _key_manifest()
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        export_extras=True,
        export_apply=False,
        # Full PBR bake is very slow on this asset; placeholders keep materials
        # in the glTF and let the site finish export in seconds.
        export_materials="PLACEHOLDER",
    )
    size_mb = os.path.getsize(out_glb) / 1e6
    elapsed = time.time() - t0
    print(f"[export] merged {merged} static meshes -> Piano_Static")
    print(f"[export] keys in manifest: {len(manifest['keys'])}")
    print(f"[export] wrote {out_glb} ({size_mb:.1f} MB, {elapsed:.0f}s)")
    print(f"[export] wrote {manifest_path}")
    print("[export] OK")


main()