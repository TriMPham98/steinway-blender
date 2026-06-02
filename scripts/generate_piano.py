"""Headless model generator / verifier.

    blender --background --python scripts/generate_piano.py
    blender --background --python scripts/generate_piano.py -- --save

Builds the procedural Steinway Model D and asserts the keyboard is correctly
mapped (88 keys, 52 white / 36 black, MIDI notes 21..108). With ``--save`` it
writes assets/steinway_d.blend.
"""

import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _present(bpy):
    """Turn the build into a clean, camera-framed scene for the saved .blend."""
    import math
    import mathutils

    for name in ("Cube", "Light", "Camera"):  # drop Blender's startup defaults
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 34
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (3.1, -2.9, 2.2)
    cam.rotation_euler = (
        mathutils.Vector((0.0, 0.95, 0.5)) - cam.location
    ).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.5
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(55), math.radians(12), math.radians(-50))

    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.05, 0.05, 0.06, 1.0)
        bg.inputs[1].default_value = 0.7
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except Exception:
            pass


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import keyboard, case

    keyboard.build()
    case.build()

    import bpy

    keys = [o for o in bpy.data.objects if o.get("midi_note") is not None]
    whites = [o for o in keys if o.get("key_color") == "white"]
    blacks = [o for o in keys if o.get("key_color") == "black"]
    notes = sorted(int(o["midi_note"]) for o in keys)

    print(f"[generate] key objects : {len(keys)} (white={len(whites)}, black={len(blacks)})")
    print(f"[generate] note range  : {notes[0]}..{notes[-1]}")
    print(f"[generate] collections : {[c.name for c in bpy.data.collections]}")
    print(f"[generate] case objects: {len(bpy.data.collections['Steinway_Case'].objects)}")

    assert len(keys) == 88, f"expected 88 keys, got {len(keys)}"
    assert len(whites) == 52, f"expected 52 white keys, got {len(whites)}"
    assert len(blacks) == 36, f"expected 36 black keys, got {len(blacks)}"
    assert notes == list(range(21, 109)), "keys must map contiguously to MIDI 21..108"
    assert "Steinway_Keys" in bpy.data.collections
    assert "Steinway_Case" in bpy.data.collections

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--save" in argv:
        _present(bpy)
        out = os.path.join(root, "assets", "steinway_d.blend")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[generate] saved {out}")

    print("[generate] OK")


main()
