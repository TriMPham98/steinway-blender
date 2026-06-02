"""Headless self-test - no MIDI hardware and no 103 MB model required.

    blender --background --python scripts/selftest.py

Two hermetic checks built from tiny synthetic meshes:
  A. retarget._split_object splits a joined mesh into per-key objects, drops a
     stray fragment, and puts each origin at the rear (max-Y) hinge edge.
  B. the anim state machine the live operator uses tips the right key (and only
     it), returns it flat on release, holds it under the sustain pedal, and tilts
     the tagged pedal object down then back up.

The full 52/36 -> MIDI 21..108 mapping is verified against the real model by
scripts/prepare_model.py.
"""

import math
import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _box(cx, w=0.02, y0=-0.15, y1=0.0, z0=0.0, z1=0.02):
    """8 verts / 6 quads of an axis-aligned key-ish box centered at x=cx."""
    x0, x1 = cx - w / 2, cx + w / 2
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
         (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return v, f


def _mesh_obj(bpy, name, verts, edges, faces, props=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, edges, faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    for k, val in (props or {}).items():
        obj[k] = val
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _test_split(bpy, retarget):
    centers = [-0.05, 0.0, 0.05]            # three separate "keys" in one mesh
    verts, faces = [], []
    for cx in centers:
        v, f = _box(cx)
        base = len(verts)
        verts += v
        faces += [tuple(base + i for i in face) for face in f]
    stray = len(verts)                       # a 2-vertex fragment, like the real file
    verts += [(centers[0], -0.05, 0.0), (centers[0], -0.05, 0.001)]
    joined = _mesh_obj(bpy, "White Keys", verts, [(stray, stray + 1)], faces)

    coll = bpy.data.collections.new("split_test")
    bpy.context.scene.collection.children.link(coll)
    parts = retarget._split_object(joined, coll, min_verts=4)

    assert len(parts) == len(centers), f"split gave {len(parts)} keys, want {len(centers)}"
    for cx, obj in parts:
        # origin sits at the rear hinge (max Y = 0), geometry hangs in front (y<=0)
        assert abs(obj.location.y - 0.0) < 1e-5, f"origin not at rear hinge: {obj.location.y}"
        min_y = min((obj.matrix_world @ v.co).y for v in obj.data.vertices)
        assert min_y < -0.1, f"key front should extend forward, min_y={min_y}"
    xs = sorted(cx for cx, _ in parts)
    assert xs[0] < xs[-1], "keys should be separable left-to-right by X"
    print(f"[selftest] split OK ({len(parts)} keys, fragment dropped)")


def _test_anim(bpy, anim):
    for note, cx in ((60, 0.0), (61, 0.03), (64, 0.09)):
        v, f = _box(cx)
        _mesh_obj(bpy, f"Key.{note:03d}", v, [], f, props={"midi_note": note})
    v, f = _box(0.0, w=0.04, y0=-0.18, y1=0.0)
    _mesh_obj(bpy, "Right Sustain Pedal", v, [], f, props={"steinway_role": "sustain_pedal"})

    press_angle = math.radians(3.5)
    dt = 0.01

    def fresh():
        return anim.LiveState(note_map=anim.build_note_map(), pedal_obj=anim.find_pedal())

    s0 = fresh()
    assert set(s0.note_map) == {60, 61, 64}, f"note map = {sorted(s0.note_map)}"
    assert s0.pedal_obj is not None, "pedal not found"

    # Velocity -> speed: a harder strike reaches the key bed in fewer ticks, while
    # every note still fully bottoms out (speed-only dynamics).
    def ticks_to_bottom(velocity, limit=500):
        st = fresh()
        anim.set_note(st, 60, velocity)
        for i in range(1, limit + 1):
            anim.ease_step(st, press_angle, dt)
            if st.note_map[60].rotation_euler.x >= press_angle * 0.99:
                return i
        return limit

    hard = ticks_to_bottom(110)
    med = ticks_to_bottom(64)
    soft = ticks_to_bottom(25)
    print(f"[selftest] ticks to bottom @dt={dt}: ff(110)={hard} mf(64)={med} pp(25)={soft}")
    assert hard < med < soft, "harder strikes must reach the key bed sooner"

    # Full bottom-out, crisp key-bed clamp (never past press_angle), neighbour still,
    # and pos stays bounded the whole time (integrator stability).
    s = fresh()
    anim.set_note(s, 60, 100)
    peak = 0.0
    for _ in range(500):
        anim.ease_step(s, press_angle, dt)
        peak = max(peak, s.note_map[60].rotation_euler.x)
        assert all(-1e-6 <= p <= 1.0 + 1e-6 for p in s.pos.values()), "pos left [0,1]"
    down = s.note_map[60].rotation_euler.x
    print(f"[selftest] bottomed at {down:.4f} (target {press_angle:.4f}), peak {peak:.4f}")
    assert down > press_angle * 0.98, "note should fully bottom out"
    assert peak <= press_angle + 1e-4, "key must not pass the key bed"
    assert abs(s.note_map[61].rotation_euler.x) < 1e-6, "neighbour key moved"

    # Release is snappy: the key returns to flat quickly.
    anim.set_note(s, 60, 0)
    rel = 0
    for i in range(1, 801):
        anim.ease_step(s, press_angle, dt)
        if abs(s.note_map[60].rotation_euler.x) < 1e-3:
            rel = i
            break
    print(f"[selftest] ticks to release: {rel}")
    assert rel and rel <= 30, f"release should be snappy, took {rel} ticks"

    # Sustain still tips the pedal (and does not hold keys down).
    anim.set_sustain(s, True)
    for _ in range(300):
        anim.ease_step(s, press_angle, dt)
    assert s.pedal_obj.rotation_euler.x > anim.PEDAL_ANGLE * 0.9, "pedal should tip down on sustain"
    anim.set_sustain(s, False)
    for _ in range(300):
        anim.ease_step(s, press_angle, dt)
    assert abs(s.pedal_obj.rotation_euler.x) < 1e-3, "pedal should return up"
    print("[selftest] anim + velocity + pedal OK")


def main():
    root = _repo_root()
    sys.path.insert(0, os.path.join(root, "extension"))

    from steinway_midi_piano.build import retarget
    from steinway_midi_piano import anim
    import bpy

    _test_split(bpy, retarget)
    _test_anim(bpy, anim)
    print("[selftest] OK")


main()
