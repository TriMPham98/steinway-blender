"""Complete the model's string set: 88 unison courses in the original fan.

The imported model ships 51 identical fat copper strings (~3.2 mm, one per
decorative damper) spread across the harp - a stylized stand-in. A real grand
of this footprint (1.77 m: a Steinway Model O scale) carries ~88 courses:
wound monochords low, wound bichords through the bass fan, and plain-steel
trichords above the section break, with gauges tapering toward the treble.

This builder replaces the stand-ins with a full set that keeps the model's own
geometry: each existing string contributes a sample of the fan (front/pin end,
rear/hitch end, height), and every new course is interpolated from those
samples so it lands on the same pin field, hitch line, and string plane. Each
course is anchored at its key's x on the hammer strike line, so every hammer
of the double-escapement action sits under its own unisons.

Sections follow the model's physical layout (its bass fan is wider than a
textbook scale): the bass/treble break falls where the model's two fans split,
at note 50 (C#3):

- notes 21-30: wound copper monochords (r 1.5 -> 1.3 mm)
- notes 31-49: wound copper bichords  (r 1.15 -> 0.9 mm)
- notes 50-108: plain steel trichords (r 0.65 -> 0.42 mm)

The original ``Strings`` object stays in the file for measurement and as the
source of truth, but is hidden and tagged ``steinway_replaced`` (the GLB export
strips it; the new ``Strings_Full`` object joins the static piano instead).

Pure ``bpy`` (no ``bpy.ops``), headless-safe, idempotent.
"""

import math

import bpy
from mathutils import Vector

from . import retarget
from . import action as action_mod

SOURCE = "Strings"
OUTPUT = "Strings_Full"
REPLACED_PROP = "steinway_replaced"

BREAK_NOTE = 50          # first plain-steel trichord (the model's fan gap)
MONO_TOP = 30            # last monochord note
SECTIONS = {
    "mono": {"count": 1, "spread": 0.0, "r": (0.00150, 0.00130)},
    "bi": {"count": 2, "spread": 0.0030, "r": (0.00115, 0.00090)},
    "tri": {"count": 3, "spread": 0.0044, "r": (0.00065, 0.00042)},
}

STEEL_MAT = "Strings_Steel"
COPPER, STEEL = 0, 1
PIN_R = 0.0032           # tuning pin radius (build/harp.py builds the pins)
RANKS = 4                # pin ranks (rows parallel to the strike line)
RANK_REL0 = -0.030       # first rank: this far in front of the strike line
RANK_PITCH = 0.025       # rank-to-rank spacing (flat web ends near -0.130)
# Raised plate struts (top ~0.916) cross the pin field; pins that land on or
# beside them must slide along the rank onto clear web rather than bury into
# the brass. Clearance is probed at mid-strut height with a small margin.
PIN_CLEAR_Z = 0.890
# Cover the pin head (harp builds it at PIN_R + 0.0006) plus a small gap.
PIN_CLEAR_MARGIN = 0.0012
PIN_NUDGE_MAX = 0.015    # max slide along the rank (metres)
WEB_Z = (0.868, 0.882)   # flat pin-field top (matches build/harp.py)


def _section_of(note):
    if note < BREAK_NOTE:
        return "mono" if note <= MONO_TOP else "bi"
    return "tri"


# --------------------------------------------------------------------------- #
# Measure the existing fan
# --------------------------------------------------------------------------- #
def _string_samples():
    """Per existing string: front mean, rear mean, sorted into bass/main fans.

    Bass strings run overstrung toward the rear-right (rear x well past front
    x); everything else (crossing tenor + straight treble) forms one
    continuous 'main' fan.
    """
    obj = bpy.data.objects.get(SOURCE)
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"'{SOURCE}' mesh not found - open the Steinway model")
    me = obj.data
    mw = action_mod._world_matrix(obj)
    comps = retarget._components(me)
    if len(comps) < 10:
        raise RuntimeError(f"'{SOURCE}' split into {len(comps)} strings - unexpected model")

    bass, main = [], []
    for c in comps:
        pts = [mw @ me.vertices[i].co for i in c]
        ymin = min(p.y for p in pts)
        ymax = max(p.y for p in pts)
        front = [p for p in pts if p.y < ymin + 0.004]
        rear = [p for p in pts if p.y > ymax - 0.004]
        F = sum(front, Vector()) / len(front)
        R = sum(rear, Vector()) / len(rear)
        (bass if (R.x - F.x) > 0.1 else main).append((F, R))
    bass.sort(key=lambda fr: fr[0].x)
    main.sort(key=lambda fr: fr[0].x)
    return bass, main


def _anchor_x(F, R, a, b):
    """X where the segment F->R crosses the strike line y = a + b*x."""
    d = R - F
    denom = d.y - b * d.x
    t = (a + b * F.x - F.y) / denom
    return (F + t * d).x, t


def _course_endpoints(fan, anchors, x):
    """Front/rear for a course anchored at strike-line x, lerped from the fan."""
    n = len(fan)
    if x <= anchors[0]:
        i, j, t = 0, 1, (x - anchors[0]) / (anchors[1] - anchors[0])
    elif x >= anchors[-1]:
        i, j = n - 2, n - 1
        t = 1.0 + (x - anchors[-1]) / (anchors[-1] - anchors[-2])
    else:
        j = next(k for k in range(1, n) if anchors[k] >= x)
        i = j - 1
        t = (x - anchors[i]) / (anchors[j] - anchors[i])
    F = fan[i][0].lerp(fan[j][0], t)
    R = fan[i][1].lerp(fan[j][1], t)
    return F, R


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _hex_string(buf_v, buf_f, buf_m, F, R, r, mat):
    """Hexagonal prism from F to R with radius r (verts/faces into the bufs)."""
    d = (R - F).normalized()
    side = d.cross(Vector((0.0, 0.0, 1.0))).normalized()
    up = side.cross(d).normalized()
    base = len(buf_v)
    for origin in (F, R):
        for k in range(6):
            ang = math.pi / 3.0 * k
            buf_v.append(origin + (side * math.cos(ang) + up * math.sin(ang)) * r)
    for k in range(6):
        buf_f.append((base + k, base + (k + 1) % 6,
                      base + 6 + (k + 1) % 6, base + 6 + k))
        buf_m.append(mat)
    buf_f.append(tuple(base + k for k in range(5, -1, -1)))
    buf_f.append(tuple(base + 6 + k for k in range(6)))
    buf_m += [mat, mat]


def _steel_material():
    mat = bpy.data.materials.get(STEEL_MAT)
    if mat is None:
        mat = bpy.data.materials.new(STEEL_MAT)
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (0.75, 0.76, 0.78, 1.0)
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.25
        mat.diffuse_color = (0.75, 0.76, 0.78, 1.0)
    return mat


# --------------------------------------------------------------------------- #
# Damper re-seating (the decorative damper units rode the fat stand-ins)
# --------------------------------------------------------------------------- #
def _damper_units():
    """Cluster the joined damper meshes into per-unit component groups by x."""
    comps_all = []
    for name in ("Dampers_Tops", "Dampers_Bottoms"):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            return []
        mw = action_mod._world_matrix(obj)
        me = obj.data
        for c in retarget._components(me):
            pts = [mw @ me.vertices[i].co for i in c]
            comps_all.append({
                "obj": obj, "idx": c,
                "cx": sum(p.x for p in pts) / len(pts),
                "cy": sum(p.y for p in pts) / len(pts),
                "zmin": min(p.z for p in pts),
                "is_felt": name == "Dampers_Bottoms",
            })
    comps_all.sort(key=lambda d: d["cx"])
    units = []
    for d in comps_all:
        if units and d["cx"] - units[-1][-1]["cx"] < 0.008:
            units[-1].append(d)
        else:
            units.append([d])
    return units


def _reseat_dampers(courses):
    """Snap each damper unit onto its nearest new course and seat the felts.

    The stand-in strings were ~3.2 mm thick and ~24 mm apart; the real courses
    are thinner and at per-note positions, so each unit shifts sideways to the
    nearest course center line and drops until its felt grazes the string top.
    """
    units = _damper_units()
    if not units:
        return None
    moved, max_dx, max_dz = 0, 0.0, 0.0
    shifts = {}                      # obj -> {vert_index: world shift}
    for unit in units:
        ux = sum(d["cx"] for d in unit) / len(unit)
        uy = sum(d["cy"] for d in unit) / len(unit)
        felt_zmin = min((d["zmin"] for d in unit if d["is_felt"]),
                        default=min(d["zmin"] for d in unit))
        crossing = []                # (course x, string top z) at the unit's y
        for c in courses:
            F, R, r = c["F"], c["R"], c["r"]
            t = (uy - F.y) / (R.y - F.y)
            if not (0.0 <= t <= 1.0):
                continue
            crossing.append((F.x + t * (R.x - F.x), F.z + t * (R.z - F.z) + r))
        if not crossing:
            continue
        nearest_x = min(crossing, key=lambda cz: abs(cz[0] - ux))[0]
        dx = max(-0.012, min(0.012, nearest_x - ux))
        # Seat on the highest course under the footprint (overstrung crossings:
        # the felt must not sink through the upper string layer).
        under = [z for cx, z in crossing if abs(cx - (ux + dx)) <= 0.011]
        dz = (max(under) + 0.0002) - felt_zmin
        shift = Vector((dx, 0.0, dz))
        for d in unit:
            dest = shifts.setdefault(d["obj"].name, {})
            for i in d["idx"]:
                dest[i] = shift
        moved += 1
        max_dx = max(max_dx, abs(dx))
        max_dz = max(max_dz, abs(dz))
    for name, table in shifts.items():
        obj = bpy.data.objects[name]
        inv = action_mod._world_matrix(obj).inverted().to_3x3()
        me = obj.data
        for i, shift in table.items():
            me.vertices[i].co += inv @ shift
        me.update()
    return {"units": moved, "max_dx_mm": round(max_dx * 1000, 2),
            "max_dz_mm": round(max_dz * 1000, 2)}


def _plate_bvh():
    obj = bpy.data.objects.get("Brass_Sound_Works.002")
    if obj is None or obj.type != "MESH":
        return None
    from mathutils.bvhtree import BVHTree
    mw = action_mod._world_matrix(obj)
    return BVHTree.FromPolygons(
        [tuple(mw @ v.co) for v in obj.data.vertices],
        [tuple(p.vertices) for p in obj.data.polygons])


def _on_rank(front, dirxy, a, b, rank):
    """Point where the string's plan-view line crosses pin rank ``rank``.

    Ranks are straight lines parallel to the strike line (rel = y - (a+b*x)
    constant), so the whole pin field reads as even rows with the classic
    diagonal lattice, like a real plate - instead of distances measured from
    each string's own (ragged) front end.
    """
    rel = RANK_REL0 - RANK_PITCH * rank
    t = ((front.y - b * front.x) - (a + rel)) / (dirxy.y - b * dirxy.x)
    return front - dirxy * t


def _pin_side_clear(bvh, cx, cy):
    """Min plan distance from (cx, cy) to plate mesh at mid-strut height.

    Returns ``(distance, outward_dir_or_None)``. Distance is huge when no plate
    is within the probe radius (open web).
    """
    if bvh is None:
        return 1.0, None
    origin = Vector((cx, cy, PIN_CLEAR_Z))
    best_d, best_n = 1.0, None
    for k in range(32):
        ang = 2.0 * math.pi * k / 32.0
        d = Vector((math.cos(ang), math.sin(ang), 0.0))
        hit = bvh.ray_cast(origin, d, 0.025)
        if hit[0] is None:
            continue
        dist = (hit[0] - origin).length
        if dist < best_d:
            best_d, best_n = dist, d
    return best_d, best_n


def _pin_footprint_on_web(bvh, cx, cy, r=PIN_R):
    """True when the pin's full footprint rests on the flat pin-field web.

    Raised strut tops (~0.916) fail this, so a pin is never left sitting under
    brass that its shaft would have to pierce.
    """
    if bvh is None:
        return True
    down = Vector((0.0, 0.0, -1.0))
    pts = [(cx, cy)]
    for k in range(8):
        ang = 2.0 * math.pi * k / 8.0
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    for x, y in pts:
        hit = bvh.ray_cast(Vector((x, y, 0.95)), down, 0.15)
        if hit[0] is None or not (WEB_Z[0] <= hit[0].z <= WEB_Z[1]):
            return False
    return True


def _nudge_pin_off_struts(bvh, pin, dirxy, rank_dir):
    """Slide ``pin`` along the rank so its cylinder clears raised plate struts.

    The lattice is kept (same rank line); only a few pins next to plate bars
    need a millimetre-scale shift. The harp seats the cylinder at
    ``pin - dirxy * PIN_R`` (string wraps the pin's side), so clearance is
    tested there.
    """
    if bvh is None:
        return pin
    need = PIN_R + PIN_CLEAR_MARGIN

    def cyl_xy(p):
        c = p - dirxy * PIN_R
        return c.x, c.y

    def ok(p):
        x, y = cyl_xy(p)
        return (_pin_side_clear(bvh, x, y)[0] >= need
                and _pin_footprint_on_web(bvh, x, y))

    if ok(pin):
        return pin

    x0, y0 = cyl_xy(pin)
    _cl, hit_dir = _pin_side_clear(bvh, x0, y0)
    # Move away from the nearest plate: hit_dir points from pin toward brass.
    prefer = 1
    if hit_dir is not None and rank_dir.dot(hit_dir) > 0:
        prefer = -1

    max_steps = int(round(PIN_NUDGE_MAX * 1000))
    for step_mm in range(1, max_steps + 1):
        for sign in (prefer, -prefer):
            cand = pin + rank_dir * (0.001 * step_mm * sign)
            if ok(cand):
                return cand
    return pin


def course_lines():
    """Per-note course geometry, shared by strings, pins, and the damper action.

    Returns a list of dicts: ``note``, ``F``/``R`` (course center front/rear),
    ``r`` (string radius), ``sec``, and ``unisons`` - one ``(F_k, R_k)`` segment
    per physical string, with the front end running to its tuning-pin position
    on one of ``RANKS`` straight pin rows over the plate's pin field.
    """
    # Plate bay/lip cut first so pin-clearance probes see the open pin field
    # (not the pre-cut damper-lip overlay). Idempotent via harp.CAPO_MARK.
    from . import harp as harp_mod
    harp_mod._cut_plate_bays()

    keys = action_mod._keys_sorted()
    meas = action_mod._measure(keys)
    plan = action_mod._plan(keys, meas)
    a, b = plan["line"]
    rank_dir = Vector((1.0, b, 0.0)).normalized()
    bvh = _plate_bvh()

    bass, main = _string_samples()
    bass_anchors = [_anchor_x(F, R, a, b)[0] for F, R in bass]
    main_anchors = [_anchor_x(F, R, a, b)[0] for F, R in main]

    courses = []
    pin_i = 0
    for n in plan["notes"]:
        note, x = n["note"], n["x"]
        sec = _section_of(note)
        spec = SECTIONS[sec]
        fan, anchors = (bass, bass_anchors) if sec != "tri" else (main, main_anchors)
        F, R = _course_endpoints(fan, anchors, x)
        # Gauge tapers across each section's note range.
        lo = 21 if sec == "mono" else (MONO_TOP + 1 if sec == "bi" else BREAK_NOTE)
        hi = MONO_TOP if sec == "mono" else (BREAK_NOTE - 1 if sec == "bi" else 108)
        t = (note - lo) / max(hi - lo, 1)
        r = spec["r"][0] * (1 - t) + spec["r"][1] * t
        # Unisons sit side by side, perpendicular to the string in plan view;
        # each front runs to its pin on one of RANKS straight rows. The rank
        # cycles pin-to-pin, which draws the diagonal lattice of a real pin
        # field - and is what clears 6.4 mm pins between courses that run as
        # little as ~9 mm apart: same-rank pins only recur RANKS pins along,
        # never closer than a course gap. Pins that still land on/against a
        # raised plate strut slide a few millimetres along the rank onto
        # clear web (see _nudge_pin_off_struts).
        d = (R - F)
        dirxy = Vector((d.x, d.y, 0.0)).normalized()
        perp = Vector((-d.y, d.x, 0.0)).normalized()
        m = spec["count"]
        unisons = []
        for k in range(m):
            off = perp * (spec["spread"] * (k - (m - 1) / 2.0))
            # perp.x < 0: k ascends right-to-left, so cycle the rank in
            # spatial (left-to-right) order or same-rank pins land a course
            # gap MINUS a unison spread apart instead of plus.
            pin = _on_rank(F + off, dirxy, a, b, (pin_i + m - 1 - k) % RANKS)
            pin = _nudge_pin_off_struts(bvh, pin, dirxy, rank_dir)
            unisons.append((pin, R + off))
        pin_i += m
        courses.append({"note": note, "F": F, "R": R, "r": r, "sec": sec,
                        "unisons": unisons})
    return courses


def build():
    courses = course_lines()

    old = bpy.data.objects.get(OUTPUT)
    if old is not None:
        me = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)

    src = bpy.data.objects[SOURCE]
    copper = src.data.materials[0] if src.data.materials else None
    steel = _steel_material()

    verts, faces, fmats = [], [], []
    counts = {"mono": 0, "bi": 0, "tri": 0}
    for c in courses:
        sec = c["sec"]
        for F_k, R_k in c["unisons"]:
            _hex_string(verts, faces, fmats, F_k, R_k, c["r"],
                        COPPER if sec != "tri" else STEEL)
        counts[sec] += len(c["unisons"])

    me = bpy.data.meshes.new(OUTPUT)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.materials.append(copper)
    me.materials.append(steel)
    for poly, mi in zip(me.polygons, fmats):
        poly.material_index = mi
    me.validate()
    me.update()
    obj = bpy.data.objects.new(OUTPUT, me)
    coll = src.users_collection[0] if src.users_collection else bpy.context.scene.collection
    coll.objects.link(obj)

    # Retire the 51 stand-ins: hidden here, stripped from the GLB export.
    action_mod._hide_keep(src)
    src[REPLACED_PROP] = 1

    dampers = _reseat_dampers(courses)

    return {
        "courses": len(courses),
        "strings": sum(counts.values()),
        "mono": counts["mono"],
        "bi": counts["bi"],
        "tri": counts["tri"],
        "verts": len(verts),
        "dampers": dampers,
    }
