"""Make the case furniture functional: fallboard, lid, and the missing nameboard.

The imported model bakes the fallboard open (a fixed vertical panel) and the
lid open on its prop stick, and has *nothing* behind the fallboard - the
nameboard/stretcher that closes the action cavity in a real piano is absent.

This builder:

- adds the **nameboard** (a case-wood panel behind the fallboard, sealing the
  cavity above the keys, like the real stretcher);
- re-origins the **fallboard** onto its hinge line, driven by
  ``Scene["fallboard_open"]`` (1 = open as imported, 0 = closed over the keys);
- re-origins the **big lid section** onto the spine hinge (driven by
  ``Scene["lid_open"]``) and rigs the **front flap** on the fold hinge between
  the sections (``Scene["lid_flap_fold"]``, 1 = folded back concert-style),
  parenting the hinge hardware and cushions along.

The controls live on the **scene** (Scene Properties > Custom Properties:
``fallboard_open``, ``lid_open``, ``lid_flap_fold``) - scene-level because a
driver reading a property of the object it poses is a dependency cycle that
Blender resolves nondeterministically. Slide or keyframe them. The lid prop
stick is re-origined onto its rim hinge and driven by ``lid_open`` too, so it
folds down flat as the lid closes instead of staying upright.

Pure ``bpy``, headless-safe, idempotent (objects are tagged once rigged).
"""

import math

import bpy
import mathutils
from mathutils import Vector

RIGGED = "steinway_rigged"
RIG_VERSION = 5
NAMEBOARD = "Name Board"

FALLBOARD = "Fall Board"
FALL_HINGE = (-0.705, 0.735)        # hinge line (y, z), along X
FALL_CLOSED = 1.48                  # rad forward to lie over the keys

LID_BIG = "Large Lid Section"
LID_SMALL = "Small Lid Section"
SPINE = (-0.564, 0.982)             # hinge line (x, z), along Y
LID_PARTS_BIG = ("Long Continuos Hinge BOTTOM", "Long Continous Hinge ROD",
                 "Long Continous Hinge Screws", "Large Lid Rubber Cushions")
LID_PARTS_SMALL = ("Long Continuos Hinge TOP", "Small Lid Rubber Cushions")
FOLD_BACK = 3.05                    # rad: front flap folded back on the lid

# Lid prop stick: hinged on the rim, stands up to hold the lid. As the lid
# closes it folds down flat into its trough instead of staying upright.
LID_PROP = "Lid Support Prop"
LID_PROP_CUP = "Lid Support Cup"        # rides the prop tip, under the lid
LID_PROP_HINGE = "Lid Prop Hinge Rod"   # the rod the prop pivots on (along Y)
LID_PROP_PIVOT = (0.849, -0.358, 0.953)  # fallback if the rod is missing
LID_PROP_FOLD = -1.0245                  # fallback fold-down angle (rad, about Y)

# Spine butt hinges: the lid-side leaves ride on the spine and must swing with
# the big lid; the base leaves and pins stay bolted to the rim.
LID_BUTT_HINGES = ("Lid Butt Hinge", "Lid Butt Hinge.001")


def _scene_prop(name, default):
    scene = bpy.context.scene
    if name not in scene:
        scene[name] = default
    ui = scene.id_properties_ui(name)
    ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0)
    return scene


def _drive(obj, channel, index, expr, prop):
    """Drive a channel from a scene custom property (cycle-free)."""
    obj.driver_remove(channel, index)
    fc = obj.driver_add(channel, index)
    drv = fc.driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "v"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "SCENE"
    var.targets[0].id = bpy.context.scene
    var.targets[0].data_path = f'["{prop}"]'
    drv.expression = expr


def _reorigin(obj, pivot_world):
    """Move the object's origin to ``pivot_world`` without moving its mesh."""
    mw = obj.matrix_world.copy()
    local = mw.inverted() @ Vector(pivot_world)
    for v in obj.data.vertices:
        v.co -= local
    obj.data.update()
    obj.matrix_world = mw @ mathutils.Matrix.Translation(local)


def _bake_basis(obj):
    """Bake rotation and scale into the mesh, leaving a pure-translation node.

    Two reasons: (1) a driver on a single rotation channel then rotates about
    that *world* axis (the prop's authored X/Z tilt would otherwise twist a
    local-Y fold out of its swing plane); (2) the LID PROP parts carry a tiny
    ~0.0004 object scale with ~2000-unit mesh coords, which glTF keeps as a
    micro-scaled node that three.js silently drops on load. Baking the basis
    normalises them to scale 1 like every other case part. World pose is
    preserved.
    """
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    basis = obj.matrix_basis.to_3x3()  # rotation @ scale, no translation
    for v in obj.data.vertices:
        v.co = basis @ v.co
    obj.data.update()
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


def _nameboard():
    if bpy.data.objects.get(NAMEBOARD) is not None:
        return "exists"
    fall = bpy.data.objects.get(FALLBOARD)
    mat = (fall.data.materials[0] if fall and fall.data.materials else None)
    v = [(-0.469, -0.702, 0.748), (0.833, -0.702, 0.748),
         (0.833, -0.694, 0.748), (-0.469, -0.694, 0.748),
         (-0.469, -0.702, 0.916), (0.833, -0.702, 0.916),
         (0.833, -0.694, 0.916), (-0.469, -0.694, 0.916)]
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(NAMEBOARD)
    me.from_pydata(v, [], f)
    if mat is not None:
        me.materials.append(mat)
    me.validate()
    me.update()
    obj = bpy.data.objects.new(NAMEBOARD, me)
    coll = (fall.users_collection[0] if fall and fall.users_collection
            else bpy.context.scene.collection)
    coll.objects.link(obj)
    return "added"


def _rig_fallboard():
    obj = bpy.data.objects.get(FALLBOARD)
    if obj is None:
        return "missing"
    if obj.get(RIGGED, 0) == RIG_VERSION:
        return "already-rigged"
    if not obj.get(RIGGED):
        hinge = bpy.data.objects.get("Key Lid Hinge")
        y, z = ((hinge.location.y, hinge.location.z) if hinge is not None
                else FALL_HINGE)
        _reorigin(obj, (obj.matrix_world.translation.x, y, z))
    if "open" in obj:
        del obj["open"]
    _scene_prop("fallboard_open", 1.0)
    _drive(obj, "rotation_euler", 0, f"(1-v)*{FALL_CLOSED}", "fallboard_open")
    obj[RIGGED] = RIG_VERSION
    obj.update_tag()
    return "rigged"


def _lid_angle(obj):
    """Tilt of the (open) lid plane: slope of its underside across x."""
    mw = obj.matrix_world
    cols = {}
    for v in obj.data.vertices:
        w = mw @ v.co
        k = round(w.x, 2)
        if k not in cols or w.z < cols[k][1]:
            cols[k] = (w.x, w.z)
    pts = sorted(cols.values())
    (x0, z0), (x1, z1) = pts[0], pts[-1]
    return math.atan2(z1 - z0, x1 - x0)


def _rig_lid():
    big = bpy.data.objects.get(LID_BIG)
    small = bpy.data.objects.get(LID_SMALL)
    if big is None or small is None:
        return "missing"
    if big.get(RIGGED, 0) == RIG_VERSION:
        return "already-rigged"
    first = not big.get(RIGGED)
    if first:
        tilt = _lid_angle(big)
        _reorigin(big, (SPINE[0], 0.0, SPINE[1]))
    else:
        # Already re-origined: the baked-open plane still gives the tilt.
        tilt = _lid_angle(big)

    hinge = bpy.data.objects.get("Lid Fold Hinge")
    if first or hinge is None:
        # Fold hinge between the sections: a frame empty tilted with the lid
        # plane carries a hinge empty whose local X is the fold axis.
        hb = bpy.data.objects.get("Long Continuos Hinge BOTTOM")
        if hb is not None:
            pts = [hb.matrix_world @ Vector(c) for c in hb.bound_box]
            pivot = Vector((min(p.x for p in pts),
                            sum(p.y for p in pts) / 8.0,
                            min(p.z for p in pts) + 0.004))
        else:
            pivot = Vector((-0.552, -0.412, 1.009))
        frame = bpy.data.objects.new("Lid Fold Frame", None)
        frame.empty_display_size = 0.05
        bpy.context.scene.collection.objects.link(frame)
        frame.matrix_world = (mathutils.Matrix.Translation(pivot)
                              @ mathutils.Matrix.Rotation(-tilt, 4, "Y"))
        frame.parent = big
        frame.matrix_parent_inverse = (
            mathutils.Matrix.Translation((SPINE[0], 0.0, SPINE[1])).inverted())
        hinge = bpy.data.objects.new("Lid Fold Hinge", None)
        hinge.empty_display_size = 0.05
        bpy.context.scene.collection.objects.link(hinge)
        hinge.parent = frame

        hinge_world = frame.matrix_world.copy()
        big_world = mathutils.Matrix.Translation((SPINE[0], 0.0, SPINE[1]))
        assignments = [(LID_SMALL, hinge, hinge_world)]
        assignments += [(nm, hinge, hinge_world) for nm in LID_PARTS_SMALL]
        assignments += [(nm, big, big_world) for nm in LID_PARTS_BIG]
        for name, parent, pw in assignments:
            obj = bpy.data.objects.get(name)
            if obj is None:
                continue
            obj.parent = parent
            obj.matrix_parent_inverse = pw.inverted()

    for obj, prop in ((big, "open"), (small, "fold")):
        if prop in obj:
            del obj[prop]
    _scene_prop("lid_open", 1.0)
    _scene_prop("lid_flap_fold", 0.0)
    _drive(big, "rotation_euler", 1, f"(1-v)*{tilt:.4f}", "lid_open")
    _drive(hinge, "rotation_euler", 0, f"v*{FOLD_BACK}", "lid_flap_fold")
    big[RIGGED] = RIG_VERSION
    big.update_tag()
    small.update_tag()
    return "rigged"


def _prop_pivot():
    """World pivot of the prop hinge (rod centre), with a constant fallback."""
    rod = bpy.data.objects.get(LID_PROP_HINGE)
    if rod is None or rod.type != "MESH" or not rod.data.vertices:
        return Vector(LID_PROP_PIVOT)
    pts = [rod.matrix_world @ v.co for v in rod.data.vertices]
    return Vector((sum(p.x for p in pts) / len(pts),
                   sum(p.y for p in pts) / len(pts),
                   sum(p.z for p in pts) / len(pts)))


def _prop_fold_angle(prop, pivot):
    """Rotation about Y (rad) that lays the upright prop flat, pointing inward.

    The prop swings in the X-Z plane (hinge rod runs along Y). Take its tip as
    the vertex furthest from the pivot, then solve for the angle that drops the
    tip to the pivot height with the stick pointing toward -X (the interior).
    """
    mw = prop.matrix_world
    tip = max((mw @ v.co for v in prop.data.vertices),
              key=lambda w: (w - pivot).length)
    dx, dz = tip.x - pivot.x, tip.z - pivot.z
    if abs(dx) < 1e-6 and abs(dz) < 1e-6:
        return LID_PROP_FOLD
    return math.atan2(dz, dx) - math.pi


def _rig_lid_prop():
    """Fold the prop stick on its rim hinge; ride the cup with the lid.

    The cup is the receptacle on the lid underside, so it stays bolted to the
    big lid (swings with it about the spine). The prop stick pivots
    independently on its own rim hinge, folding flat as the lid closes.
    """
    prop = bpy.data.objects.get(LID_PROP)
    cup = bpy.data.objects.get(LID_PROP_CUP)
    if prop is None:
        return "missing"
    if prop.get(RIGGED, 0) == RIG_VERSION:
        return "already-rigged"
    pivot = _prop_pivot()
    fold = _prop_fold_angle(prop, pivot)

    # Prop: re-origin onto the hinge, normalise its basis, drive the fold.
    if (prop.matrix_world.translation - pivot).length > 1e-4:
        _reorigin(prop, pivot)
    _bake_basis(prop)
    _scene_prop("lid_open", 1.0)
    _drive(prop, "rotation_euler", 1, f"(1-v)*{fold:.4f}", "lid_open")
    prop["fold_angle"] = fold
    prop[RIGGED] = RIG_VERSION
    prop.update_tag()

    # Cup: drop any fold driver it picked up from an older rig, normalise its
    # basis, and parent it to the big lid so it swings with the lid.
    if cup is not None:
        cup.driver_remove("rotation_euler", 1)
        cup.rotation_euler = (0.0, 0.0, 0.0)
        _bake_basis(cup)
        big = bpy.data.objects.get(LID_BIG)
        if big is not None and cup.parent is not big:
            cup.parent = big
            cup.matrix_parent_inverse = big.matrix_world.inverted()
        cup[RIGGED] = RIG_VERSION
        cup.update_tag()
    return "rigged"


def _rig_lid_butt_hinges():
    """Parent the spine's lid-side hinge leaves to the big lid so they swing."""
    big = bpy.data.objects.get(LID_BIG)
    if big is None:
        return "missing"
    done = []
    for name in LID_BUTT_HINGES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.parent is big:
            continue
        obj.parent = big
        obj.matrix_parent_inverse = big.matrix_world.inverted()
        done.append(name)
    return done or "already-rigged"


def build():
    return {
        "nameboard": _nameboard(),
        "fallboard": _rig_fallboard(),
        "lid": _rig_lid(),
        "lid_prop": _rig_lid_prop(),
        "lid_butt_hinges": _rig_lid_butt_hinges(),
    }
