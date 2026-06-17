"""Export the prepared Steinway .blend to a web-ready GLB (+ key manifest).

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py -- \\
        --out web/public/models/steinway.glb --with-action

Pipeline (source of truth: ``assets/steinway_grand_playable.blend``):

1. Strip scene props (Floor, oversized meshes).
2. **Bench** — remove ``Seat_Cushion``, ``Seat_Frame``, and any ``Piano_Bench``.
3. **Bench legs** — remove the four bench leg meshes (``Bench_Leg_01`` … ``Bench_Leg_04``) only.
4. **Stray curves** — remove CURVE objects the mesh-only join skips (they'd export
   as standalone meshes, e.g. a gold disc floating above the case rim).
5. **Body** — join remaining static meshes into ``Piano_Static``.
6. Flatten materials to fast Principled trees; export GLB. Web viewer refines by
   material name (``web/src/scene-utils.js``).

Keys stay separate ``Key.NNN`` with ``midi_note``; sustain pedal keeps
``steinway_role``.

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


def _is_action(obj):
    return obj.get("action_part") is not None


def _strip_action(keep):
    """Drop the double-escapement action (hidden inside the case) from the GLB.

    440+ extra nodes/draw calls buy nothing in the closed-case web view; pass
    ``--with-action`` to keep the parts (exported at rest - glTF has no drivers).
    """
    import bpy

    if keep:
        return 0
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and _is_action(obj):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    if removed:
        print(f"[export] action parts stripped: {removed} (--with-action keeps them)")
    return removed


def _strip_replaced():
    """Drop retired stand-in meshes (e.g. the 51 fat strings ``Strings_Full``
    superseded); they are hidden in the .blend but would leak into the GLB."""
    import bpy

    removed = []
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and obj.get("steinway_replaced"):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        print(f"[export] replaced stand-ins stripped: {', '.join(removed)}")
    return removed


def _unhide_all():
    """Clear hide flags on meshes that should join Piano_Static.

    Skips ``steinway_replaced`` retirees (decorative dampers once the action
    damper set exists). Those only export on builds without ``--with-action``,
    where they are not tagged replaced and serve as the static stand-in.
    """
    import bpy

    for obj in bpy.data.objects:
        if obj.get("steinway_replaced"):
            continue
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)


def _is_bench(obj):
    return obj.name in ("Seat_Cushion", "Seat_Frame", "Piano_Bench")


_BENCH_LEG_NAMES = frozenset({"Bench_Leg_01", "Bench_Leg_02", "Bench_Leg_03", "Bench_Leg_04"})

# Lid edge: brass/gold trim and inner wood rim are modeled flush; push trim out and
# wood back slightly so joined GLB does not z-fight in the web viewer.
_LID_TRIM_OUTWARD_M = 0.00025  # 0.25 mm along vertex normals
# Continuous-hinge leaves/screw plate are ~1 mm shells sitting on lacquer. Tier
# the push so each layer clears the one below without the 2 mm lump that caused
# web z-fight (geometry + polygonOffset + DoubleSide was overkill).
_HINGE_TRIM_PUSH = {
    "Long_Continuous_Hinge_Bottom": 0.0006,  # 0.6 mm off lacquer
    "Long_Continuous_Hinge_Top": 0.0006,
    "Long_Continuous_Hinge_Screws": 0.00085,  # screws ride above the leaves
    "Long_Continuous_Hinge_Rod": 0.0004,
}
_LID_WOOD_INWARD_M = 0.00015  # 0.15 mm
_LID_TRIM_OBJECTS = (
    "Brass_Sound_Works.001",
    "Long_Continuous_Hinge_Top",
    "Long_Continuous_Hinge_Bottom",
    "Long_Continuous_Hinge_Rod",
    "Long_Continuous_Hinge_Screws",
)
_HINGE_TRIM_OBJECTS = frozenset({
    "Long_Continuous_Hinge_Top",
    "Long_Continuous_Hinge_Bottom",
    "Long_Continuous_Hinge_Rod",
    "Long_Continuous_Hinge_Screws",
})
_LID_WOOD_OBJECTS = ("Inside_Rim_Case",)

# Harp interior: stays in Piano_Static; tier normal push + distinct brass
# materials (rim vs plate) so the viewer can depth-bias each layer.
_BRIDGE_SEAT_MARK = "steinway_bridge_seated"
_BRIDGE_SEAT_VERSION = 1
_BRIDGE_MIN_CLEARANCE_M = 0.0006   # target gap after seating (meters)

_INTERIOR_TRIM_PUSH = {
    "Soundboard": -0.0015,            # 1.5 mm inset under the seated bridge
    "String_Supports_01": 0.00015,
    "Brass_Sound_Works.002": 0.00045,  # capo / web plate
    "Brass_Sound_Works.001": 0.00055,  # main gold pin-field board
    "Strings_Full": 0.00075,
    "Tuning_Pins": 0.00085,
    "Hitch_Pins": 0.00065,
}

# Lid prop stick — exported separately, re-origined onto the rim hinge by
# build/case.py, so the web viewer can fold it down as the lid closes. The
# hinge hardware (rod, screws, bracket) is the pivot and stays put in
# Piano_Static; the cup rides the lid (see _CASE_MOVING below).
_LID_PROP_PARTS = (
    "Lid_Support_Prop",
)

# Case parts driven by scene props in build/case.py — keep out of Piano_Static.
_CASE_MOVING = frozenset({
    "Fall_Board",
    "Large_Lid_Section",
    "Small_Lid_Section",
    "Long_Continuous_Hinge_Bottom",
    "Long_Continuous_Hinge_Rod",
    "Long_Continuous_Hinge_Screws",
    "Large_Lid_Rubber_Cushions",
    "Long_Continuous_Hinge_Top",
    "Small_Lid_Rubber_Cushions",
    # Parented to the big lid by build/case.py so they swing with it; keep them
    # out of Piano_Static. (Spine butt-hinge leaves + the prop's lid-side cup.)
    "Lid_Butt_Hinge",
    "Lid_Butt_Hinge.001",
    "Lid_Support_Cup",
    *_LID_PROP_PARTS,
})
_CASE_TAGS = {
    "Large_Lid_Section": "lid_big",
    "Lid_Fold_Hinge": "lid_fold_hinge",
    "Fall_Board": "fallboard",
    "Lid_Support_Prop": "lid_prop",
}
_CASE_FOLD_BACK = 3.05
_CASE_FALL_CLOSED = 1.48


def _is_case_moving(obj):
    return obj.name in _CASE_MOVING


def _is_bench_leg(obj):
    return obj.name in _BENCH_LEG_NAMES


def _remove_bench():
    """Drop bench parts so the GLB and viewer frame only the piano."""
    import bpy

    removed = []
    for obj in list(bpy.data.objects):
        if _is_bench(obj):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        print(f"[export] bench removed: {', '.join(removed)}")
    return removed


def _remove_bench_legs():
    """Drop the four bench leg meshes; piano legs and casters stay."""
    import bpy

    removed = []
    for obj in list(bpy.data.objects):
        if obj.type == "MESH" and _is_bench_leg(obj):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        print(f"[export] bench legs removed: {', '.join(removed)}")
    return removed


def _strip_lid_hinge():
    """Remove leftover 0.5.x lid rig so the glTF scene root is not Key_Lid_Hinge."""
    import bpy

    hinge = bpy.data.objects.get("Key_Lid_Hinge")
    if hinge is None:
        return
    for child in list(hinge.children):
        child.parent = None
        for sub in child.children:
            sub.parent = None
    bpy.data.objects.remove(hinge, do_unlink=True)


def _strip_scene_props():
    """Delete non-piano scene meshes (e.g. the ``Floor`` plane / backdrops).

    The source asset is a full scene: a 30x66m ``Floor`` plane is welded into the
    static join, which blows up the glTF bounding box so the web viewer auto-fit
    shrinks the piano to a speck. Drop any non-key / non-pedal mesh that is either
    named ``Floor`` or larger than a real grand piano (> 5m in any axis).
    """
    import bpy

    removed = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH" or _is_key(obj) or _is_pedal(obj):
            continue
        dims = obj.dimensions
        if obj.name == "Floor" or max(dims.x, dims.y, dims.z) > 5.0:
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return removed


def _strip_stray_curves():
    """Delete stray CURVE objects so they don't leak into the export.

    ``_join_static`` only selects ``type == "MESH"``, so Blender curve objects
    skip the static join and the glTF exporter tessellates them into standalone
    meshes (e.g. a flat gold disc that floats above the case rim). No real piano
    part is a curve, so drop them outright.
    """
    import bpy

    removed = []
    for obj in list(bpy.data.objects):
        if obj.type == "CURVE":
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        print(f"[export] stray curves removed: {', '.join(removed)}")
    return removed


def _apply_mesh_scales(names):
    """Bake non-unit object scale into mesh data so glTF local verts are real size.

    Lid rigging (build/case.py) preserves world pose via matrix_parent_inverse but
    leaves hinge trim at ~0.017 / ~0.005 scale. glTF exports that scale on the
    node while the mesh stays in huge local coords — Three.js then renders
    microscopic leaves/screws and only the rod (scale 1) survives.
    """
    import bpy

    applied = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        if all(abs(s - 1.0) < 1e-4 for s in obj.scale):
            continue
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        applied.append(name)
    if applied:
        print(f"[export] baked object scale into mesh: {', '.join(applied)}")
    return applied


def _push_mesh_along_normals(obj, distance):
    """Offset mesh vertices along their normals (edit-mode push/pull)."""
    import bpy

    if obj.type != "MESH" or not obj.data.vertices:
        return False
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.transform.push_pull(value=distance)
    bpy.ops.object.mode_set(mode="OBJECT")
    return True


def _fix_lid_trim_zfight():
    """Separate coplanar lid-edge brass/gold from lacquer and wood before join."""
    import bpy

    moved = []
    for name in _LID_TRIM_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        dist = _HINGE_TRIM_PUSH.get(name, _LID_TRIM_OUTWARD_M)
        if _push_mesh_along_normals(obj, dist):
            moved.append(name)
    for name in _LID_WOOD_OBJECTS:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if _push_mesh_along_normals(obj, -_LID_WOOD_INWARD_M):
            moved.append(f"{name} (inset)")
    if moved:
        print(f"[export] lid trim z-fight offset: {', '.join(moved)}")
    return moved


def _avg_world_normal(obj):
    """Mean face normal in world space (for hinge-leaf separation)."""
    import bmesh
    from mathutils import Vector

    mw = obj.matrix_world.to_3x3()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    acc = Vector((0.0, 0.0, 0.0))
    for face in bm.faces:
        acc += (mw @ face.normal).normalized()
    bm.free()
    return acc.normalized() if acc.length else Vector((0.0, 1.0, 0.0))


def _material_slot_copy(obj, slot, suffix):
    """Give one mesh its own material copy (joined static can bias each slot)."""
    import bpy

    if obj is None or obj.type != "MESH" or slot >= len(obj.material_slots):
        return None
    src = obj.material_slots[slot].material
    if src is None:
        return None
    name = f"{src.name}_{suffix}"
    dup = bpy.data.materials.get(name)
    if dup is None:
        dup = src.copy()
        dup.name = name
    obj.material_slots[slot].material = dup
    return name


def _split_interior_materials():
    """Rim brass vs plate brass share one shader in the .blend — split for depth bias."""
    import bpy

    tagged = []
    pairs = (
        ("Brass_Sound_Works.001", "Rim"),
        ("Brass_Sound_Works.002", "Plate"),
        ("Soundboard", "Soundboard"),
        ("String_Supports_02", "Bridge"),
    )
    for obj_name, suffix in pairs:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        name = _material_slot_copy(obj, 0, suffix)
        if name:
            tagged.append(f"{obj_name}->{name}")
    if tagged:
        print(f"[export] interior material split: {', '.join(tagged)}")
    return tagged


def _world_z_extents(obj):
    from mathutils import Vector

    mw = obj.matrix_world
    zs = [(mw @ Vector(v.co)).z for v in obj.data.vertices]
    return min(zs), max(zs)


def _seat_soundboard_bridge():
    """Lift the bridge off the soundboard if the import left them coplanar."""
    import bpy
    from mathutils import Matrix

    sb = bpy.data.objects.get("Soundboard")
    br = bpy.data.objects.get("String_Supports_02")
    if br is None:
        return None
    if br.get(_BRIDGE_SEAT_MARK, 0) == _BRIDGE_SEAT_VERSION:
        return f"{br.name} (already seated)"
    if sb is not None:
        _, sb_top = _world_z_extents(sb)
        br_bot, _ = _world_z_extents(br)
        gap = br_bot - sb_top
        if gap >= 0.0003:
            br[_BRIDGE_SEAT_MARK] = _BRIDGE_SEAT_VERSION
            return f"{br.name} ({gap * 1000:.2f} mm clearance, no lift)"
        lift = _BRIDGE_MIN_CLEARANCE_M - gap
    else:
        lift = 0.0015
    br.matrix_world = Matrix.Translation((0.0, 0.0, lift)) @ br.matrix_world
    br[_BRIDGE_SEAT_MARK] = _BRIDGE_SEAT_VERSION
    if sb is not None:
        _, sb_top = _world_z_extents(sb)
        br_bot, _ = _world_z_extents(br)
        return (
            f"{br.name} (+{lift * 1000:.2f} mm -> "
            f"{(br_bot - sb_top) * 1000:.2f} mm clearance)"
        )
    return f"{br.name} (+{lift * 1000:.2f} mm)"


def _fix_interior_zfight():
    """Tier soundboard / plate / strings before they are joined into Piano_Static."""
    import bpy

    moved = []
    for name, dist in _INTERIOR_TRIM_PUSH.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if _push_mesh_along_normals(obj, dist):
            moved.append(f"{name} ({dist * 1000:.2f} mm)")
    if moved:
        print(f"[export] interior z-fight offset: {', '.join(moved)}")
    return moved


def _split_hinge_leaves():
    """Separate the top/bottom continuous-hinge leaves along the stack axis.

    The two ~1 mm shells were modeled coplanar (often <0.4 mm apart). Normal
    push moves both sheets equally so they still z-fight — especially in the
    ~15 cm band visible around middle C. Rigid offsets along the bottom-leaf
    normal open a real gap; screws ride slightly further out.
    """
    import bpy
    from mathutils import Matrix

    top = bpy.data.objects.get("Long_Continuous_Hinge_Top")
    bot = bpy.data.objects.get("Long_Continuous_Hinge_Bottom")
    scr = bpy.data.objects.get("Long_Continuous_Hinge_Screws")
    if top is None or bot is None:
        return []
    axis = _avg_world_normal(bot)
    half = 0.0012  # 1.2 mm each way (2.4 mm total leaf gap)
    top.matrix_world = Matrix.Translation(axis * half) @ top.matrix_world
    bot.matrix_world = Matrix.Translation(-axis * half) @ bot.matrix_world
    moved = [top.name, bot.name]
    if scr is not None:
        scr.matrix_world = Matrix.Translation(axis * 0.0016) @ scr.matrix_world
        moved.append(scr.name)
    print(f"[export] hinge leaf stack split: {', '.join(moved)} ({half * 2000:.1f} mm gap)")
    return moved


def _join_static():
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if _is_key(obj) or _is_pedal(obj) or _is_bench(obj) or _is_bench_leg(obj):
            continue
        if _is_case_moving(obj):
            continue
        if _is_action(obj):     # moving parts (with --with-action) stay separate
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


def _lid_tilt(big):
    """Slope of the open lid plane across x (matches build/case.py)."""
    import math
    import mathutils

    mw = big.matrix_world
    cols = {}
    for v in big.data.vertices:
        w = mw @ v.co
        k = round(w.x, 2)
        if k not in cols or w.z < cols[k][1]:
            cols[k] = (w.x, w.z)
    pts = sorted(cols.values())
    (x0, z0), (x1, z1) = pts[0], pts[-1]
    return math.atan2(z1 - z0, x1 - x0)


def _tag_case_parts():
    import bpy

    tagged = []
    for name, part in _CASE_TAGS.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj["case_part"] = part
        tagged.append(name)
    return tagged


def _case_manifest():
    import bpy

    big = bpy.data.objects.get("Large_Lid_Section")
    tilt = round(_lid_tilt(big), 6) if big is not None and big.type == "MESH" else 0.27
    prop = bpy.data.objects.get("Lid_Support_Prop")
    prop_fold = round(float(prop.get("fold_angle", -1.0245)), 6) if prop else -1.0245
    return {
        "lid_tilt": tilt,
        "fold_back": _CASE_FOLD_BACK,
        "fall_closed": _CASE_FALL_CLOSED,
        "prop_fold": prop_fold,
        "nodes": {
            "lid_big": "Large_Lid_Section",
            "lid_fold_hinge": "Lid_Fold_Hinge",
            "fallboard": "Fall_Board",
            "lid_prop": list(_LID_PROP_PARTS),
        },
        "defaults": {
            "lid_open": 1.0,
            "lid_flap_fold": 0.0,
            "fallboard_open": 1.0,
        },
    }


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
        "case": _case_manifest(),
        "defaults": {
            "press_angle_deg": 3.5,
            "snappiness": 1.0,
            "velocity_sensitivity": 1.0,
            "pedal_angle_deg": 5.0,
        },
    }


def _collect_images(node_tree, depth=0, mat_name=""):
    """Gather packed images per PBR role from nested node groups."""
    import bpy

    found = {}
    if node_tree is None or depth > 8:
        return found
    prefer_dapple = "dapple" in mat_name.lower()
    for node in node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            name = node.image.name.lower()
            if "normal" in name and "dapple" not in name:
                found.setdefault("normal", node.image)
            elif "roughness" in name:
                found.setdefault("rough", node.image)
            elif "dapple" in name or "yiksong" in name:
                found["base"] = node.image
            elif "diffuse" in name or "color" in name or "albedo" in name:
                found.setdefault("base", node.image)
            elif not prefer_dapple:
                found.setdefault("base", node.image)
        elif node.type == "GROUP" and node.node_tree:
            for key, img in _collect_images(
                node.node_tree, depth + 1, mat_name
            ).items():
                if key == "base" and prefer_dapple and "dapple" not in img.name.lower():
                    continue
                found.setdefault(key, img)
    return found


def _snapshot_smart_material(nt):
    """Read sy_plastic (and similar) group inputs before the tree is cleared."""
    for node in nt.nodes:
        if node.type != "GROUP" or node.node_tree is None:
            continue
        if not node.node_tree.name.startswith("sy_plastic"):
            continue
        color_in = node.inputs.get("Color")
        rough_in = node.inputs.get("Roughness")
        if color_in is None:
            continue
        color = tuple(color_in.default_value[:3])
        rough = float(rough_in.default_value) if rough_in else 0.5
        return {"color": color, "roughness": rough}
    return None


def _snapshot_material(mat):
    import bpy

    nt = mat.node_tree
    snap = {
        "smart": _snapshot_smart_material(nt),
        "images": _collect_images(nt, mat_name=mat.name),
    }
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        met = bsdf.inputs.get("Metallic")
        if met and not met.is_linked:
            snap["metallic"] = float(met.default_value)
    return snap


def _rebuild_flat_material(mat, snap):
    """Replace deep node trees with Principled + optional image maps."""
    import bpy

    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if snap.get("smart"):
        color = snap["smart"]["color"]
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = snap["smart"]["roughness"]
        # Lacquer: no metal, slight coat on shiny variants.
        if "shiny" in mat.name.lower():
            coat = bsdf.inputs.get("Coat Weight") or bsdf.inputs.get("Clearcoat")
            if coat:
                coat.default_value = 1.0
            coat_r = bsdf.inputs.get("Coat Roughness") or bsdf.inputs.get(
                "Clearcoat Roughness"
            )
            if coat_r:
                coat_r.default_value = 0.05
        return

    images = snap.get("images") or {}
    if "base" in images:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = images["base"]
        tex.image.colorspace_settings.name = "sRGB"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "rough" in images:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = images["rough"]
        tex.image.colorspace_settings.name = "Non-Color"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
    if "normal" in images:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = images["normal"]
        tex.image.colorspace_settings.name = "Non-Color"
        norm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex.outputs["Color"], norm.inputs["Color"])
        nt.links.new(norm.outputs["Normal"], bsdf.inputs["Normal"])
    if snap.get("metallic") is not None:
        bsdf.inputs["Metallic"].default_value = snap["metallic"]
    elif any(k in mat.name.lower() for k in ("gold", "brass", "copper", "steel")):
        bsdf.inputs["Metallic"].default_value = 1.0


def _flatten_materials():
    """Collapse every material to a bare Principled BSDF (fast glTF export).

    The source uses materialiq + sy_plastic node groups that make a full
    ``export_materials="EXPORT"`` crawl take 50+ minutes. We snapshot each
    material's effective inputs first:

    - ``sy_*`` smart lacquer/ivory: procedural (no bitmaps) — copy group Color
      and Roughness into Principled so the GLB is not default gray.
    - Wood / metal / plastic: packed images from the .blend — wire diffuse,
      roughness, and normal into a shallow Principled tree for glTF export.

    The web viewer still refines ``sy_*`` lacquer (scene-utils.js) because
    procedural noise does not survive export; wood/metal can use GLB maps.
    """
    import bpy

    flattened = 0
    for mat in list(bpy.data.materials):
        if not mat.use_nodes or mat.node_tree is None:
            continue
        snap = _snapshot_material(mat)
        _rebuild_flat_material(mat, snap)
        flattened += 1
    return flattened


def main():
    import bpy

    root = _repo_root()
    out_glb = _parse_out(root)
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    manifest_path = os.path.splitext(out_glb)[0] + ".keys.json"

    t0 = time.time()
    _strip_lid_hinge()
    _strip_action(keep="--with-action" in _argv_after_double_dash())
    _strip_replaced()
    _unhide_all()
    stripped = _strip_scene_props()
    _remove_bench()
    _remove_bench_legs()
    _strip_stray_curves()
    _apply_mesh_scales(_CASE_MOVING)
    _fix_lid_trim_zfight()
    _split_hinge_leaves()
    _split_interior_materials()
    seated = _seat_soundboard_bridge()
    if seated:
        print(f"[export] bridge seated on soundboard: {seated}")
    _fix_interior_zfight()
    case_tagged = _tag_case_parts()
    if case_tagged:
        print(f"[export] case parts tagged: {', '.join(case_tagged)}")
    merged = _join_static()
    manifest = _key_manifest()
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    flattened = _flatten_materials()
    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        export_extras=True,
        export_apply=False,
        # Materials are flattened to bare *named* Principled BSDFs just above
        # (_flatten_materials): the source's materialiq / smart-material node
        # groups make a real EXPORT pathologically slow (50+ min). The web viewer
        # re-authors each part by material name (scene-utils.js refineMaterials).
        export_materials="EXPORT",
    )
    print(f"[export] flattened materials: {flattened}")
    size_mb = os.path.getsize(out_glb) / 1e6
    elapsed = time.time() - t0
    print(f"[export] stripped scene props: {stripped}")
    print(f"[export] merged {merged} static meshes -> Piano_Static")
    print(f"[export] keys in manifest: {len(manifest['keys'])}")
    print(f"[export] wrote {out_glb} ({size_mb:.1f} MB, {elapsed:.0f}s)")
    print(f"[export] wrote {manifest_path}")
    print("[export] OK")


if __name__ == "__main__":
    main()