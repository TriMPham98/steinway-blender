"""Build the Steinway double-escapement (repetition) action behind the keys.

Adds, for each of the 88 ``Key.NNN`` objects, the grand-action assembly that the
imported furniture model lacks: a hidden rear **key arm** (capstan + backcheck),
a **wippen** on a support rail carrying the L-shaped **jack** (toe under a
**let-off button**) and the spring-loaded **repetition lever** (slot, saddle,
**drop screw**), and a **hammer** (shank + leather knuckle + felt head) on a
flange rail that strikes the model's real strings just in front of the dampers.

Everything is rigged with drivers off each key's ``rotation_euler.x`` (the
channel the live-MIDI animator already writes), so the whole action follows both
live play and keyframed/scrubbed keys with no add-on required:

- key arm      ``psi * q``           (per-note gain -> uniform capstan rise)
- wippen       ``OMEGA * q``         (heel stays glued to the rising capstan)
- jack         ``-max(c*q - g, 0)``  (toe pinned on the let-off button -> escape)
- rep lever    ``-max(c*q - g, 0)``  (drop screw stops its rise near let-off)
- hammer       throw ~ jack lift, capped at let-off, small drop to the saddle,
               plus ``0.45 * key["hammer"]`` so the live animator can fire real
               strikes (ballistic flight to the string, fall back to check)

where ``q = clamp(rot_x / press_angle)``. All expressions stay inside Blender's
trusted simple-driver subset (min/max arithmetic), so no script auto-run is
needed when the .blend is reopened.

The strike line follows the model's diagonal string band: per-note string fronts
and damper fronts are measured from the meshes, a straight action line is fitted
through them, and each hammer's strike height comes from an upward BVH raycast
against strings / plate / pins / dampers (so heads stop just under whatever is
actually above them). The imported soundboard slab extends under the strike zone
where no real soundboard exists, so its front edge is cut back along the action
line (a real piano's belly-rail gap; hidden under the Music Shelf; the playable
.blend is fully regenerable from the source model).

Pure ``bpy``/``bmesh`` (no ``bpy.ops``), headless-safe, idempotent: rebuilding
replaces the ``Steinway_Action`` collection and skips the (marked) soundboard cut.
"""

import math

import bpy
import bmesh
import mathutils
from mathutils import Vector

# --------------------------------------------------------------------------- #
# Layout constants (world meters; +Y toward the piano tail, player at -Y)
# --------------------------------------------------------------------------- #
PRESS_ANGLE = math.radians(3.5)     # full key dip the drivers normalize against
Q = 1.0 / PRESS_ANGLE               # rot_x -> press fraction

CAP_RISE = 0.0051        # capstan rise at full press (uniform across notes)
STRIKE_SETBACK = 0.018   # preferred strike distance behind the string front end

# Stations as offsets from the fitted action line ``yl`` (the capstan line).
W_PIVOT_DY = -0.105      # wippen flange pivot (support rail)
JACK_DY = 0.075          # jack pivot / knuckle / saddle station
LEVER_DY = 0.040         # repetition-lever pivot (flange post on the wippen)
LETOFF_DY = 0.062        # let-off button (through the lever's button window)
SCREW_DY = 0.088         # drop screw (above the repetition-lever tail)
FLANGE_DY = 0.115        # hammershank flange pivot (hammer rail)
RAIL_DY = 0.127          # hammer rail beam center

# Vertical stack. The model's brass plate has a solid web at z = 0.850 under the
# whole string band, so the hammers strike its underside (from the cavity that
# surface *is* the strings); the stack is compressed to fit between the key arms
# (~0.73) and that ceiling while keeping every contact at a believable height.
W_PIVOT_Z = 0.7605       # wippen pivot height
JACK_PIVOT_Z = 0.7705
LEVER_PIVOT_Z = 0.7745
FLANGE_Z = 0.804         # hammershank pivot height
CAP_TOP_Z = 0.7495       # capstan top = wippen heel felt at rest
HEAD_TOP = 0.022         # felt crown above the shank center line
HEAD_REST_TOP_Z = FLANGE_Z + HEAD_TOP

# Driver gains, derived so every contact stays consistent through the stroke:
#   wippen:    OMEGA * 0.105 == CAP_RISE  (heel rides the capstan exactly)
#   jack:      toe (19.5 mm ahead of its pivot, station 160.5 mm) pinned on the
#              let-off button from q = JACK_Q0 -> tip kicks out from the knuckle
#   rep lever: saddle stopped by the drop screw from q = LEVER_Q0 so the falling
#              knuckle lands on it at full press (the double-escapement "check")
#   hammer:    knuckle lift / 40 mm knuckle radius, capped at a per-note let-off
#              just short of its strike height, then DROP rad down onto the lever
OMEGA = CAP_RISE / abs(W_PIVOT_DY)            # 0.0486 rad at full press
JACK_GAIN = OMEGA * 0.167 / 0.013             # toe station / toe arm
JACK_Q0 = 0.85
LEVER_GAIN = OMEGA * 0.193 / 0.048            # screw station / screw arm
LEVER_Q0 = 0.915
HAM_SLOPE = OMEGA * 0.180 / 0.040             # jack station / knuckle radius
HAM_DROP = 0.020
HAM_IMPULSE = 0.25                            # gain on the live key["hammer"]

SOUNDBOARD = "Soundboard"
CUT_MARGIN = 0.032       # soundboard removed for y < action line + this margin
CUT_MARK = "steinway_action_cut"

COLLECTION = "Steinway_Action"
PART_PROP = "action_part"
NOTE_PROP = "action_note"

# Meshes the hammers must clear from below (strike-height raycast targets).
_OBSTACLES = (
    "Strings", "String Pins", "Dampers Bottoms", "Dampers Tops",
    "Brass_Sound_Works.001", "Brass_Sound_Works.002",
    "String Supports-01", "String Supports-02", SOUNDBOARD,
)

_MATS = (
    # name, rgba, roughness, metallic
    ("Action_Maple", (0.62, 0.44, 0.24, 1.0), 0.55, 0.0),
    ("Action_Walnut", (0.16, 0.09, 0.05, 1.0), 0.60, 0.0),
    ("Action_Felt_White", (0.91, 0.88, 0.80, 1.0), 0.95, 0.0),
    ("Action_Felt_Red", (0.42, 0.05, 0.07, 1.0), 0.95, 0.0),
    ("Action_Brass", (0.78, 0.62, 0.28, 1.0), 0.35, 1.0),
    ("Action_Leather", (0.48, 0.30, 0.16, 1.0), 0.85, 0.0),
)
MAPLE, WALNUT, FELT, FELT_RED, BRASS, LEATHER = range(6)


# --------------------------------------------------------------------------- #
# Small mesh-building toolkit (everything is boxes / prisms / cylinders)
# --------------------------------------------------------------------------- #
class _Buf:
    """Accumulates verts/faces (+ per-face material index) for one mesh."""

    def __init__(self):
        self.v, self.f, self.fm = [], [], []

    def _emit(self, verts, faces, mat):
        base = len(self.v)
        self.v += verts
        self.f += [tuple(base + i for i in face) for face in faces]
        self.fm += [mat] * len(faces)

    def box(self, x0, x1, y0, y1, z0, z1, mat):
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        self._emit(v, f, mat)

    def bar(self, p0, p1, r, mat):
        """Square prism of half-width r along an arbitrary segment."""
        p0, p1 = Vector(p0), Vector(p1)
        d = (p1 - p0).normalized()
        side = d.cross(Vector((0.0, 0.0, 1.0)))
        if side.length < 1e-6:
            side = d.cross(Vector((0.0, 1.0, 0.0)))
        side = side.normalized() * r
        up = d.cross(side).normalized() * r
        ring0 = [p0 + side + up, p0 - side + up, p0 - side - up, p0 + side - up]
        ring1 = [p + (p1 - p0) for p in ring0]
        v = [tuple(p) for p in ring0 + ring1]
        f = [(0, 1, 2, 3), (7, 6, 5, 4)]
        f += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
        self._emit(v, f, mat)

    def cyl(self, axis, center, r, a0, a1, mat, n=10):
        """Axis-aligned cylinder; ``center`` = the two fixed coords, a0..a1 along axis."""
        ring0, ring1 = [], []
        for i in range(n):
            t = 2.0 * math.pi * i / n
            u, w = center[0] + r * math.cos(t), center[1] + r * math.sin(t)
            if axis == "x":
                ring0.append((a0, u, w)); ring1.append((a1, u, w))
            elif axis == "y":
                ring0.append((u, a0, w)); ring1.append((u, a1, w))
            else:
                ring0.append((u, w, a0)); ring1.append((u, w, a1))
        v = ring0 + ring1
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        f += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self._emit(v, f, mat)

    def profile_x(self, pts, x0, x1, mat):
        """Prism from a convex (y, z) outline extruded across x0..x1."""
        n = len(pts)
        v = [(x0, y, z) for y, z in pts] + [(x1, y, z) for y, z in pts]
        f = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
        f += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self._emit(v, f, mat)

    def to_object(self, name, origin, coll, mats, local=False):
        """Make an object at ``origin``. Buffer coords are world unless ``local``."""
        me = bpy.data.meshes.new(name)
        ox, oy, oz = (0.0, 0.0, 0.0) if local else origin
        me.from_pydata([(x - ox, y - oy, z - oz) for x, y, z in self.v], [], self.f)
        for m in mats:
            me.materials.append(m)
        for poly, mi in zip(me.polygons, self.fm):
            poly.material_index = mi
        me.validate()
        me.update()
        obj = bpy.data.objects.new(name, me)
        obj.location = origin
        coll.objects.link(obj)
        return obj


def _materials():
    out = []
    for name, rgba, rough, metal in _MATS:
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            bsdf.inputs["Base Color"].default_value = rgba
            bsdf.inputs["Roughness"].default_value = rough
            bsdf.inputs["Metallic"].default_value = metal
            mat.diffuse_color = rgba
        out.append(mat)
    return out


# --------------------------------------------------------------------------- #
# Measurement: per-note string fronts / damper fronts from the model meshes
# --------------------------------------------------------------------------- #
def _keys_sorted():
    keys = [o for o in bpy.data.objects if o.get("midi_note") is not None]
    keys.sort(key=lambda o: int(o["midi_note"]))
    if len(keys) != 88:
        raise RuntimeError(f"expected 88 tagged keys, found {len(keys)} - prepare the model first")
    return keys

def _world_verts(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        return []
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def _xbins(verts, width=0.005):
    bins = {}
    for v in verts:
        bins.setdefault(int(math.floor(v.x / width)), []).append(v)
    return bins, width


def _near_x(bins, width, x, half=0.0073):
    lo, hi = int(math.floor((x - half) / width)), int(math.floor((x + half) / width))
    out = []
    for b in range(lo, hi + 1):
        out += [v for v in bins.get(b, ()) if abs(v.x - x) <= half]
    return out


def _clean_series(vals, lo, hi):
    """Reject out-of-range samples, then linearly interpolate the gaps."""
    n = len(vals)
    ok = [i for i, v in enumerate(vals) if v is not None and lo <= v <= hi]
    if not ok:
        raise RuntimeError("measurement series is empty - is this the Steinway model?")
    out = list(vals)
    for i in range(n):
        if i in ok:
            continue
        prev = max((j for j in ok if j < i), default=None)
        nxt = min((j for j in ok if j > i), default=None)
        if prev is None:
            out[i] = vals[nxt]
        elif nxt is None:
            out[i] = vals[prev]
        else:
            t = (i - prev) / (nxt - prev)
            out[i] = vals[prev] * (1 - t) + vals[nxt] * t
    return out


def _measure(keys):
    sbins, sw = _xbins(_world_verts("Strings"))
    dbins, dw = _xbins(_world_verts("Dampers Bottoms"))
    s_front, d_front = [], []
    for key in keys:
        x = key.location.x
        sv = [v for v in _near_x(sbins, sw, x) if v.y < -0.30]
        s_front.append(min((v.y for v in sv), default=None))
        dv = [v for v in _near_x(dbins, dw, x) if v.y < -0.30]
        d_front.append(min((v.y for v in dv), default=None))
    return {
        "s_front": _clean_series(s_front, -0.62, -0.40),
        "d_front": _clean_series(d_front, -0.55, -0.40),
    }


def _fit_line(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _plan(keys, meas):
    """Per-note geometry: action line, strike target, arm lengths, driver gains."""
    xs = [k.location.x for k in keys]
    prefer = [
        min(sf + STRIKE_SETBACK, df - 0.0085)
        for sf, df in zip(meas["s_front"], meas["d_front"])
    ]
    a, b = _fit_line(xs, prefer)
    plan = []
    for i, key in enumerate(keys):
        x = key.location.x
        yl = a + b * x                                   # action (capstan) line
        s = min(max(prefer[i], meas["s_front"][i] + 0.001), meas["d_front"][i] - 0.0080)
        s = min(max(s, yl + FLANGE_DY - 0.135), yl + FLANGE_DY - 0.095)
        hinge_y, hinge_z = key.location.y, key.location.z
        arm = yl - hinge_y
        plan.append({
            "note": int(key["midi_note"]),
            "key": key,
            "color": key.get("key_color", "white"),
            "x": x, "yl": yl, "s": s,
            "hinge_y": hinge_y, "hinge_z": hinge_z,
            "arm": arm,
            "psi": CAP_RISE / arm,
            "shank": (yl + FLANGE_DY) - s,
            "s_front": meas["s_front"][i],
            "d_front": meas["d_front"][i],
        })
    return {"line": (a, b), "notes": plan}


# --------------------------------------------------------------------------- #
# Soundboard cut (the model's slab extends under the strike zone)
# --------------------------------------------------------------------------- #
def _cut_soundboard(plan):
    sb = bpy.data.objects.get(SOUNDBOARD)
    if sb is None:
        return "missing"
    if sb.get(CUT_MARK):
        return "already-cut"
    a, b = plan["line"]
    # Plane through the diagonal y = (a + CUT_MARGIN) + b*x, normal facing rear
    # (+y side kept); clear_inner removes the front part under the action.
    p0 = Vector((0.0, a + CUT_MARGIN, 0.8))
    no_w = Vector((-b, 1.0, 0.0)).normalized()
    mw = sb.matrix_world
    co_l = mw.inverted() @ p0
    no_l = (mw.to_3x3().transposed() @ no_w).normalized()
    bm = bmesh.new()
    bm.from_mesh(sb.data)
    res = bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
        plane_co=co_l, plane_no=no_l,
        clear_inner=True, clear_outer=False,
    )
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if cut_edges:
        bmesh.ops.holes_fill(bm, edges=cut_edges)
    bm.to_mesh(sb.data)
    bm.free()
    sb.data.update()
    sb[CUT_MARK] = 1
    return "cut"


# --------------------------------------------------------------------------- #
# Strike heights: upward raycasts against everything above the hammers
# --------------------------------------------------------------------------- #
def _obstacle_bvh():
    from mathutils.bvhtree import BVHTree

    deps = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for name in _OBSTACLES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        ev = obj.evaluated_get(deps)
        me = ev.to_mesh()
        mw = ev.matrix_world
        base = len(verts)
        verts += [tuple(mw @ v.co) for v in me.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def _min_clearance(bvh, x, s, z0=0.8265):
    up = Vector((0.0, 0.0, 1.0))
    zmin = 0.8895                       # default: just under the string band
    for dx in (-0.0035, 0.0, 0.0035):
        for dy in (-0.003, 0.0, 0.003):
            hit = bvh.ray_cast(Vector((x + dx, s + dy, z0)), up, 0.10)
            if hit[0] is not None:
                zmin = min(zmin, hit[0].z)
    return zmin


def _phi_for_rise(shank, rise):
    """Hammer angle that lifts the felt crown by ``rise`` (crown radius arc)."""
    lo, hi = 0.0, 0.6
    for _ in range(48):
        mid = 0.5 * (lo + hi)
        if shank * math.sin(mid) - HEAD_TOP * (1.0 - math.cos(mid)) < rise:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _strike_heights(plan):
    bvh = _obstacle_bvh()
    flagged = []
    for n in plan["notes"]:
        flange_y = n["yl"] + FLANGE_DY
        # Keep the head over the open head-slot in the soundboard and the shank
        # believable; within that, nudge to wherever overhead clearance is best.
        best_s, best_z = n["s"], -1.0
        for dy in (0.0, 0.003, -0.003, 0.006, -0.006):
            s = n["s"] + dy
            if not (0.100 <= flange_y - s <= 0.130):
                continue
            z = _min_clearance(bvh, n["x"], s)
            if z > best_z:
                best_s, best_z = s, z
        n["s"] = best_s
        n["shank"] = flange_y - best_s
        n["strike_z"] = best_z - 0.0008
        n["phi_cap"] = _phi_for_rise(n["shank"], n["strike_z"] - HEAD_REST_TOP_Z)
        # Let-off just short of the strike (per note: shank lengths differ).
        n["letoff"] = min(max(0.92 * n["phi_cap"] / HAM_SLOPE, 0.70), 0.92)
        if n["strike_z"] < HEAD_REST_TOP_Z + 0.015:
            flagged.append((n["note"], round(n["strike_z"], 4)))
    return flagged


# --------------------------------------------------------------------------- #
# Geometry: shared part meshes + per-note arms/hammers + the static frame
# --------------------------------------------------------------------------- #
def _wippen_buf():
    b = _Buf()
    b.box(-0.005, 0.005, -0.006, 0.010, -0.007, 0.005, MAPLE)        # flange fork
    b.box(-0.0045, 0.0045, 0.010, 0.196, -0.0045, 0.0045, MAPLE)     # body bar
    b.box(-0.0045, 0.0045, 0.096, 0.114, -0.009, -0.0045, MAPLE)     # heel
    b.box(-0.0045, 0.0045, 0.096, 0.114, -0.011, -0.009, FELT_RED)   # heel felt
    b.box(-0.003, 0.003, 0.140, 0.152, 0.0045, 0.014, MAPLE)         # lever post
    b.bar((0, 0.150, 0.011), (0, 0.162, 0.002), 0.0008, BRASS)       # rep spring
    b.bar((0, 0.162, 0.002), (0, 0.172, 0.0195), 0.0008, BRASS)
    return b


def _jack_buf():
    b = _Buf()
    b.box(-0.0045, 0.0045, -0.005, 0.005, -0.0055, 0.0, MAPLE)       # flange lugs
    b.box(-0.00275, 0.00275, -0.0035, 0.0035, -0.003, 0.0175, MAPLE) # vertical arm
    b.box(-0.00275, 0.00275, -0.0035, 0.0035, 0.0175, 0.0195, LEATHER)
    b.box(-0.00275, 0.00275, -0.018, -0.0035, -0.0005, 0.005, MAPLE) # toe
    b.box(-0.00275, 0.00275, -0.017, -0.010, 0.005, 0.0062, FELT_RED)
    return b


def _lever_buf():
    """Repetition lever: thin front bar, a window the let-off button passes
    through, the slotted knuckle saddle over the jack, and the drop-screw tail."""
    b = _Buf()
    for sx in (-1, 1):                                               # pivot fork
        b.box(sx * 0.003, sx * 0.0045, -0.006, 0.006, -0.004, 0.0105, MAPLE)
    b.box(-0.005, 0.005, -0.030, 0.013, 0.0065, 0.0085, MAPLE)       # front bar
    for sx in (-1, 1):                                               # button window
        b.box(sx * 0.0040, sx * 0.0065, 0.013, 0.030, 0.0065, 0.0085, MAPLE)
    for sx in (-1, 1):                                               # jack window
        b.box(sx * 0.0035, sx * 0.0055, 0.030, 0.046, 0.0065, 0.0085, MAPLE)
    for sx in (-1, 1):                                               # knuckle saddle
        b.box(sx * 0.00375, sx * 0.0065, 0.030, 0.044, 0.0085, 0.015, MAPLE)
    b.box(-0.0065, 0.0065, 0.046, 0.052, 0.0065, 0.0115, MAPLE)      # screw tail
    return b


def _hammer_buf(shank):
    b = _Buf()
    b.box(-0.0035, 0.0035, -0.010, 0.006, -0.005, 0.005, WALNUT)     # butt
    b.bar((0, -0.008, 0), (0, -(shank - 0.004), 0), 0.0032, MAPLE)   # shank
    b.cyl("x", (-0.040, -0.010), 0.004, -0.0045, 0.0045, LEATHER)    # knuckle
    yc = -shank
    b.box(-0.0045, 0.0045, yc - 0.0045, yc + 0.0045, -0.014, 0.006, WALNUT)
    felt = [(yc - 0.0048, 0.004), (yc - 0.0048, 0.0115), (yc - 0.0028, 0.0185),
            (yc, HEAD_TOP), (yc + 0.0028, 0.0185), (yc + 0.0048, 0.0115),
            (yc + 0.0048, 0.004)]
    b.profile_x(felt, -0.0045, 0.0045, FELT)
    return b


def _key_arm_buf(n):
    """Hidden seesaw arm behind one key: slab + capstan + backcheck (world coords)."""
    b = _Buf()
    x, yl, s = n["x"], n["yl"], n["s"]
    hy, hz = n["hinge_y"], n["hinge_z"]
    if n["color"] == "black":
        z0, z1 = hz - 0.0045, hz + 0.0015
    else:
        z0, z1 = hz - 0.0038, hz + 0.0042
    b.box(x - 0.005, x + 0.005, hy + 0.0005, yl + 0.010, z0, z1, WALNUT)
    b.cyl("z", (x, yl), 0.0035, z1, 0.746, BRASS)                    # capstan
    b.cyl("z", (x, yl), 0.0048, 0.746, CAP_TOP_Z, BRASS)
    ybc = s - 0.016                                                  # backcheck
    b.bar((x, ybc, z1), (x, ybc, 0.794), 0.0011, BRASS)
    b.box(x - 0.004, x + 0.004, ybc - 0.0025, ybc + 0.0025, 0.794, 0.806, LEATHER)
    return b


def _frame_buf(plan):
    """All static parts in one mesh: rails, buttons, flange lugs, drop screws."""
    b = _Buf()
    a, slope = plan["line"]
    notes = plan["notes"]
    xL, xR = notes[0]["x"] - 0.012, notes[-1]["x"] + 0.012

    def rail(dy, half_y, z0, z1, mat):
        pts, faces = [], []
        for x in (xL, xR):
            yc = a + slope * x + dy
            pts += [(x, yc - half_y, z0), (x, yc + half_y, z0),
                    (x, yc + half_y, z1), (x, yc - half_y, z1)]
        f = [(3, 2, 1, 0), (4, 5, 6, 7)]
        f += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
        b._emit(pts, f, mat)

    rail(W_PIVOT_DY, 0.008, 0.7465, 0.7605, WALNUT)      # support rail
    rail(LETOFF_DY, 0.006, 0.792, 0.798, WALNUT)         # let-off rail
    rail(RAIL_DY, 0.008, 0.7985, 0.8125, WALNUT)         # hammershank rail

    for n in notes:
        x, yl = n["x"], n["yl"]
        # let-off button: screw shaft + felted regulating button under the rail,
        # reaching the jack toe through the repetition lever's button window
        b.cyl("z", (x, yl + LETOFF_DY), 0.0015, 0.786, 0.793, BRASS, n=8)
        b.cyl("z", (x, yl + LETOFF_DY), 0.0035, 0.7836, 0.786, FELT_RED, n=10)
        # hammershank flange: lug plates + center pin
        for sx in (-1, 1):
            b.box(x + sx * 0.0042, x + sx * 0.0072,
                  yl + 0.107, yl + 0.123, 0.799, 0.811, MAPLE)
        b.cyl("x", (yl + FLANGE_DY, FLANGE_Z), 0.0012, x - 0.0042, x + 0.0042, BRASS, n=8)
        # drop screw on a small bracket beside the shank, over the lever tail
        b.box(x + 0.0035, x + 0.0065, yl + 0.084, yl + 0.112, 0.8005, 0.8035, MAPLE)
        b.bar((x + 0.005, yl + SCREW_DY, 0.7946), (x + 0.005, yl + SCREW_DY, 0.8005),
              0.0012, BRASS)
        b.cyl("z", (x + 0.005, yl + SCREW_DY), 0.0022, 0.7946, 0.7966, BRASS, n=8)

    for x0, x1 in ((xL - 0.0045, xL - 0.0005), (xR + 0.0005, xR + 0.0045)):
        yc = a + slope * (0.5 * (x0 + x1))
        b.box(x0, x1, yc - 0.113, yc + 0.135, 0.677, 0.8125, WALNUT) # end brackets
    return b


# --------------------------------------------------------------------------- #
# Objects, parenting, drivers
# --------------------------------------------------------------------------- #
def _fresh_collection():
    coll = bpy.data.collections.get(COLLECTION)
    if coll is not None:
        for obj in list(coll.objects):
            me = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    else:
        coll = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


def _tag(obj, part, note):
    obj[PART_PROP] = part
    obj[NOTE_PROP] = note


def _driver(obj, key, expr, with_hammer=False):
    # SINGLE_PROP on the raw channel (not a TRANSFORMS variable): it is exactly
    # what the live animator writes, and it also evaluates headless.
    fc = obj.driver_add("rotation_euler", 0)
    drv = fc.driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "r"
    var.type = "SINGLE_PROP"
    var.targets[0].id = key
    var.targets[0].data_path = "rotation_euler[0]"
    if with_hammer:
        var = drv.variables.new()
        var.name = "h"
        var.type = "SINGLE_PROP"
        var.targets[0].id = key
        var.targets[0].data_path = '["hammer"]'
    drv.expression = expr


_QEXPR = f"max(min(r*{Q:.4f},1),0)"


def _build_units(plan, coll, mats):
    shared = {
        "wippen": _wippen_buf().to_object("ActionMesh.Wippen", (0, 0, 0), coll, mats),
        "jack": _jack_buf().to_object("ActionMesh.Jack", (0, 0, 0), coll, mats),
        "lever": _lever_buf().to_object("ActionMesh.RepLever", (0, 0, 0), coll, mats),
    }
    # The prototype objects only exist to own the shared meshes; unlink them.
    proto = {k: o.data for k, o in shared.items()}
    for o in shared.values():
        bpy.data.objects.remove(o, do_unlink=True)

    for n in plan["notes"]:
        note, key, x, yl = n["note"], n["key"], n["x"], n["yl"]

        arm = _key_arm_buf(n).to_object(
            f"KeyArm.{note:03d}", (x, n["hinge_y"], n["hinge_z"]), coll, mats)
        _tag(arm, "key_arm", note)
        _driver(arm, key, f"{n['psi']:.4f}*{_QEXPR}")

        wip = bpy.data.objects.new(f"Wippen.{note:03d}", proto["wippen"])
        wip.location = (x, yl + W_PIVOT_DY, W_PIVOT_Z)
        coll.objects.link(wip)
        _tag(wip, "wippen", note)
        _driver(wip, key, f"{OMEGA:.4f}*{_QEXPR}")

        # A fresh object's cached matrix_world is still identity, so build the
        # parent inverse from the wippen's intended transform, not its cache.
        wip_inv = mathutils.Matrix.Translation(wip.location).inverted()

        jack = bpy.data.objects.new(f"Jack.{note:03d}", proto["jack"])
        jack.location = (x, yl + JACK_DY, JACK_PIVOT_Z)
        coll.objects.link(jack)
        jack.parent = wip
        jack.matrix_parent_inverse = wip_inv
        _tag(jack, "jack", note)
        _driver(jack, key, f"-max({JACK_GAIN:.4f}*min(r*{Q:.4f},1)-{JACK_GAIN * JACK_Q0:.4f},0)")

        lev = bpy.data.objects.new(f"RepLever.{note:03d}", proto["lever"])
        lev.location = (x, yl + LEVER_DY, LEVER_PIVOT_Z)
        coll.objects.link(lev)
        lev.parent = wip
        lev.matrix_parent_inverse = wip_inv
        _tag(lev, "rep_lever", note)
        _driver(lev, key, f"-max({LEVER_GAIN:.4f}*min(r*{Q:.4f},1)-{LEVER_GAIN * LEVER_Q0:.4f},0)")

        ham = _hammer_buf(n["shank"]).to_object(
            f"Hammer.{note:03d}", (x, yl + FLANGE_DY, FLANGE_Z), coll, mats,
            local=True)
        _tag(ham, "hammer", note)
        lo = n["letoff"]
        ramp = 1.0 / max(1.0 - lo, 0.05)
        expr = (
            f"-min({HAM_SLOPE:.4f}*min({_QEXPR},{lo:.3f})"
            f"-{HAM_DROP}*min(max({_QEXPR}-{lo:.3f},0)*{ramp:.2f},1)"
            f"+{HAM_IMPULSE}*h,{n['phi_cap']:.4f})"
        )
        _driver(ham, key, expr, with_hammer=True)

    frame = _frame_buf(plan).to_object("Action_Frame", (0, 0, 0), coll, mats)
    _tag(frame, "frame", -1)

    # The new drivers' first evaluation must see freshly-copied key data, or
    # they compile against stale evaluated copies and stick invalid for the
    # session (reopened files build the graph from scratch and are fine).
    for n in plan["notes"]:
        n["key"].update_tag()


# --------------------------------------------------------------------------- #
# Verification: pose the drivers and measure the contacts they promise
# --------------------------------------------------------------------------- #
def _verify(plan):
    deps = bpy.context.evaluated_depsgraph_get()
    sample = [n for n in plan["notes"] if n["note"] in (21, 36, 60, 61, 84, 108)]
    rows, worst_heel, worst_strike = [], 0.0, 0.0

    def crown_z(n):
        ham = bpy.data.objects[f"Hammer.{n['note']:03d}"]
        ev = ham.evaluated_get(deps)
        return (ev.matrix_world @ Vector((0.0, -n["shank"], HEAD_TOP))).z

    for n in sample:
        key = n["key"]
        for q, h in ((0.0, 0.0), (1.0, 0.0), (0.6, 1.0)):
            key.rotation_euler.x = q * PRESS_ANGLE
            key["hammer"] = h
            key.update_tag()
            deps.update()
            cz = crown_z(n)
            if h > 0.0:
                worst_strike = max(worst_strike, abs(cz - n["strike_z"]))
            arm = bpy.data.objects[f"KeyArm.{n['note']:03d}"].evaluated_get(deps)
            cap = (arm.matrix_world @ Vector((0.0, n["yl"] - n["hinge_y"],
                                              CAP_TOP_Z - n["hinge_z"]))).z
            wip = bpy.data.objects[f"Wippen.{n['note']:03d}"].evaluated_get(deps)
            heel = (wip.matrix_world @ Vector((0.0, abs(W_PIVOT_DY), CAP_TOP_Z - W_PIVOT_Z))).z
            worst_heel = max(worst_heel, abs(heel - cap))
            rows.append((n["note"], q, h, round(cz, 4), round(heel - cap, 5)))
        key.rotation_euler.x = 0.0
        key["hammer"] = 0.0
        key.update_tag()
    deps.update()
    return {"rows": rows, "heel_err": worst_heel, "strike_err": worst_strike}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build():
    keys = _keys_sorted()
    # The live-strike channel must exist before the depsgraph is first built,
    # or drivers reading it stay invalid until the next full graph rebuild.
    for key in keys:
        if "hammer" not in key:
            key["hammer"] = 0.0
    meas = _measure(keys)
    plan = _plan(keys, meas)
    cut = _cut_soundboard(plan)
    flagged = _strike_heights(plan)
    coll = _fresh_collection()
    mats = _materials()
    _build_units(plan, coll, mats)
    checks = _verify(plan)
    szs = [n["strike_z"] for n in plan["notes"]]
    a, b = plan["line"]
    return {
        "notes": len(plan["notes"]),
        "objects": len(coll.objects),
        "soundboard": cut,
        "action_line": (round(a, 4), round(b, 4)),
        "strike_z": (round(min(szs), 4), round(max(szs), 4)),
        "shank": (round(min(n["shank"] for n in plan["notes"]), 4),
                  round(max(n["shank"] for n in plan["notes"]), 4)),
        "low_clearance_notes": flagged,
        "heel_err": round(checks["heel_err"], 5),
        "strike_err": round(checks["strike_err"], 5),
    }
