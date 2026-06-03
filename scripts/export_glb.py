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


def _is_bench(obj):
    return obj.name in ("Seat Cushion", "Seat Frame")


def _fix_bench_cushion_materials():
    """Dapple only on the top face; sides get sy_dark_shiny like the frame.

    Flattened glTF UVs on vertical faces turn the dapple tile into piano-key
    stripes in Three.js. Blender hides this via cw-scale node groups.
    """
    import bpy
    import bmesh

    obj = bpy.data.objects.get("Seat Cushion")
    dark = bpy.data.materials.get("sy_dark_shiny")
    if obj is None or obj.type != "MESH" or dark is None:
        return False

    mesh = obj.data
    dapple_idx = None
    for i, slot in enumerate(obj.material_slots):
        if slot.material and "dapple" in slot.material.name.lower():
            dapple_idx = i
            break
    if dapple_idx is None:
        return False

    if dark.name not in [s.material.name for s in obj.material_slots if s.material]:
        mesh.materials.append(dark)
    dark_idx = next(
        i for i, s in enumerate(obj.material_slots) if s.material and s.material == dark
    )

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    top = 0
    side = 0
    for face in bm.faces:
        if face.normal.z > 0.85:
            face.material_index = dapple_idx
            top += 1
        else:
            face.material_index = dark_idx
            side += 1
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    print(f"[export] bench cushion: {top} top (dapple), {side} side (lacquer) faces")
    return True


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


def _join_static():
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    targets = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if _is_key(obj) or _is_pedal(obj) or _is_bench(obj):
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
    elif "dapple" in mat.name.lower() and "base" in images:
        # Cushion: export diffuse only. Baking dapple into a glTF normal map reads as
        # horizontal stripes in Three.js (false keyboard-like ridges).
        bsdf.inputs["Roughness"].default_value = 0.38
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
    stripped = _strip_scene_props()
    _fix_bench_cushion_materials()
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


main()