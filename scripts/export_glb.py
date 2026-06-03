"""Export the prepared Steinway .blend to a web-ready GLB (+ key manifest).

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py
    $B --background assets/steinway_grand_playable.blend --python scripts/export_glb.py -- \\
        --out web/public/models/steinway.glb

Pipeline (source of truth: ``assets/steinway_grand_playable.blend``):

1. Strip scene props (Floor, oversized meshes).
2. **Bench** — apply object scale; replace only the cushion with a bound-box solid
   (source mesh is wavy in local space); keep frame geometry; join as
   ``Piano_Bench``.
3. **Body** — join remaining static meshes into ``Piano_Static``.
4. Flatten materials to fast Principled trees; export GLB. Web viewer refines by
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


def _is_bench(obj):
    return obj.name in ("Seat Cushion", "Seat Frame", "Piano_Bench")


def _apply_mesh_transforms(obj):
    """Bake non-uniform object scale into mesh data (glTF scale nodes deform the bench)."""
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def _solidify_bench_cushion(obj):
    """Swap wavy high-res cushion mesh for a solid box in its bound_box (after scale apply).

    Source cushion carries ~2 m of folded geometry in local Z; baking non-uniform
    scale leaves 5–7 cm ripples that read as spikes in glTF. The box is fit to
    ``bound_box`` so the object origin stays put (contrast with a center-origin cube).
    """
    import bpy
    import bmesh
    from mathutils import Vector

    dapple = bpy.data.materials.get("CW-Plastic-Dapple")
    dark = bpy.data.materials.get("sy_dark_shiny")
    if dapple is None or dark is None:
        return False

    corners = [Vector(c) for c in obj.bound_box]
    mn = Vector([min(c[i] for c in corners) for i in range(3)])
    mx = Vector([max(c[i] for c in corners) for i in range(3)])
    dims = mx - mn
    if min(dims) < 0.01:
        return False

    new_mesh = bpy.data.meshes.new("SeatCushionSolid")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x = mn.x + (vert.co.x + 0.5) * dims.x
        vert.co.y = mn.y + (vert.co.y + 0.5) * dims.y
        vert.co.z = mn.z + (vert.co.z + 0.5) * dims.z
    bm.faces.ensure_lookup_table()
    new_mesh.materials.append(dapple)
    new_mesh.materials.append(dark)
    for face in bm.faces:
        face.material_index = 0 if face.normal.z > 0.9 else 1
    bm.to_mesh(new_mesh)
    bm.free()
    for poly in new_mesh.polygons:
        poly.use_smooth = True

    old = obj.data
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)
    print(
        f"[export] bench cushion: solid box {dims.x:.2f}x{dims.y:.2f}x{dims.z:.2f} m"
    )
    return True


def _prepare_bench_export():
    """One ``Piano_Bench`` object: real meshes, baked scale, web-safe materials.

    Prior attempts replaced the cushion with a centered cube (wrong local origin →
    bench vanished) or left ``Seat Frame`` scale at 0.13 on an axis (squashed legs).
    """
    import bpy

    parts = []
    for name in ("Seat Cushion", "Seat Frame"):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        for mod in list(obj.modifiers):
            obj.modifiers.remove(mod)
        _apply_mesh_transforms(obj)
        if name == "Seat Cushion":
            _solidify_bench_cushion(obj)
        elif hasattr(obj.data, "shade_smooth"):
            obj.data.shade_smooth()
        parts.append(obj)

    if not parts:
        print("[export] bench: no Seat Cushion / Seat Frame found")
        return False

    if len(parts) == 1:
        parts[0].name = "Piano_Bench"
        bench = parts[0]
    else:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in parts:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        bpy.ops.object.join()
        bench = bpy.context.active_object
        bench.name = "Piano_Bench"

    bench["steinway_role"] = "bench"
    dims = bench.dimensions
    print(
        f"[export] bench: {bench.name} {dims.x:.2f}x{dims.y:.2f}x{dims.z:.2f} m, "
        f"{len(bench.data.polygons)} faces"
    )
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
    _prepare_bench_export()
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