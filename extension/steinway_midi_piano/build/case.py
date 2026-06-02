"""Procedural Steinway Model D case (aesthetic + intentionally swappable).

This is the "hybrid" half of the model: a recognizable concert-grand body that
frames the precisely-rigged keyboard. It is built into its own collection
(``Steinway_Case``) and never touches the key rig, so it can later be replaced
by an imported high-detail body without affecting MIDI playback.

Coordinate convention (shared with keyboard.py):
  +X = bass -> treble,  -Y = toward the player (keys poke out the front at y<0),
  +Z = up.  The keyboard front sits at y = 0.
"""

import math

import bpy

from . import _geom, keyboard

COLL = "Steinway_Case"

WIDTH = 1.48
W2 = WIDTH / 2.0
BODY_BOTTOM = 0.58
BODY_TOP = 0.94
LID_THICK = 0.02
LID_OPEN = math.radians(35.0)   # lid lifted on the bass-side hinge

# Top-view outline of the rim, front edge at y = 0, sweeping up the treble
# (bent) side, around the tail, and straight back down the bass spine.
OUTLINE = [
    (-W2, 0.00), (W2, 0.00),
    (W2, 0.55), (0.72, 0.95), (0.68, 1.35), (0.62, 1.72),
    (0.52, 2.05), (0.38, 2.33), (0.20, 2.54), (0.00, 2.66),
    (-0.22, 2.71), (-0.44, 2.69), (-0.60, 2.58), (-0.70, 2.38),
    (-W2, 2.05),
]


def clear():
    _geom.clear_collection(COLL)


def _box(coll, name, x0, x1, y0, y1, z0, z1, mat):
    obj = _geom.new_object(name, _geom.box_mesh(name, x0, x1, y0, y1, z0, z1), coll)
    _geom.assign_material(obj, mat)
    return obj


def _leg(coll, name, x, y, mat):
    mesh = _geom.cone_mesh(name, 0.045, 0.055, BODY_BOTTOM)
    obj = _geom.new_object(name, mesh, coll, (x, y, BODY_BOTTOM / 2.0))
    _geom.assign_material(obj, mat)
    return obj


def build():
    """(Re)build the case into the Steinway_Case collection. Idempotent."""
    clear()
    coll = _geom.ensure_collection(COLL)
    ebony = _geom.get_material("Steinway_Ebony", (0.015, 0.015, 0.018), roughness=0.18)
    brass = _geom.get_material("Steinway_Brass", (0.66, 0.50, 0.18), roughness=0.25, metallic=1.0)

    # Rim / body slab.
    body = _geom.new_object(
        "Steinway_Body", _geom.extruded_polygon("Steinway_Body", OUTLINE, BODY_BOTTOM, BODY_TOP), coll
    )
    _geom.assign_material(body, ebony)

    # Lid: same outline, hinged on the bass spine (local x = 0) and propped open.
    lid_pts = [(x + W2, y) for (x, y) in OUTLINE]
    lid = _geom.new_object(
        "Steinway_Lid", _geom.extruded_polygon("Steinway_Lid", lid_pts, 0.0, LID_THICK), coll,
        (-W2, 0.0, BODY_TOP),
    )
    lid.rotation_euler = (0.0, -LID_OPEN, 0.0)   # lift the treble side up
    _geom.assign_material(lid, ebony)

    # Lid prop stick (approximate contact under the raised treble side).
    _box(coll, "Steinway_LidProp", 0.58, 0.62, 0.18, 0.22, BODY_TOP, BODY_TOP + 0.77, ebony)

    # Three tapered legs.
    _leg(coll, "Steinway_LegFL", -0.55, 0.18, ebony)
    _leg(coll, "Steinway_LegFR", 0.55, 0.18, ebony)
    _leg(coll, "Steinway_LegTail", -0.10, 2.35, ebony)

    # Cheek blocks framing the keyboard ends (keys span +/-0.6125 in x).
    _box(coll, "Steinway_CheekL", -0.70, -0.61, -0.16, 0.02, 0.72, 0.80, ebony)
    _box(coll, "Steinway_CheekR", 0.61, 0.70, -0.16, 0.02, 0.72, 0.80, ebony)

    # Pedal lyre + three pedals.
    _box(coll, "Steinway_Lyre", -0.10, 0.10, 0.18, 0.215, 0.12, 0.42, ebony)
    _box(coll, "Steinway_LyreRodL", -0.085, -0.07, 0.19, 0.205, 0.40, BODY_BOTTOM, ebony)
    _box(coll, "Steinway_LyreRodR", 0.07, 0.085, 0.19, 0.205, 0.40, BODY_BOTTOM, ebony)
    for i, px in enumerate((-0.06, 0.0, 0.06)):
        _box(coll, f"Steinway_Pedal{i}", px - 0.018, px + 0.018, 0.04, 0.17, 0.11, 0.13, brass)

    return coll
