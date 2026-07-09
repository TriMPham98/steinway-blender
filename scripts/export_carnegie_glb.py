"""Export the Carnegie Hall set to a web-ready GLB (+ placement meta).

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/carnegie_hall.blend --python scripts/export_carnegie_glb.py
    $B --background assets/carnegie_hall.blend --python scripts/export_carnegie_glb.py -- \\
        --out web/public/models/carnegie_hall.glb

The hall is authored with the stage top at world Z=0 so the web piano
(frameModel-grounded at Y=0) sits on stage without a scale-to-fit pass.
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
        out = os.path.join(root, "web", "public", "models", "carnegie_hall.glb")
    if not os.path.isabs(out):
        out = os.path.join(root, out)
    return out


def main():
    import bpy
    from mathutils import Vector

    t0 = time.time()
    root = _repo_root()
    out_glb = _parse_out(root)
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    meta_path = os.path.splitext(out_glb)[0] + ".meta.json"

    # Drop cameras / empties / lights — web rebuilds lighting; keep meshes only.
    removed = []
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            removed.append(f"{obj.type}:{obj.name}")
            bpy.data.objects.remove(obj, do_unlink=True)
    if removed:
        print(f"[carnegie-export] stripped non-mesh: {', '.join(removed)}")

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("[carnegie-export] no mesh objects to export")

    total_v = sum(len(o.data.vertices) for o in meshes)
    total_f = sum(len(o.data.polygons) for o in meshes)
    print(f"[carnegie-export] meshes={len(meshes)} verts={total_v} faces={total_f}")
    if total_f > 30000:
        print(f"[carnegie-export] WARNING: face count {total_f} exceeds 30k budget")

    # Stage top in authoring space (Blender Z-up). Prefer Stage_Floor max Z.
    stage = bpy.data.objects.get("Stage_Floor")
    if stage is not None:
        tops = [(stage.matrix_world @ Vector(c)).z for c in stage.bound_box]
        stage_top_z = max(tops)
    else:
        stage_top_z = 0.0
        print("[carnegie-export] WARNING: Stage_Floor missing; stage_top_z=0")

    all_bb = []
    for o in meshes:
        for c in o.bound_box:
            all_bb.append(o.matrix_world @ Vector(c))
    xs = [v.x for v in all_bb]
    ys = [v.y for v in all_bb]
    zs = [v.z for v in all_bb]
    bounds_blender = {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }

    # Select everything remaining and export.
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=out_glb,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
        export_materials="EXPORT",
        export_yup=True,
    )

    size_mb = os.path.getsize(out_glb) / 1e6
    # glTF Y-up: Blender (x,y,z) → (x,z,-y). Stage top Z becomes world Y.
    meta = {
        "source": "assets/carnegie_hall.blend",
        "stage_top_blender_z": round(stage_top_z, 4),
        "stage_top_gltf_y": round(stage_top_z, 4),
        "bounds_blender": bounds_blender,
        "mesh_count": len(meshes),
        "vertex_count": total_v,
        "face_count": total_f,
        "camera_far_hint": 120,
        "notes": (
            "Place hall with stage top at Y=0 under the frameModel-grounded piano. "
            "Do not run frameModel/scale-to-fit on the hall root."
        ),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    elapsed = time.time() - t0
    print(f"[carnegie-export] wrote {out_glb} ({size_mb:.2f} MB, {elapsed:.1f}s)")
    print(f"[carnegie-export] wrote {meta_path}")
    print(f"[carnegie-export] stage_top_z={stage_top_z:.4f}")
    print("[carnegie-export] OK")


if __name__ == "__main__":
    main()
