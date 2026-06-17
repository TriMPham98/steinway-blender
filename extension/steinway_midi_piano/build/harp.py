"""Open the plate's bays and fit the full pin set (one peg per string).

Two fixes to the imported harp:

**Plate bays.** ``Brass_Sound_Works.002`` models its front section as one giant
flat n-gon at z = 0.850 reaching back to y = -0.392 - solid gold under the whole
strike band and damper band, where a real Steinway plate ends at the capo bar
with open bays behind it. The builder bisects that single face along the capo
line (just in front of the hammer strike line) and deletes the rear portion, so
hammers and damper wires work in open air over the soundboard, exactly like the
real plate. The struts and raised bars above the web are untouched.

**Pins.** The stand-in pin field served 51 strings. This builds one tuning pin
per physical string (225 for the Model-O-style scale; straight ranks parallel
to the strike line with the rank cycling pin-to-pin - the diagonal lattice of
a real pin field - with each string's front end already run to its pin by
``strings.course_lines``) plus one hitch pin per course at the rear. The old
``String_Pins`` mesh is hidden and tagged ``steinway_replaced``.

Run after ``build/strings.py``. Pure ``bpy``/``bmesh``, headless, idempotent.
"""

import bmesh
import bpy
from mathutils import Vector

from . import action as action_mod
from . import strings as strings_mod

PLATE = "Brass_Sound_Works.002"
OLD_PINS = "String_Pins"
TUNING_PINS = "Tuning_Pins"
HITCH_PINS = "Hitch_Pins"
CAPO_MARK = "steinway_capo_cut"
CAPO_VERSION = 4
CAPO_SETBACK = 0.018     # capo (web cut) line sits this far in front of strike
LIP_TRIM = 0.016         # raised front-slab rear edge: this far behind strike
PIN_TRIM = (strings_mod.RANK_REL0
            - (strings_mod.RANKS - 1) * strings_mod.RANK_PITCH - 0.005)

PIN_R = strings_mod.PIN_R
PIN_LEN = 0.032          # exposed pin above the local plate surface
HITCH_R = 0.0018
WEB_Z = (0.868, 0.882)   # flat pin-field top (raised bars/struts sit above)


def _capo_line():
    """Strike-line fit (a, b) shifted toward the player by CAPO_SETBACK."""
    keys = action_mod._keys_sorted()
    plan = action_mod._plan(keys, action_mod._measure(keys))
    a, b = plan["line"]
    return a - CAPO_SETBACK, b


def _trim_damper_lip(bm, mw, a, b):
    """Trim the raised front slab to a straight edge behind the strike line.

    Besides the z=0.850 floor, the model's front section carries a thin raised
    slab (underside ~z 0.892, deck ~z 0.916) whose jagged rear edge overhangs
    the damper band - the strings even pierce its underside skin. Real plates
    end at the capo bar, so the damper heads must work in open air: bisect the
    slab along a line parallel to the strike fit, drop everything behind it,
    and wall up the open cross-section.

    The slab is collected by flood fill from its underside skin, fenced to
    z above the (already removed) bay floor and to the strike line's
    neighborhood so the struts crossing toward the rear are never touched.
    """
    inv3 = mw.to_3x3().transposed()

    def rel(p):
        return p.y - (a + b * p.x)

    centers = {}
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        centers[f] = (c, rel(c), (mw.to_3x3() @ f.normal).normalized().z)
    seeds = [f for f, (c, r, nz) in centers.items()
             if nz < -0.7 and 0.886 < c.z < 0.901 and -0.06 < r < 0.16]
    if not seeds:
        return 0
    slab = set(seeds)
    queue = list(seeds)
    while queue:
        f = queue.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g in slab:
                    continue
                c, r, _nz = centers[g]
                if 0.8855 < c.z < 0.93 and -0.06 < r < 0.16:
                    slab.add(g)
                    queue.append(g)
    mat_idx = seeds[0].material_index

    geom = list(slab)
    vs, es = set(), set()
    for f in slab:
        vs.update(f.verts)
        es.update(f.edges)
    geom += list(vs) + list(es)
    plane_no = (inv3 @ Vector((-b, 1.0, 0.0))).normalized()
    bmesh.ops.bisect_plane(
        bm, geom=geom,
        plane_co=mw.inverted() @ Vector((0.0, a + LIP_TRIM, 0.9)),
        plane_no=plane_no,
        clear_outer=True)

    # The slab also cantilevers forward over the pin field (rogue pins sat on
    # its underside ~0.91 with nothing below). Drop everything from the rear
    # pin rank toward the strike line so the web stays open like a real plate.
    geom = list(slab)
    vs, es = set(), set()
    for f in slab:
        if not f.is_valid:
            continue
        vs.update(f.verts)
        es.update(f.edges)
    geom = [f for f in slab if f.is_valid] + list(vs) + list(es)
    if geom:
        bmesh.ops.bisect_plane(
            bm, geom=geom,
            plane_co=mw.inverted() @ Vector((0.0, a + PIN_TRIM, 0.9)),
            plane_no=plane_no,
            clear_outer=True)

    # Close the slab's open cross-section: the deck and the underside skin
    # are separate sheets, so the cut leaves two boundary rims facing each
    # other - bridge them into a rear wall.
    lip = []
    for e in bm.edges:
        if e.is_boundary:
            ws = [mw @ v.co for v in e.verts]
            if all(abs(rel(w) - LIP_TRIM) < 0.002 and 0.8855 < w.z < 0.93
                   for w in ws):
                lip.append(e)
    new = []
    if lip:
        try:
            new = bmesh.ops.bridge_loops(bm, edges=lip)["faces"]
        except RuntimeError:  # loop fragments bridge_loops cannot pair
            new = []
    for f in new:
        f.material_index = mat_idx
    if new:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return len(new)


def _cut_plate_bays():
    """Open the bays: the model fakes a gold floor under the whole harp as
    flat sheets at z ~0.850 (plus the big pin-field n-gon). Everything behind
    the capo line goes; a real plate is open between its struts."""
    plate = bpy.data.objects.get(PLATE)
    if plate is None:
        return "missing"
    if plate.get(CAPO_MARK, 0) == CAPO_VERSION:
        return "already-cut"
    a, b = _capo_line()
    mw = action_mod._world_matrix(plate)
    bm = bmesh.new()
    bm.from_mesh(plate.data)
    bm.faces.ensure_lookup_table()
    if not plate.get(CAPO_MARK):
        # First pass: bisect the big pin-field n-gon along the capo line so
        # its front (under the pins) survives the sheet purge below.
        web = max(bm.faces, key=lambda f: f.calc_area())
        co_l = mw.inverted() @ Vector((0.0, a, 0.85))
        no_l = (mw.to_3x3().transposed()
                @ Vector((-b, 1.0, 0.0))).normalized()
        geom = [web] + list(web.verts) + list(web.edges)
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co_l, plane_no=no_l)
        bm.faces.ensure_lookup_table()
    rear = []
    for f in bm.faces:
        n = (mw.to_3x3() @ f.normal).normalized()
        c = mw @ f.calc_center_median()
        if abs(n.z) > 0.9 and 0.8495 <= c.z <= 0.8506 and c.y > a + b * c.x + 1e-5:
            rear.append(f)
    bmesh.ops.delete(bm, geom=rear, context="FACES")
    walled = _trim_damper_lip(bm, mw, a + CAPO_SETBACK, b)
    bm.to_mesh(plate.data)
    bm.free()
    plate.data.update()
    plate[CAPO_MARK] = CAPO_VERSION
    return (f"cut v{CAPO_VERSION} ({len(rear)} floor faces removed, "
            f"lip walled with {walled} faces)")


def _pin_material():
    old = bpy.data.objects.get(OLD_PINS)
    if old is not None and old.data.materials and old.data.materials[0]:
        return old.data.materials[0]
    return strings_mod._steel_material()


def _make_pins(courses):
    for name in (TUNING_PINS, HITCH_PINS):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            me = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)

    mat = _pin_material()
    src = bpy.data.objects.get(OLD_PINS)
    coll = (src.users_collection[0] if src is not None and src.users_collection
            else bpy.context.scene.collection)

    def cyl(verts, faces, cx, cy, r, z0, z1, n=8):
        import math
        base = len(verts)
        for z in (z0, z1):
            for k in range(n):
                t = 2.0 * math.pi * k / n
                verts.append((cx + r * math.cos(t), cy + r * math.sin(t), z))
        for k in range(n):
            faces.append((base + k, base + (k + 1) % n,
                          base + n + (k + 1) % n, base + n + k))
        faces.append(tuple(base + k for k in range(n - 1, -1, -1)))
        faces.append(tuple(base + n + k for k in range(n)))

    # Pins stand on the plate's visible top surface (probed per pin: the
    # field is at z ~0.878, not the 0.850 underside sheet).
    bvh = strings_mod._plate_bvh()
    down = Vector((0.0, 0.0, -1.0))

    def surface(px, py):
        """Local plate top under a pin spot.

        Peel through overlays (the damper-lip slab ~0.91 sits over part of the
        pin field) and prefer the flat web. Spots with no flat web underneath
        still stand on raised bars/struts rather than buried inside them.
        """
        if bvh is None:
            return 0.878
        origin = Vector((px, py, 0.95))
        raised = None
        for _ in range(12):
            hit = bvh.ray_cast(origin, down, 0.15)
            if hit[0] is None or hit[0].z < 0.84:
                break
            z = hit[0].z
            if WEB_Z[0] <= z <= WEB_Z[1]:
                return z
            raised = z
            # Drop straight below (px, py): hit points drift on sloped faces and
            # a tiny offset along the ray never peels through thin overlays.
            origin = Vector((px, py, hit[0].z - 0.002))
        return raised if raised is not None else 0.878

    tv, tf = [], []
    tuning = 0
    for c in courses:
        d = (c["R"] - c["F"])
        dirxy = Vector((d.x, d.y, 0.0)).normalized()
        for F_k, _R_k in c["unisons"]:
            p = F_k - dirxy * PIN_R          # string end wraps the pin's side
            surf = surface(p.x, p.y)
            cyl(tv, tf, p.x, p.y, PIN_R, surf - 0.002, surf + PIN_LEN)
            cyl(tv, tf, p.x, p.y, PIN_R + 0.0006,
                surf + PIN_LEN - 0.004, surf + PIN_LEN)
            tuning += 1

    hv, hf = [], []
    for c in courses:
        R = c["R"]
        cyl(hv, hf, R.x, R.y, HITCH_R, R.z - 0.012, R.z + 0.005, n=6)

    for name, verts, faces in ((TUNING_PINS, tv, tf), (HITCH_PINS, hv, hf)):
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.materials.append(mat)
        me.validate()
        me.update()
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)

    if src is not None:
        action_mod._hide_keep(src)
        src[strings_mod.REPLACED_PROP] = 1
    return tuning


def build():
    cut = _cut_plate_bays()
    courses = strings_mod.course_lines()
    tuning = _make_pins(courses)
    return {
        "plate": cut,
        "tuning_pins": tuning,
        "hitch_pins": len(courses),
    }
