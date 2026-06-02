"""Low-level Blender geometry + material helpers shared by keyboard.py and case.py.

Pure bpy/bmesh, no MIDI. Everything here is safe to import and run headless.
"""

import bpy
import bmesh


# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #
def ensure_collection(name):
    """Return a scene collection with `name`, creating + linking it if needed."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_collection(name):
    """Remove a collection and every object inside it (idempotent rebuilds)."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for scene in bpy.data.scenes:
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
    bpy.data.collections.remove(coll)


# --------------------------------------------------------------------------- #
# Meshes
# --------------------------------------------------------------------------- #
def _finalize(bm, name):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return me


def box_mesh(name, x0, x1, y0, y1, z0, z1):
    """Axis-aligned box from two opposite corners, outward normals."""
    bm = bmesh.new()
    v = [
        bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0)),
        bm.verts.new((x1, y1, z0)), bm.verts.new((x0, y1, z0)),
        bm.verts.new((x0, y0, z1)), bm.verts.new((x1, y0, z1)),
        bm.verts.new((x1, y1, z1)), bm.verts.new((x0, y1, z1)),
    ]
    for a, b, c, d in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                       (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
        bm.faces.new((v[a], v[b], v[c], v[d]))
    return _finalize(bm, name)


def extruded_polygon(name, points2d, z0, z1):
    """Build a flat ngon from `points2d` at z0 and extrude it up to z1 (solid slab)."""
    bm = bmesh.new()
    ring = [bm.verts.new((x, y, z0)) for (x, y) in points2d]
    face = bm.faces.new(ring)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0.0, 0.0, z1 - z0), verts=moved)
    return _finalize(bm, name)


def cone_mesh(name, r_bottom, r_top, depth, segments=20):
    """Vertical (Z-axis) cone/cylinder centered on the origin, height `depth`."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, segments=segments,
        radius1=r_bottom, radius2=r_top, depth=depth,
    )
    return _finalize(bm, name)


# --------------------------------------------------------------------------- #
# Objects + materials
# --------------------------------------------------------------------------- #
def new_object(name, mesh, collection, location=(0.0, 0.0, 0.0)):
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    collection.objects.link(obj)
    return obj


def get_material(name, color, roughness=0.4, metallic=0.0):
    """Get/create a Principled BSDF material (idempotent by name)."""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (color[0], color[1], color[2], 1.0)  # solid/Workbench viewport color
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
