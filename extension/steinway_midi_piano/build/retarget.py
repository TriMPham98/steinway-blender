"""Retarget an imported grand-piano model onto the live-MIDI rig.

The imported ``SteinwayGrandPiano.blend`` ships its keys as two *joined* meshes,
``White Keys`` (52 keys) and ``Black Keys`` (36 keys), rather than the 88 separate
objects the animator needs. This module splits each joined mesh into its
connected components, drops stray fragments, gives every key an origin at its
**rear hinge edge** (so ``rotation_euler.x`` tips the front down, exactly like the
retired procedural keyboard), tags it with its MIDI note, and names it
``Key.NNN`` -- which is all ``anim.build_note_map()`` looks for. It also re-origins
and tags the right (sustain) pedal so CC64 can tilt it.

Pure ``bpy`` (no ``bpy.ops``) so it runs headless without a window context.
"""

import bpy
import mathutils

from . import _geom

# Source mesh + output collection names.
WHITE_MESH = "White Keys"
BLACK_MESH = "Black Keys"
KEYS_COLL = "Steinway_Keys"
DEFAULT_PEDAL = "Right Sustain Pedal"
PEDAL_ROLE = "sustain_pedal"
LOGO_COLL = "Steinway & Sons Logo"   # the lyre + wordmark decal group
LID_PANEL = "Fall Board"             # panel the logo sits on (centered within it)
PIANO_COLL_FROM = "BABY GRAN PIANO"  # imported top-level collection, renamed on prep
PIANO_COLL_TO = "STEINWAY GRAND PIANO"

# MIDI range / note classes (A0..C8; white = C D E F G A B).
MIDI_LOW, MIDI_HIGH = 21, 108
WHITE_CLASSES = frozenset({0, 2, 4, 5, 7, 9, 11})
WHITE_NOTES = [n for n in range(MIDI_LOW, MIDI_HIGH + 1) if (n % 12) in WHITE_CLASSES]
BLACK_NOTES = [n for n in range(MIDI_LOW, MIDI_HIGH + 1) if (n % 12) not in WHITE_CLASSES]

_REAR_EPS = 1e-4   # verts within this of max-Y count as the rear hinge edge


def is_white(note):
    return (note % 12) in WHITE_CLASSES


# --------------------------------------------------------------------------- #
# Mesh splitting
# --------------------------------------------------------------------------- #
def _components(me):
    """Connected vertex-index groups of a mesh, via union-find over its edges."""
    n = len(me.vertices)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]   # path halving
            a = parent[a]
        return a

    for e in me.edges:
        a, b = e.vertices
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _rear_hinge_pivot(coords, idxs):
    """Pivot for a key/pedal: center X, rear (max) Y, mean Z of the rear edge."""
    xs = [coords[i].x for i in idxs]
    ys = [coords[i].y for i in idxs]
    max_y = max(ys)
    rear = [i for i in idxs if max_y - coords[i].y <= _REAR_EPS]
    zref = sum(coords[i].z for i in rear) / len(rear)
    return mathutils.Vector((0.5 * (min(xs) + max(xs)), max_y, zref))


def _split_object(obj, coll, min_verts=50):
    """Split one joined key mesh into per-key objects with rear-hinge origins.

    Returns ``[(center_x, object), ...]`` (unsorted). Honors modifiers (reads the
    evaluated mesh) and discards components with fewer than ``min_verts`` vertices
    (the stray edge fragments in ``White Keys``). Source materials are copied so
    the split keys keep their imported look.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    me = obj_eval.to_mesh()
    mw = obj.matrix_world

    # Pull everything we need into plain Python BEFORE creating any datablocks,
    # so building new meshes can't invalidate the temporary evaluated mesh.
    coords = [mw @ v.co for v in me.vertices]
    comps = _components(me)
    comp_of = [0] * len(me.vertices)
    for cid, idxs in enumerate(comps):
        for i in idxs:
            comp_of[i] = cid
    faces_by_comp = [[] for _ in comps]
    for poly in me.polygons:
        vs = tuple(poly.vertices)
        faces_by_comp[comp_of[vs[0]]].append(vs)   # connected => one component
    mats = list(obj.data.materials)
    obj_eval.to_mesh_clear()

    out = []
    for cid, idxs in enumerate(comps):
        if len(idxs) < min_verts:
            continue
        pivot = _rear_hinge_pivot(coords, idxs)
        remap = {}
        verts = []
        for i in idxs:
            remap[i] = len(verts)
            verts.append(tuple(coords[i] - pivot))     # local to the hinge origin
        faces = [[remap[i] for i in f] for f in faces_by_comp[cid]]

        mesh = bpy.data.meshes.new(obj.name + ".part")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        for m in mats:
            mesh.materials.append(m)

        nobj = bpy.data.objects.new(obj.name + ".part", mesh)
        nobj.location = pivot                          # identity rot/scale
        coll.objects.link(nobj)
        out.append((pivot.x, nobj))
    return out


def _tag(obj, note, color):
    obj.name = f"Key.{note:03d}"
    obj.data.name = f"KeyMesh.{note:03d}"
    obj["midi_note"] = note
    obj["key_color"] = color


def split_keys(white=WHITE_MESH, black=BLACK_MESH, reverse=None):
    """Split the two joined key meshes into 88 tagged ``Key.NNN`` objects.

    ``reverse`` controls bass->treble direction; ``None`` auto-detects it from the
    white/black interleave pattern (so a mirrored model just works).
    """
    src_white = bpy.data.objects.get(white)
    src_black = bpy.data.objects.get(black)
    if src_white is None or src_black is None:
        raise RuntimeError(
            f"Joined key meshes not found (need '{white}' and '{black}'). "
            "Open the imported Steinway model first."
        )

    _geom.clear_collection(KEYS_COLL)
    coll = _geom.ensure_collection(KEYS_COLL)

    whites = _split_object(src_white, coll)
    blacks = _split_object(src_black, coll)
    if len(whites) != len(WHITE_NOTES):
        raise RuntimeError(f"expected {len(WHITE_NOTES)} white keys, split gave {len(whites)}")
    if len(blacks) != len(BLACK_NOTES):
        raise RuntimeError(f"expected {len(BLACK_NOTES)} black keys, split gave {len(blacks)}")

    # Auto-detect bass->treble orientation by matching the color interleave.
    combined = sorted([(x, "white") for x, _ in whites] + [(x, "black") for x, _ in blacks])
    got = [c for _, c in combined]
    want = ["white" if is_white(n) else "black" for n in range(MIDI_LOW, MIDI_HIGH + 1)]
    if reverse is None:
        if got == want:
            reverse = False
        elif got == want[::-1]:
            reverse = True
        else:
            raise RuntimeError("split key colors don't match an 88-key layout (bad separation?)")

    whites.sort(key=lambda t: t[0], reverse=reverse)
    blacks.sort(key=lambda t: t[0], reverse=reverse)
    for (_, obj), note in zip(whites, WHITE_NOTES):
        _tag(obj, note, "white")
    for (_, obj), note in zip(blacks, BLACK_NOTES):
        _tag(obj, note, "black")

    bpy.data.objects.remove(src_white, do_unlink=True)
    bpy.data.objects.remove(src_black, do_unlink=True)

    notes = sorted(int(o["midi_note"]) for o in coll.objects)
    assert notes == list(range(MIDI_LOW, MIDI_HIGH + 1)), "keys must map to MIDI 21..108"
    return {"white": len(whites), "black": len(blacks),
            "low": notes[0], "high": notes[-1], "reversed": reverse}


# --------------------------------------------------------------------------- #
# Sustain pedal
# --------------------------------------------------------------------------- #
def _find_pedal_obj(name):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        return obj
    for o in bpy.data.objects:                  # fuzzy fallback
        ln = o.name.lower()
        if o.type == "MESH" and "right" in ln and "pedal" in ln:
            return o
    return None


def prep_sustain_pedal(name=DEFAULT_PEDAL):
    """Move the right pedal's origin to its rear hinge and tag it for the animator.

    Returns the pedal object, or ``None`` if the model has no recognizable pedal.
    """
    obj = _find_pedal_obj(name)
    if obj is None:
        return None
    me = obj.data
    mw = obj.matrix_world.copy()
    world = [mw @ v.co for v in me.vertices]
    pivot = _rear_hinge_pivot(world, range(len(world)))
    for v, c in zip(me.vertices, world):
        v.co = c - pivot                        # keep geometry in place...
    me.update()
    obj.matrix_world = mathutils.Matrix.Translation(pivot)   # ...origin -> hinge
    obj["steinway_role"] = PEDAL_ROLE
    return obj


# --------------------------------------------------------------------------- #
# Branding
# --------------------------------------------------------------------------- #
def _world_z_bounds(objs):
    lo, hi = float("inf"), float("-inf")
    for o in objs:
        for corner in o.bound_box:
            z = (o.matrix_world @ mathutils.Vector(corner)).z
            lo, hi = min(lo, z), max(hi, z)
    return lo, hi


def center_logo(coll=LOGO_COLL, panel=LID_PANEL):
    """Vertically center the logo/wordmark group on its panel (world Z only).

    Idempotent, and a no-op when either the collection or the panel is missing, so
    it is safe to call on any model. Returns the applied Z shift (m), or None.
    """
    group = bpy.data.collections.get(coll)
    plate = bpy.data.objects.get(panel)
    if group is None or plate is None or not group.objects:
        return None
    objs = list(group.objects)
    glo, ghi = _world_z_bounds(objs)
    plo, phi = _world_z_bounds([plate])
    dz = (plo + phi) / 2.0 - (glo + ghi) / 2.0
    for obj in objs:
        obj.location.z += dz        # unparented + Z-translate -> shifts whole bbox
    return dz


def rename_piano_collection(old=PIANO_COLL_FROM, new=PIANO_COLL_TO):
    """Rename the imported top-level piano collection. Idempotent / safe no-op."""
    if bpy.data.collections.get(new) is not None:
        return new
    coll = bpy.data.collections.get(old)
    if coll is None:
        return None
    coll.name = new
    return new


def reset_cursor():
    """Park the 3D cursor at the world origin (its conventional home)."""
    cur = bpy.context.scene.cursor
    cur.location = (0.0, 0.0, 0.0)
    cur.rotation_euler = (0.0, 0.0, 0.0)
    return tuple(cur.location)


# --------------------------------------------------------------------------- #
# One-shot entry point
# --------------------------------------------------------------------------- #
def _tagged_keys():
    return [o for o in bpy.data.objects if o.get("midi_note") is not None]


def prepare():
    """Split keys, prep the pedal, center the logo, tidy collection names. Idempotent."""
    logo_dz = center_logo()
    collection = rename_piano_collection()
    reset_cursor()
    if bpy.data.objects.get(WHITE_MESH) is None and bpy.data.objects.get(BLACK_MESH) is None:
        keys = _tagged_keys()
        if keys:
            return {"status": "already-prepared", "logo_dz": logo_dz, "collection": collection,
                    "white": sum(o["key_color"] == "white" for o in keys),
                    "black": sum(o["key_color"] == "black" for o in keys)}
        raise RuntimeError(
            f"Joined key meshes '{WHITE_MESH}'/'{BLACK_MESH}' not found. "
            "Open the imported Steinway model first."
        )
    summary = split_keys()
    pedal = prep_sustain_pedal()
    summary["pedal"] = pedal.name if pedal else None
    summary["logo_dz"] = logo_dz
    summary["collection"] = collection
    summary["status"] = "prepared"
    return summary
