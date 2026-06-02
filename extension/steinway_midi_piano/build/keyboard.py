"""Procedural 88-key keyboard.

Each key is a separate object named ``Key.NNN`` (NNN = MIDI note, zero-padded),
carrying custom properties ``midi_note`` (int) and ``key_color`` ("white"/"black").
Every key's origin sits at its REAR edge (the fallboard hinge line) so the live
driver can tip the front of the key down with a small +X rotation.
"""

import bpy

from . import _geom

COLL = "Steinway_Keys"

# --- geometry, in meters ----------------------------------------------------
KEYBED_WIDTH = 1.225            # standard 88-key playing width
N_WHITE = 52
WHITE_W = KEYBED_WIDTH / N_WHITE
WHITE_GAP = 0.0015             # visible gap between adjacent white keys
WHITE_L = 0.145                # front-to-back length of a white key
WHITE_H = 0.022                # white key thickness
BLACK_W = 0.011
BLACK_L = 0.095
BLACK_BOTTOM = 0.010           # black key floats above the keybed...
BLACK_TOP = 0.031              # ...and rises ~9 mm above the white tops
KEY_Z = 0.74                   # playing-surface height above the floor

# --- MIDI range -------------------------------------------------------------
MIDI_LOW = 21                  # A0
MIDI_HIGH = 108                # C8
WHITE_CLASSES = frozenset({0, 2, 4, 5, 7, 9, 11})  # C D E F G A B


def is_white(note):
    return (note % 12) in WHITE_CLASSES


def clear():
    _geom.clear_collection(COLL)


def build():
    """(Re)build all 88 keys into the Steinway_Keys collection. Idempotent."""
    clear()
    coll = _geom.ensure_collection(COLL)
    white_mat = _geom.get_material("Steinway_KeyWhite", (0.93, 0.92, 0.88), roughness=0.25)
    black_mat = _geom.get_material("Steinway_KeyBlack", (0.02, 0.02, 0.02), roughness=0.20)

    x_left = -KEYBED_WIDTH / 2.0
    white_index = 0
    for note in range(MIDI_LOW, MIDI_HIGH + 1):
        if is_white(note):
            cx = x_left + (white_index + 0.5) * WHITE_W
            w = WHITE_W - WHITE_GAP
            mesh = _geom.box_mesh(
                f"KeyMesh.{note:03d}", -w / 2, w / 2, -WHITE_L, 0.0, 0.0, WHITE_H
            )
            obj = _geom.new_object(f"Key.{note:03d}", mesh, coll, (cx, 0.0, KEY_Z))
            _geom.assign_material(obj, white_mat)
            obj["key_color"] = "white"
            white_index += 1
        else:
            # Black key centered on the seam between the two flanking white keys.
            cx = x_left + white_index * WHITE_W
            mesh = _geom.box_mesh(
                f"KeyMesh.{note:03d}",
                -BLACK_W / 2, BLACK_W / 2, -BLACK_L, 0.0, BLACK_BOTTOM, BLACK_TOP,
            )
            obj = _geom.new_object(f"Key.{note:03d}", mesh, coll, (cx, 0.0, KEY_Z))
            _geom.assign_material(obj, black_mat)
            obj["key_color"] = "black"
        obj["midi_note"] = note
    return coll
