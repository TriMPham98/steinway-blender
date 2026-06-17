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
line (a real piano's belly-rail gap; hidden under the Music_Shelf; the playable
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

CAP_RISE = 0.00933       # capstan rise at full press (uniform across notes)
STRIKE_FRAC = 0.09       # strike point as a fraction of the string's length

# Stations as offsets from the fitted action line ``yl`` (the capstan line).
W_PIVOT_DY = -0.105      # wippen flange pivot (support rail)
JACK_DY = 0.075          # jack pivot / knuckle / saddle station
LEVER_DY = 0.040         # repetition-lever pivot (flange post on the wippen)
LETOFF_DY = 0.062        # let-off button (through the lever's button window)
SCREW_DY = 0.088         # drop screw (above the repetition-lever tail)
FLANGE_DY = 0.115        # hammershank flange pivot (hammer rail)
RAIL_DY = 0.127          # hammer rail beam center

# Damper action stations (offsets from the fitted strike line; dampers exist
# for notes 21..88 like a real grand, with the underlever linkage up to
# DAMPER_LINK_TOP - above that the bridge sits too close for the wire slot and
# the heads ride short stub wires instead).
DAMPER_TOP = 88
DAMPER_LINK_TOP = 81
HEAD_DY = 0.042          # damper head center behind the strike line
WIRE_DY = 0.139          # vertical wire drop (behind the hammershank rail)
DLEVER_DY = 0.184        # damper underlever pivot
DCONTACT_DY = 0.129      # key-arm felt -> underlever contact
DRAIL_DY = 0.1975        # damper underlever rail beam center
DTRAY_DY = 0.133         # sustain lift tray beam center
DLEVER_Z = 0.7395        # underlever pivot height (key tails step to one level)
DGAP = 0.0048            # contact gap -> dampers pick up at ~40% key travel
DPEDAL_LIFT = 0.0055     # damper lift at full sustain pedal
PEDAL_Q = 1.0 / math.radians(5.0)   # pedal rot -> press fraction (anim.PEDAL_ANGLE)

# Vertical stack (the plate's bays are opened by build/harp.py, so hammers
# reach the actual strings at z ~0.885-0.893).
W_PIVOT_Z = 0.7605       # wippen pivot height
JACK_PIVOT_Z = 0.7705
LEVER_PIVOT_Z = 0.7745
FLANGE_Z = 0.8175        # hammershank pivot height
CAP_TOP_Z = 0.7495       # capstan top = wippen heel felt at rest
HEAD_TOP = 0.026         # felt crown above the shank center line
HEAD_REST_TOP_Z = FLANGE_Z + HEAD_TOP

# Driver gains, derived so every contact stays consistent through the stroke:
#   wippen:    OMEGA * 0.105 == CAP_RISE  (heel rides the capstan exactly)
#   jack:      toe (13 mm ahead of its pivot, station 167 mm) pinned on the
#              let-off button from q = JACK_Q0 -> tip kicks out from the knuckle
#   rep lever: saddle stopped by the drop screw from q = LEVER_Q0 so the falling
#              knuckle lands on it at full press (the double-escapement "check")
#   hammer:    knuckle lift / 40 mm knuckle radius, capped at a per-note let-off
#              just short of its strike height, then DROP rad down onto the lever
OMEGA = CAP_RISE / abs(W_PIVOT_DY)            # 0.0889 rad at full press
JACK_GAIN = OMEGA * 0.167 / 0.013             # toe station / toe arm
JACK_Q0 = 0.85
LEVER_GAIN = OMEGA * 0.193 / 0.048            # screw station / screw arm
LEVER_Q0 = 0.879
HAM_SLOPE = OMEGA * 0.180 / 0.040             # jack station / knuckle radius
HAM_DROP = 0.026
HAM_IMPULSE = 0.45                            # gain on the live key["hammer"]

SOUNDBOARD = "Soundboard"
BRIDGE = "String_Supports_02"
BRIDGE_SEAT_MARK = "steinway_bridge_seated"
BRIDGE_SEAT_VERSION = 1
BRIDGE_SEAT_LIFT = 0.0015   # world +Z; ~0.6 mm clearance after ~0.9 mm overlap
CUT_MARGIN = 0.082       # soundboard removed for y < strike line + this margin
CUT_DEEP = 0.150         # extra slot for the damper wires (bass of CUT_DEEP_X)
CUT_DEEP_X = 0.428       # the treble bridge sits too close beyond this x
CUT_MARK = "steinway_action_cut"
CUT_VERSION = 2

COLLECTION = "Steinway_Action"
PART_PROP = "action_part"
NOTE_PROP = "action_note"
REPLACED_PROP = "steinway_replaced"

# Meshes the hammers must clear from below (strike-height raycast targets).
# "Strings_Full" is the rebuilt 88-course set (build/strings.py), present once
# that step has run; missing names are skipped. The retired stand-ins (old
# fat strings / 51-string pin field) are deliberately absent - they no longer
# represent the model.
_OBSTACLES = (
    "Strings_Full", "Dampers_Bottoms", "Dampers_Tops",
    "Brass_Sound_Works.001", "Brass_Sound_Works.002",
    "String_Supports_01", "String_Supports_02", SOUNDBOARD,
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

def _world_matrix(obj):
    """Object-to-world matrix that survives viewport-disabled objects.

    ``matrix_world`` is never evaluated for objects excluded from the
    depsgraph (e.g. hidden stand-ins on a fresh file load) and reads as
    identity; rebuild it from the local transform instead. The measured
    stand-ins are all unparented.
    """
    if obj.parent is None:
        return obj.matrix_basis.copy()
    return obj.matrix_world


def _hide_keep(obj):
    """Hide a stand-in without knocking it out of the depsgraph."""
    obj.hide_render = True
    obj.hide_viewport = False        # heals files saved with the breaking flag
    try:
        obj.hide_set(True)
    except RuntimeError:             # not in the active view layer
        pass


def _world_verts(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        return []
    mw = _world_matrix(obj)
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
    dbins, dw = _xbins(_world_verts("Dampers_Bottoms"))
    s_front, s_rear, d_front = [], [], []
    for key in keys:
        x = key.location.x
        sv = [v for v in _near_x(sbins, sw, x) if v.y < -0.30]
        s_front.append(min((v.y for v in sv), default=None))
        rv = _near_x(sbins, sw, x)
        s_rear.append(max((v.y for v in rv), default=None))
        dv = [v for v in _near_x(dbins, dw, x) if v.y < -0.30]
        d_front.append(min((v.y for v in dv), default=None))
    return {
        "s_front": _clean_series(s_front, -0.62, -0.40),
        "s_rear": _clean_series(s_rear, -0.35, 0.85),
        "d_front": _clean_series(d_front, -0.55, -0.40),
    }


def _fit_line(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _plan(keys, meas):
    """Per-note geometry: action line, strike target, arm lengths, driver gains.

    The strike point sits a real fraction of each string's length behind its
    front end (~1/8 of the speaking length), clamped to stay just in front of
    the decorative damper line and on the string at the squeezed treble.
    """
    xs = [k.location.x for k in keys]
    prefer = []
    for sf, sr, df in zip(meas["s_front"], meas["s_rear"], meas["d_front"]):
        s = sf + STRIKE_FRAC * (sr - sf)
        s = min(s, df - 0.0085)
        prefer.append(max(s, sf + 0.004))
    a, b = _fit_line(xs, prefer)
    plan = []
    for i, key in enumerate(keys):
        x = key.location.x
        yl = a + b * x                                   # action (capstan) line
        # The hammer/damper rows sit exactly on the fitted line: per-note
        # measurement jitter would read as a ragged action.
        s = yl
        # Arm slabs fill the keybed to neighbor midpoints (0.5 mm kerfs).
        x_lo = (xs[i - 1] + x) / 2.0 + 0.0005 if i > 0 else x - 0.0068
        x_hi = (x + xs[i + 1]) / 2.0 - 0.0005 if i < 87 else x + 0.0068
        hinge_y, hinge_z = key.location.y, key.location.z
        arm = yl - hinge_y
        plan.append({
            "note": int(key["midi_note"]),
            "key": key,
            "color": key.get("key_color", "white"),
            "x": x, "yl": yl, "s": s,
            "hinge_y": hinge_y, "hinge_z": hinge_z,
            "arm": arm,
            "arm_x0": x_lo, "arm_x1": x_hi,
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
    """Carve the action gap: an L-shaped region (deeper where the damper wires
    drop, bounded at CUT_DEEP_X where the treble bridge approaches) is removed
    from the imported slab, which extends under the strike zone where a real
    piano has open air down to the keybed."""
    sb = bpy.data.objects.get(SOUNDBOARD)
    if sb is None:
        return "missing"
    if sb.get(CUT_MARK, 0) == CUT_VERSION:
        return "already-cut"
    a, b = plan["line"]
    mw = sb.matrix_world
    inv = mw.inverted()
    nrm = mw.to_3x3().transposed()

    bm = bmesh.new()
    bm.from_mesh(sb.data)
    # Score the slab along both diagonal lines and the x boundary (no clears),
    # then drop every face whose center lies in the union region; shared verts
    # survive a FACES-context delete and the open edges get re-filled.
    planes = (
        (Vector((0.0, a + CUT_MARGIN, 0.8)), Vector((-b, 1.0, 0.0))),
        (Vector((0.0, a + CUT_DEEP, 0.8)), Vector((-b, 1.0, 0.0))),
        (Vector((CUT_DEEP_X, 0.0, 0.8)), Vector((1.0, 0.0, 0.0))),
    )
    for co_w, no_w in planes:
        bmesh.ops.bisect_plane(
            bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
            plane_co=inv @ co_w, plane_no=(nrm @ no_w).normalized(),
        )
    bm.faces.ensure_lookup_table()
    doomed = []
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        line = a + b * c.x
        if c.y < line + CUT_MARGIN - 1e-5 or (
                c.x < CUT_DEEP_X - 1e-5 and c.y < line + CUT_DEEP - 1e-5):
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    edges = [e for e in bm.edges if e.is_boundary]
    if edges:
        bmesh.ops.holes_fill(bm, edges=edges)
    bm.to_mesh(sb.data)
    bm.free()
    sb.data.update()
    sb[CUT_MARK] = CUT_VERSION
    return f"cut v{CUT_VERSION}"


def _world_z_bounds(obj):
    mw = obj.matrix_world
    return min((mw @ v.co).z for v in obj.data.vertices), max(
        (mw @ v.co).z for v in obj.data.vertices)


def _seat_bridge_on_soundboard():
    """Lift the treble bridge off the soundboard top (imported coplanar overlap)."""
    sb = bpy.data.objects.get(SOUNDBOARD)
    br = bpy.data.objects.get(BRIDGE)
    if br is None:
        return "missing-bridge"
    if br.get(BRIDGE_SEAT_MARK, 0) == BRIDGE_SEAT_VERSION:
        return "already-seated"
    if sb is not None:
        _, sb_top = _world_z_bounds(sb)
        br_bot, _ = _world_z_bounds(br)
        gap = br_bot - sb_top
        if gap >= 0.0003:
            br[BRIDGE_SEAT_MARK] = BRIDGE_SEAT_VERSION
            return f"ok ({gap * 1000:.2f} mm clearance)"
    br.matrix_world = (
        mathutils.Matrix.Translation((0.0, 0.0, BRIDGE_SEAT_LIFT)) @ br.matrix_world
    )
    br[BRIDGE_SEAT_MARK] = BRIDGE_SEAT_VERSION
    if sb is not None:
        _, sb_top = _world_z_bounds(sb)
        br_bot, _ = _world_z_bounds(br)
        return f"lifted {BRIDGE_SEAT_LIFT * 1000:.1f} mm (gap { (br_bot - sb_top) * 1000:.2f} mm)"
    return f"lifted {BRIDGE_SEAT_LIFT * 1000:.1f} mm"


# --------------------------------------------------------------------------- #
# Strike heights: upward raycasts against everything above the hammers
# --------------------------------------------------------------------------- #
def _obstacle_bvh():
    from mathutils.bvhtree import BVHTree

    # Plain mesh reads (no modifiers on these), with depsgraph-proof matrices:
    # hidden stand-ins keep contributing correct geometry.
    verts, polys = [], []
    for name in _OBSTACLES:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        mw = _world_matrix(obj)
        me = obj.data
        base = len(verts)
        verts += [tuple(mw @ v.co) for v in me.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in me.polygons]
    return BVHTree.FromPolygons(verts, polys)


def _min_clearance(bvh, x, s, z0=0.8445):
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
        # The head stays on the fitted strike line (an even hammer row); the
        # raycast only caps how high it may fly under whatever crosses above.
        n["shank"] = FLANGE_DY
        n["strike_z"] = _min_clearance(bvh, n["x"], n["s"]) - 0.0008
        n["phi_cap"] = _phi_for_rise(n["shank"], n["strike_z"] - HEAD_REST_TOP_Z)
        # Let-off just short of the strike (per note: strike heights differ).
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
    b.box(-0.00275, 0.00275, -0.0035, 0.0035, -0.003, 0.0295, MAPLE) # vertical arm
    b.box(-0.00275, 0.00275, -0.0035, 0.0035, 0.0295, 0.0315, LEATHER)
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
        b.box(sx * 0.00375, sx * 0.0065, 0.030, 0.044, 0.0085, 0.0265, MAPLE)
    b.box(-0.0065, 0.0065, 0.046, 0.052, 0.0065, 0.0115, MAPLE)      # screw tail
    return b


def _hammer_buf(shank):
    b = _Buf()
    b.box(-0.0035, 0.0035, -0.010, 0.006, -0.005, 0.005, WALNUT)     # butt
    b.bar((0, -0.008, 0), (0, -(shank - 0.004), 0), 0.0032, MAPLE)   # shank
    b.cyl("x", (-0.040, -0.011), 0.0045, -0.0045, 0.0045, LEATHER)   # knuckle
    yc = -shank
    b.box(-0.0045, 0.0045, yc - 0.0045, yc + 0.0045, -0.014, 0.006, WALNUT)
    felt = [(yc - 0.0048, 0.004), (yc - 0.0048, 0.013), (yc - 0.0030, 0.0215),
            (yc, HEAD_TOP), (yc + 0.0030, 0.0215), (yc + 0.0048, 0.013),
            (yc + 0.0048, 0.004)]
    b.profile_x(felt, -0.0045, 0.0045, FELT)
    return b


def _key_arm_buf(n):
    """Hidden seesaw arm behind one key: slab + capstan + backcheck, extended to
    the damper underlever contact (with black keys stepping down to the common
    tail level so every underlever sits at one height). Slabs fill to the
    neighbor midpoints like a real keybed - a continuous surface with thin
    kerfs - and every tail ends on the same line. World coords."""
    b = _Buf()
    x, yl, s = n["x"], n["yl"], n["s"]
    xl, xr = n["arm_x0"], n["arm_x1"]
    hy, hz = n["hinge_y"], n["hinge_z"]
    tail_end = s + DCONTACT_DY + 0.006
    if n["color"] == "black":
        z0, z1 = hz - 0.0045, hz + 0.0015
    else:
        z0, z1 = hz - 0.0038, hz + 0.0042
    if n["color"] == "black":
        step_y = yl + 0.020
        b.box(xl, xr, hy + 0.0005, step_y, z0, z1, WALNUT)
        b.box(xl, xr, step_y - 0.002, step_y + 0.010, 0.7225, z0 + 0.001, WALNUT)
        b.box(xl, xr, step_y, tail_end, 0.7225, 0.7305, WALNUT)
    else:
        b.box(xl, xr, hy + 0.0005, tail_end, z0, z1, WALNUT)
    if n["note"] <= DAMPER_LINK_TOP:
        b.box(x - 0.0045, x + 0.0045, s + DCONTACT_DY - 0.008,
              s + DCONTACT_DY + 0.004, 0.7305, 0.7317, FELT_RED)     # lift felt
    b.cyl("z", (x, yl), 0.0035, z1, 0.746, BRASS)                    # capstan
    b.cyl("z", (x, yl), 0.0048, 0.746, CAP_TOP_Z, BRASS)
    ybc = s - 0.016                                                  # backcheck
    b.bar((x, ybc, z1), (x, ybc, 0.821), 0.0011, BRASS)
    b.box(x - 0.004, x + 0.004, ybc - 0.0025, ybc + 0.0025, 0.821, 0.833, LEATHER)
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
    rail(LETOFF_DY, 0.006, 0.800, 0.807, WALNUT)         # let-off rail
    rail(RAIL_DY, 0.008, 0.7985, 0.8125, WALNUT)         # hammershank rail

    for n in notes:
        x, yl = n["x"], n["yl"]
        # let-off button: screw shaft + felted regulating button under the rail,
        # reaching the jack toe through the repetition lever's button window
        b.cyl("z", (x, yl + LETOFF_DY), 0.0015, 0.7917, 0.800, BRASS, n=8)
        b.cyl("z", (x, yl + LETOFF_DY), 0.0035, 0.7893, 0.7917, FELT_RED, n=10)
        # hammershank flange: lug plates + center pin
        for sx in (-1, 1):
            b.box(x + sx * 0.0042, x + sx * 0.0072,
                  yl + 0.107, yl + 0.123, 0.8115, 0.8235, MAPLE)
        b.cyl("x", (yl + FLANGE_DY, FLANGE_Z), 0.0012, x - 0.0042, x + 0.0042, BRASS, n=8)
        # drop screw on a small bracket beside the shank, over the lever tail
        b.box(x + 0.0035, x + 0.0065, yl + 0.084, yl + 0.112, 0.8045, 0.8075, MAPLE)
        b.bar((x + 0.005, yl + SCREW_DY, 0.8011), (x + 0.005, yl + SCREW_DY, 0.8045),
              0.0012, BRASS)
        b.cyl("z", (x + 0.005, yl + SCREW_DY), 0.0022, 0.8011, 0.8031, BRASS, n=8)
        # damper underlever flange lug on its own rail (linked notes only)
        if n["note"] <= DAMPER_LINK_TOP:
            yd = a + slope * x + DLEVER_DY
            b.box(x - 0.004, x + 0.004, yd + 0.004, yd + 0.014,
                  0.7365, 0.7425, MAPLE)

    # damper underlever rail spans the linked notes
    link = [n for n in notes if n["note"] <= DAMPER_LINK_TOP]
    if link:
        pts = []
        for x in (link[0]["x"] - 0.012, link[-1]["x"] + 0.012):
            yc = a + slope * x + DRAIL_DY
            pts += [(x, yc - 0.0075, 0.733), (x, yc + 0.0075, 0.733),
                    (x, yc + 0.0075, 0.7465), (x, yc - 0.0075, 0.7465)]
        fcs = [(3, 2, 1, 0), (4, 5, 6, 7)]
        fcs += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
        b._emit(pts, fcs, WALNUT)

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


def _tag(obj, part, note, **extras):
    obj[PART_PROP] = part
    obj[NOTE_PROP] = note
    for key, val in extras.items():
        obj[f"action_{key}"] = val


def _drive(obj, channel, index, expr, var_specs):
    # SINGLE_PROP on raw channels (not TRANSFORMS variables): they are exactly
    # what the live animator writes, and they also evaluate headless.
    fc = obj.driver_add(channel, index)
    drv = fc.driver
    drv.type = "SCRIPTED"
    for name, vid, path in var_specs:
        var = drv.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id = vid
        var.targets[0].data_path = path
    drv.expression = expr


def _driver(obj, key, expr, with_hammer=False):
    var_specs = [("r", key, "rotation_euler[0]")]
    if with_hammer:
        var_specs.append(("h", key, '["hammer"]'))
    _drive(obj, "rotation_euler", 0, expr, var_specs)


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
        _tag(arm, "key_arm", note, psi=n["psi"])
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
        _tag(ham, "hammer", note, letoff=n["letoff"], phi_cap=n["phi_cap"])
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


def _pedal_obj():
    for obj in bpy.data.objects:
        if obj.get("steinway_role") == "sustain_pedal":
            return obj
    return None


def _collect_decorative_templates():
    """Snapshot each imported decorative damper unit (top + felt) for reuse."""
    from . import strings as strings_mod

    if bpy.data.objects.get("Dampers_Tops") is None:
        return []
    units = strings_mod._damper_units()
    templates = []
    for unit in units:
        verts, faces, fmats = [], [], []
        for d in unit:
            obj = d["obj"]
            mw = _world_matrix(obj)
            me = obj.data
            mi = 1 if d["is_felt"] else 0
            idx_set = set(d["idx"])
            vmap = {}
            for poly in me.polygons:
                pverts = poly.vertices
                if not all(vi in idx_set for vi in pverts):
                    continue
                mapped = []
                for vi in pverts:
                    if vi not in vmap:
                        vmap[vi] = len(verts)
                        verts.append(mw @ me.vertices[vi].co)
                    mapped.append(vmap[vi])
                faces.append(tuple(mapped))
                fmats.append(mi)
        if not verts:
            continue
        felt_z = min((d["zmin"] for d in unit if d["is_felt"]),
                     default=min(v.z for v in verts))
        cx = sum(v.x for v in verts) / len(verts)
        cy = sum(v.y for v in verts) / len(verts)
        templates.append({
            "verts": verts, "faces": faces, "fmats": fmats,
            "felt_z": felt_z, "cx": cx, "cy": cy,
        })
    templates.sort(key=lambda t: t["cx"])
    return templates


def _nearest_decorative_template(templates, x):
    return min(templates, key=lambda t: abs(t["cx"] - x))


def _place_decorative_head(buf, template, cx, y_h, hb):
    """Imported damper shape seated on the action line (felt on the string)."""
    shift = Vector((cx - template["cx"], y_h - template["cy"],
                    hb - template["felt_z"]))
    base = len(buf.v)
    for v in template["verts"]:
        w = v + shift
        buf.v.append((w.x, w.y, w.z))
    for face, mi in zip(template["faces"], template["fmats"]):
        buf.f.append(tuple(base + i for i in face))
        buf.fm.append(mi)


def _damper_head_buf(b, cx, y0, y1, hb, half_w=0.00625):
    """Procedural fallback when the imported decorative units are missing."""
    depth = y1 - y0
    felt = [
        (y0, hb),
        (y0 + 0.14 * depth, hb + 0.0008),
        (y0 + 0.42 * depth, hb + 0.0042),
        (y1 - 0.10 * depth, hb + 0.0035),
        (y1, hb + 0.0005),
    ]
    b.profile_x(felt, cx - half_w, cx + half_w, 1)
    block = [
        (y0 + 0.08 * depth, hb + 0.005),
        (y0 + 0.20 * depth, hb + 0.0145),
        (y1 - 0.14 * depth, hb + 0.013),
        (y1 - 0.04 * depth, hb + 0.0055),
    ]
    b.profile_x(block, cx - half_w * 0.92, cx + half_w * 0.92, 0)


def _damper_lever_buf():
    b = _Buf()
    b.box(-0.0045, 0.0045, -0.003, 0.009, -0.004, 0.004, MAPLE)      # flange
    b.box(-0.004, 0.004, -0.063, 0.004, -0.003, 0.003, MAPLE)        # lever bar
    b.box(-0.004, 0.004, -0.059, -0.051, -0.0042, -0.003, FELT_RED)  # contact felt
    b.box(-0.0025, 0.0025, -0.0475, -0.0415, 0.003, 0.0065, MAPLE)   # wire post
    return b


def _build_dampers(plan, coll, mats):
    """Per-note damper action (notes 21..DAMPER_TOP): head riding its course,
    wire cranked back over the shanks, underlever lifted by the key arm's tail,
    and a sustain tray - so a pressed key or the pedal raises the dampers."""
    try:
        from . import strings as strings_mod
        courses = {c["note"]: c for c in strings_mod.course_lines()}
    except Exception:  # noqa: BLE001 - no stand-in strings to measure
        courses = {}
    if not courses:
        return 0
    pedal = _pedal_obj()
    a, b = plan["line"]

    # Damper heads must not pass through the plate struts: probe each head
    # footprint from below and slide along its course where a strut crosses.
    from mathutils.bvhtree import BVHTree
    plate_geo = ([], [])
    for name in ("Brass_Sound_Works.001", "Brass_Sound_Works.002"):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        mw = _world_matrix(obj)
        base = len(plate_geo[0])
        plate_geo[0].extend(tuple(mw @ v.co) for v in obj.data.vertices)
        plate_geo[1].extend(tuple(base + i for i in p.vertices)
                            for p in obj.data.polygons)
    plate_bvh = BVHTree.FromPolygons(*plate_geo) if plate_geo[0] else None

    def head_blocked(cx, y, hb, half_d):
        """Probe rays whose plate hit passes THROUGH the head's z-range.

        Plate surfaces below the head's bottom (the gold top skin under the
        string band) are not intersections - only raised bars and struts that
        cross between felt bottom and head top count.
        """
        if plate_bvh is None:
            return 0
        up = Vector((0.0, 0.0, 1.0))
        top = hb + 0.017
        blocked = 0
        for dx in (-0.007, 0.0, 0.007):
            for dy in (-half_d - 0.0005, -half_d / 2, half_d / 2, half_d + 0.0005):
                origin = Vector((cx + dx, y + dy, 0.845))
                dist = 0.0
                while dist < 0.085:
                    hit = plate_bvh.ray_cast(origin, up, 0.09 - dist)
                    if hit[0] is None:
                        break
                    if hb - 0.003 < hit[0].z < top + 0.002:
                        blocked += 1
                        break
                    if hit[0].z >= top + 0.002:
                        break
                    dist += (hit[0].z - origin.z) + 0.0005
                    origin = Vector((cx + dx, y + dy, hit[0].z + 0.0005))
        return blocked

    # Snapshot the imported decorative units, then retire the joined meshes.
    # Each action damper clones the nearest decorative shape but is seated on
    # the fitted action line (not the old 51-string spacing).
    tops = bpy.data.objects.get("Dampers_Tops")
    bots = bpy.data.objects.get("Dampers_Bottoms")
    deco_templates = _collect_decorative_templates()
    for obj in (tops, bots):
        if obj is not None:
            _hide_keep(obj)
            obj[REPLACED_PROP] = 1
    top_mat = (tops.data.materials[0] if tops and tops.data.materials
               else mats[FELT])
    felt_mat = (bots.data.materials[0] if bots and bots.data.materials
                else mats[FELT])
    dmats = [top_mat, felt_mat, mats[BRASS]]
    lever_proto = None

    def lift_exprs(A):
        """Damper z lift / underlever angle as max(key term, pedal term)."""
        key_z = f"max(({A:.4f}*min(r*{Q:.4f},1)-{DGAP})*0.8182,0)"
        key_t = f"max(({A:.4f}*min(r*{Q:.4f},1)-{DGAP})*18.1818,0)"
        if pedal is None:
            return key_z, f"-{key_t}"
        ped = f"max(min(pd*{PEDAL_Q:.4f},1),0)"
        return (f"max({key_z},{DPEDAL_LIFT}*{ped})",
                f"-max({key_t},{DPEDAL_LIFT / 0.045:.4f}*{ped})")

    built = 0
    clipped = []
    for n in plan["notes"]:
        note = n["note"]
        if note > DAMPER_TOP or note not in courses:
            continue
        c = courses[note]
        key, x, s = n["key"], n["x"], n["s"]
        fit = a + b * x
        F, R = c["F"], c["R"]

        def at_y(y):
            t = (y - F.y) / (R.y - F.y)
            return (F.x + t * (R.x - F.x),
                    F.z + t * (R.z - F.z) + c["r"] + 0.0002)

        # Real damper heads shorten toward the treble - and must here, where
        # the row converges with the bays' rear border bar.
        depth = 0.045 - 0.017 * (note - 21) / (DAMPER_TOP - 21)
        half_d = depth / 2.0
        y_h = s + HEAD_DY
        cx, hb = at_y(y_h)
        # Slide along the course where a plate bar crosses the damper row:
        # smallest offset that fully clears wins; otherwise least-blocked.
        # Never slide so far forward that the head meets the hammer at strike.
        y_floor = s + 0.009 + half_d
        residual = head_blocked(cx, y_h, hb, half_d)
        if residual:
            best = (residual, 0.0, cx, hb)
            for step in range(1, 12):
                for dy in (0.004 * step, -0.004 * step):
                    if y_h + dy < y_floor:
                        continue
                    cx2, hb2 = at_y(y_h + dy)
                    n_blk = head_blocked(cx2, y_h + dy, hb2, half_d)
                    if n_blk < best[0]:
                        best = (n_blk, dy, cx2, hb2)
                if best[0] == 0:
                    break
            residual, y_h, cx, hb = best[0], y_h + best[1], best[2], best[3]
            if residual:
                clipped.append((note, residual))
        linked = note <= DAMPER_LINK_TOP

        dbuf = _Buf()
        if deco_templates:
            _place_decorative_head(
                dbuf, _nearest_decorative_template(deco_templates, x),
                cx, y_h, hb)
        else:
            _damper_head_buf(dbuf, cx, y_h - half_d, y_h + half_d, hb)
        if linked:
            dbuf.bar((cx, y_h, hb), (cx, y_h, 0.875), 0.0009, 2)
            dbuf.bar((cx, y_h, 0.875), (x, fit + WIRE_DY, 0.832), 0.0009, 2)
            dbuf.bar((x, fit + WIRE_DY, 0.832), (x, fit + WIRE_DY, 0.746), 0.0009, 2)
        else:
            dbuf.bar((cx, y_h, hb), (cx, y_h, hb - 0.040), 0.0009, 2)
        dob = dbuf.to_object(f"Damper.{note:03d}", (cx, y_h, 0.0), coll, dmats)
        A = n["psi"] * (fit + DCONTACT_DY - n["hinge_y"])
        _tag(dob, "damper_head", note, lift_a=A)
        z_expr, t_expr = lift_exprs(A)
        var_specs = [("r", key, "rotation_euler[0]")]
        if pedal is not None:
            var_specs.append(("pd", pedal, "rotation_euler[0]"))
        _drive(dob, "location", 2, z_expr, var_specs)

        if linked:
            if lever_proto is None:
                proto_obj = _damper_lever_buf().to_object(
                    "ActionMesh.DamperLever", (0, 0, 0), coll, mats)
                lever_proto = proto_obj.data
                bpy.data.objects.remove(proto_obj, do_unlink=True)
            lev = bpy.data.objects.new(f"DamperLever.{note:03d}", lever_proto)
            lev.location = (x, fit + DLEVER_DY, DLEVER_Z)
            coll.objects.link(lev)
            _tag(lev, "damper_lever", note)
            _drive(lev, "rotation_euler", 0, t_expr, list(var_specs))
        built += 1

    # Sustain lift tray under the underlever fronts.
    link = [n for n in plan["notes"] if n["note"] <= DAMPER_LINK_TOP]
    if link:
        tbuf = _Buf()
        pts = []
        for x in (link[0]["x"] - 0.012, link[-1]["x"] + 0.012):
            yc = a + b * x + DTRAY_DY
            pts += [(x, yc - 0.010, 0.7305), (x, yc + 0.010, 0.7305),
                    (x, yc + 0.010, 0.7345), (x, yc - 0.010, 0.7345)]
        fcs = [(3, 2, 1, 0), (4, 5, 6, 7)]
        fcs += [(i, (i + 1) % 4, 4 + (i + 1) % 4, 4 + i) for i in range(4)]
        tbuf._emit(pts, fcs, WALNUT)
        tray = tbuf.to_object("Damper_Tray", (0, 0, 0), coll, mats)
        _tag(tray, "damper_tray", -1)
        if pedal is not None:
            _drive(tray, "location", 2,
                   f"{DPEDAL_LIFT / 0.8182:.4f}*max(min(pd*{PEDAL_Q:.4f},1),0)",
                   [("pd", pedal, "rotation_euler[0]")])
    if clipped:
        print(f"[action] damper heads still touching plate: {clipped}")
    return built


def _tag_targets(plan):
    # The new drivers' first evaluation must see freshly-copied target data, or
    # they compile against stale evaluated copies and stick invalid for the
    # session (reopened files build the graph from scratch and are fine).
    for n in plan["notes"]:
        n["key"].update_tag()
    pedal = _pedal_obj()
    if pedal is not None:
        pedal.update_tag()


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

    # Damper action: a pressed key lifts its damper; the pedal lifts them all.
    damper_err = 0.0
    probe = bpy.data.objects.get("Damper.060")
    pedal = _pedal_obj()
    if probe is not None:
        key = next(n["key"] for n in plan["notes"] if n["note"] == 60)
        key.rotation_euler.x = PRESS_ANGLE
        key.update_tag()
        deps.update()
        key_lift = probe.evaluated_get(deps).location.z
        key.rotation_euler.x = 0.0
        key.update_tag()
        ped_lift = None
        if pedal is not None:
            pedal.rotation_euler.x = math.radians(5.0)
            pedal.update_tag()
            deps.update()
            ped_lift = probe.evaluated_get(deps).location.z
            pedal.rotation_euler.x = 0.0
            pedal.update_tag()
        deps.update()
        damper_err = abs((ped_lift if ped_lift is not None else DPEDAL_LIFT)
                         - DPEDAL_LIFT)
        rows.append((60, "damper", round(key_lift, 5),
                     round(ped_lift, 5) if ped_lift is not None else None, 0))
        if key_lift < 0.003:
            damper_err = max(damper_err, 1.0)
    return {"rows": rows, "heel_err": worst_heel, "strike_err": worst_strike,
            "damper_err": damper_err}


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
    seated = _seat_bridge_on_soundboard()
    flagged = _strike_heights(plan)
    coll = _fresh_collection()
    mats = _materials()
    _build_units(plan, coll, mats)
    dampers = _build_dampers(plan, coll, mats)
    _tag_targets(plan)
    checks = _verify(plan)
    szs = [n["strike_z"] for n in plan["notes"]]
    a, b = plan["line"]
    return {
        "notes": len(plan["notes"]),
        "objects": len(coll.objects),
        "soundboard": cut,
        "bridge_seat": seated,
        "action_line": (round(a, 4), round(b, 4)),
        "strike_z": (round(min(szs), 4), round(max(szs), 4)),
        "shank": (round(min(n["shank"] for n in plan["notes"]), 4),
                  round(max(n["shank"] for n in plan["notes"]), 4)),
        "dampers": dampers,
        "low_clearance_notes": flagged,
        "heel_err": round(checks["heel_err"], 5),
        "strike_err": round(checks["strike_err"], 5),
        "damper_err": round(checks["damper_err"], 5),
    }
