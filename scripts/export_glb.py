"""Export the prepared Steinway .blend to a web-ready GLB (+ key manifest).

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py -- \\
        --out web/public/models/steinway.glb --with-action

Pipeline (source of truth: ``assets/steinway_grand_playable.blend``):

1. Strip scene props (Floor, oversized meshes).
2. **Bench** — remove ``Seat Cushion``, ``Seat Frame``, and any ``Piano_Bench``.
3. **Bench legs** — remove the four bench leg meshes (``Leg-01`` … ``Leg-04``) only.
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
    """Clear hide flags so view-hidden keepers (e.g. the decorative damper
    meshes, which stand in for the stripped moving dampers) join and export."""
    import bpy

    for obj in bpy.data.objects:
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)


def _is_bench(obj):
    return obj.name in ("Seat Cushion", "Seat Frame", "Piano_Bench")


_BENCH_LEG_NAMES = frozenset({"Leg-01", "Leg-02", "Leg-03", "Leg-04"})

# Lid edge: brass/gold trim and inner wood rim are modeled flush; push trim out and
# wood back slightly so joined GLB does not z-fight in the web viewer.
_LID_TRIM_OUTWARD_M = 0.00025  # 0.25 mm along vertex normals
_LID_WOOD_INWARD_M = 0.00015  # 0.15 mm
_LID_TRIM_OBJECTS = (
    "Brass_Sound_Works.001",
    "Brass_Sound_Works.002",
    "Long Continuos Hinge TOP",
    "Long Continuos Hinge BOTTOM",
    "Long Continous Hinge ROD",
    "Long Continous Hinge Screws",
)
_LID_WOOD_OBJECTS = ("Inside Rim Case",)


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
        if _push_mesh_along_normals(obj, _LID_TRIM_OUTWARD_M):
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


def _join_static():
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if _is_key(obj) or _is_pedal(obj) or _is_bench(obj) or _is_bench_leg(obj):
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
    _fix_lid_trim_zfight()
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