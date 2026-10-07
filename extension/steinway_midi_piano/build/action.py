"""Build the Steinway grand (double-escapement) action behind the keys.

The imported furniture model has keys and a harp but nothing in between. This
builds the full 88-note grand action in its real arrangement (player at -Y):

    key front .. balance rail (the key hinge) .. key stick (cranked into its
    action lane) .. capstan .. backcheck .. key end -> damper underlever

    hammer flange rail (front, under the pin field)
      `- hammer shank -> knuckle (~19 mm behind the center pin) -> hammer head
         at the strike line, tail facing the backcheck
    wippen (flange at the REAR on the wippen rail, heel on the capstan)
      |- jack at its front end, top under the knuckle, tender under the
      |  let-off button
      `- repetition lever on a post, reaching forward through the jack window
         to the drop screw in front of the hammer center pin

Rails are Steinway's tubular metallic action frame (brass tubes) on five cast
action brackets; the hammer rest rail, let-off rail, key frame (balance rail,
back rail with cloth) and the damper action (underlevers on their rail,
sostenuto rod, sustain tray, guide rail, vertical wires, felted heads) complete
it. Damper heads use wedge felts on the mono/bi/trichords and flat felts in
the upper treble; notes above 88 are undamped, as on a real grand.

Action lanes are evenly spaced per section (bass 21-49, treble 50-108, with
gaps at the internal brackets) - real keys are cranked behind the balance rail
to reach them. ``build/strings.py`` anchors each course on its lane, so every
hammer and damper sits square under its own unisons.

Everything is rigged with drivers off each key's ``rotation_euler.x`` (the
channel the live-MIDI animator writes), staying inside Blender's trusted
simple-expression subset (no script auto-run needed). With
``q = clamp(rot_x / press_angle)``:

- key stick    ``psi * q``            (per-note gain -> uniform capstan rise)
- wippen       ``-OMEGA * q``         (heel rides the capstan)
- jack         ``JG * max(q - lo, 0)`` (tender pinned on the let-off button)
- rep lever    ``LG * max(q - lo, 0)`` (tip stopped by the drop screw)
- hammer       ``REST + min(SLOPE*min(q,lo) - DROP*ramp + IMP*key["hammer"],
               CAP)`` - pushed by the jack until let-off, thrown to the string
               by the live strike channel, caught at the backcheck
- dampers      lift once the key end picks up its underlever (~45 % travel)
               or the sustain pedal raises the tray

Every gain and per-note constant is also written to the objects as
``action_*`` custom properties, which the web viewer reads (glTF extras) to
reproduce the same motion.

Mesh data is shared wherever parts are identical (wippens, jacks, repetition
levers, underlevers; hammers and damper heads in size groups), so the GLB
stores one copy per shape. Pure ``bpy``/``bmesh`` (no ``bpy.ops``),
headless-safe, idempotent: rebuilding replaces the ``Steinway_Action``
collection.
"""

import math

import bmesh
import bpy
import mathutils
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------- #
# Key / strike-line constants (world meters; +Y toward the tail, +Z up)
# --------------------------------------------------------------------------- #
PRESS_ANGLE = math.radians(3.5)     # full key dip the drivers normalize against
Q = 1.0 / PRESS_ANGLE               # rot_x -> press fraction
STRIKE_FRAC = 0.09                  # strike point as a fraction of string length

# Action lanes: evenly spaced per section, stepping over the plate struts that
# cross the strike/damper band (a real scale leaves exactly these gaps, and the
# action brackets stand in them). Strut spans were measured on the model's
# plate along the strike and damper lines (x, metres).
BREAK_NOTE = 50                     # first treble-section note (strings.BREAK_NOTE)
BASS_LO_X = -0.4460                 # lane of note 21 (clear of the bass-end strut)
BASS_TOP_X = -0.0815                # lane of note 49 (clear of the break struts)
TENOR_X = -0.018                    # lane of note 50 (treble section start)
STRUTS = ((0.3115, 0.3230), (0.4980, 0.5090))   # treble struts to step over
STRUT_CLEAR = 0.0068                # lane center -> strut face (half head + air)
LANE_CLEAR = 0.0017                 # free space between neighbor lanes

# Hammer (frame: center pin at HC; +Y local runs along the shank to the head)
HC_DY = -0.1243          # hammer center pin, relative to the strike line
HC_Z = 0.832
LH = 0.128               # center pin -> head center line, along the shank
LK = 0.019               # knuckle station along the shank
KNUCKLE_DZ = -0.0075     # knuckle center below the shank axis
KNUCKLE_R = 0.0062
SHANK_R = 0.0037
PHI_TARGET = 0.075       # shank angle at the strike (just above horizontal)
BLOW = 0.047             # hammer blow distance (crown travel to the string)
LETOFF_GAP = 0.002       # crown-to-string gap at let-off
CHECK_GAP = 0.016        # crown-to-string gap when caught by the backcheck
HAM_IMPULSE = 0.30       # gain on the live key["hammer"] strike channel
HAMMER_GROUPS = 8        # hammer head sizes (bass -> treble)
RHO_NOM = math.hypot(LH, 0.044)
REST = PHI_TARGET - BLOW / RHO_NOM  # common rest angle (straight hammer line)

# Wippen / jack / repetition lever (world z; y from the knuckle contact)
W_Z = 0.7565             # wippen center pin height
JACK_Z = 0.7605          # jack center pin height
REP_Z = 0.8015           # repetition-lever center pin height
JACK_W_ARM = 0.090       # wippen center -> jack top contact
HEEL_W_ARM = 0.045       # wippen center -> heel (capstan)
REP_W_ARM = 0.045        # wippen center -> repetition-lever post
TENDER_CROWN = (-0.0135, 0.0062)   # tender crown, jack-local (y, z)
TENDER_REACH = -TENDER_CROWN[0] - 0.002   # crown in front of the jack contact
LO_NOM = 0.88            # nominal let-off point (fraction of key travel)

# Key stick / key frame
STICK_BOT = 0.7063       # = visible white key underside
STICK_TOP = 0.7300
CAP_TOP = 0.7410         # capstan top = wippen heel cushion at rest
CRANK_Y = (-0.695, -0.655)   # key sticks crank from key x to lane x here
KEYBED_Z = 0.674
STICK_END_DY = 0.040     # damped key end behind the strike line
STICK_END_UNDAMPED = 0.030

# Damper action (y from the strike line). The underlevers pivot on a rail
# behind the belly rail (they reach under it, through the opening cut by
# _open_belly_rail) and run forward over the key ends: key contact in front,
# wire block between, like a real grand.
DAMPER_TOP = 88
HEAD_DY = 0.042          # damper head / wire line behind the strike line
DP_DY = 0.150            # underlever center pin
DP_Z = 0.7505
DC_ARM = 0.120           # underlever pin -> key-end contact felt (s + 0.030)
DW_ARM = 0.108           # underlever pin -> wire block (= HEAD_DY line)
DT_ARM = 0.040           # underlever pin -> sustain tray
DLIFT_Q0 = 0.30          # dampers start lifting at this key travel
DPEDAL_LIFT = 0.006      # damper lift at full sustain pedal
PEDAL_Q = 1.0 / math.radians(5.0)   # pedal rot -> press fraction (anim.PEDAL_ANGLE)
GUIDE_Z = (0.848, 0.858)  # damper guide rail (under the strings)

SOUNDBOARD = "Soundboard"
BRIDGE = "String_Supports_02"
BRIDGE_SEAT_MARK = "steinway_bridge_seated"
BRIDGE_SEAT_VERSION = 1
BRIDGE_SEAT_LIFT = 0.0015   # world +Z; ~0.6 mm clearance after ~0.9 mm overlap
CUT_MARGIN = 0.082       # soundboard removed for y < strike line + this margin
CUT_DEEP = 0.150         # extra slot (wire drop of the v1 action; kept as is)
CUT_DEEP_X = 0.428
CUT_MARK = "steinway_action_cut"
CUT_VERSION = 2
RIM = "Inside_Rim_Case"
BELLY_MARK = "steinway_belly_opening"
BELLY_VERSION = 1
BELLY_Z = 0.790          # belly rail underside (opening below it)
BELLY_X = (-0.492, 0.858)

COLLECTION = "Steinway_Action"
PART_PROP = "action_part"
NOTE_PROP = "action_note"
REPLACED_PROP = "steinway_replaced"

# Meshes the hammers must clear from below (strike-height raycast targets).
_OBSTACLES = (
    "Strings_Full", "Tuning_Pins",
    "Brass_Sound_Works.001", "Brass_Sound_Works.002",
    "String_Supports_01", "String_Supports_02", SOUNDBOARD,
)
_PLATE = ("Brass_Sound_Works.001", "Brass_Sound_Works.002")

_MATS = (
    # name, rgba, roughness, metallic
    ("Action_Hornbeam", (0.70, 0.55, 0.36, 1.0), 0.55, 0.0),   # shanks, wippens
    ("Action_Maple", (0.62, 0.44, 0.24, 1.0), 0.55, 0.0),      # rails, flanges
    ("Action_Mahogany", (0.26, 0.10, 0.05, 1.0), 0.45, 0.0),   # hammer moldings
    ("Action_Spruce", (0.80, 0.67, 0.47, 1.0), 0.65, 0.0),     # key sticks, frame
    ("Action_Felt_White", (0.92, 0.90, 0.84, 1.0), 0.95, 0.0), # hammer felt
    ("Action_Felt_Red", (0.42, 0.05, 0.07, 1.0), 0.95, 0.0),   # cushions, punchings
    ("Action_Felt_Green", (0.08, 0.22, 0.13, 1.0), 0.95, 0.0), # key frame cloth
    ("Action_Brass", (0.80, 0.63, 0.30, 1.0), 0.30, 1.0),      # tubes, capstans
    ("Action_Steel", (0.72, 0.72, 0.74, 1.0), 0.30, 1.0),      # pins, screws
    ("Action_Leather", (0.55, 0.38, 0.22, 1.0), 0.75, 0.0),    # knuckles, backchecks
    ("Action_Iron", (0.11, 0.11, 0.12, 1.0), 0.45, 0.6),       # action brackets
)
(HORNBEAM, MAPLE, MAHOGANY, SPRUCE, FELT, FELT_RED, FELT_GREEN,
 BRASS, STEEL, LEATHER, IRON) = range(len(_MATS))

SMOOTH_ANGLE = math.radians(35.0)


# --------------------------------------------------------------------------- #
# Mesh toolkit: rounded prisms, tubes, oriented boxes (closed shells)
# --------------------------------------------------------------------------- #
def _area2(pts):
    return sum(pts[i - 1][0] * p[1] - p[0] * pts[i - 1][1]
               for i, p in enumerate(pts))


def _round_poly(pts, r, segs=1):
    """Fillet every corner of a 2D polygon (quadratic arcs, ``segs`` steps)."""
    if r <= 0.0:
        return [tuple(p) for p in pts]
    out, n = [], len(pts)
    for i in range(n):
        p = Vector(pts[i])
        a, c = Vector(pts[i - 1]), Vector(pts[(i + 1) % n])
        da, dc = a - p, c - p
        d = min(r, 0.45 * da.length, 0.45 * dc.length)
        if d < 1e-6:
            out.append((p.x, p.y))
            continue
        p0, p1 = p + da.normalized() * d, p + dc.normalized() * d
        for k in range(segs + 1):
            t = k / segs
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p + t * t * p1
            out.append((q.x, q.y))
    return out


def _inset(pts, c):
    """Miter-offset a CCW polygon inward by ``c``."""
    n, out = len(pts), []
    for i in range(n):
        p = Vector(pts[i])
        e1 = (p - Vector(pts[i - 1]))
        e2 = (Vector(pts[(i + 1) % n]) - p)
        if e1.length < 1e-9 or e2.length < 1e-9:
            out.append((p.x, p.y))
            continue
        n1 = Vector((-e1.y, e1.x)).normalized()
        n2 = Vector((-e2.y, e2.x)).normalized()
        m = n1 + n2
        if m.length < 1e-6:
            m = n1
        m.normalize()
        q = p + m * (c / max(m.dot(n1), 0.35))
        out.append((q.x, q.y))
    return out


class _Buf:
    """Accumulates verts/faces (+ per-face material index) for one mesh."""

    def __init__(self):
        self.v, self.f, self.fm = [], [], []

    def _emit(self, verts, faces, mat):
        base = len(self.v)
        self.v += [tuple(v) for v in verts]
        self.f += [tuple(base + i for i in face) for face in faces]
        self.fm += [mat] * len(faces)

    def merge(self, other, offset=(0.0, 0.0, 0.0)):
        ox, oy, oz = offset
        base = len(self.v)
        self.v += [(x + ox, y + oy, z + oz) for x, y, z in other.v]
        self.f += [tuple(base + i for i in f) for f in other.f]
        self.fm += list(other.fm)

    # -- prisms ------------------------------------------------------------ #
    def prism(self, poly, a0, a1, origin, U, V, W, mat, r=0.0, c=0.0, segs=1):
        """Extrude a 2D outline (coords along V, W) from a0 to a1 along U.

        ``r`` fillets the outline corners, ``c`` chamfers both cap rims.
        """
        pts = _round_poly(poly, r, segs) if r > 0 else [tuple(p) for p in poly]
        if _area2(pts) < 0:
            pts.reverse()
        a0, a1 = min(a0, a1), max(a0, a1)
        c = min(c, 0.3 * (a1 - a0))
        origin, U, V, W = Vector(origin), Vector(U), Vector(V), Vector(W)

        def ring(p2, a):
            return [origin + U * a + V * u + W * w for u, w in p2]

        if c > 1e-7:
            ins = _inset(pts, c)
            rings = [ring(ins, a0), ring(pts, a0 + c), ring(pts, a1 - c), ring(ins, a1)]
        else:
            rings = [ring(pts, a0), ring(pts, a1)]
        n = len(pts)
        verts = [p for rg in rings for p in rg]
        faces = [tuple(range(n - 1, -1, -1))]
        for k in range(len(rings) - 1):
            b0, b1 = k * n, (k + 1) * n
            faces += [(b0 + i, b0 + (i + 1) % n, b1 + (i + 1) % n, b1 + i)
                      for i in range(n)]
        last = (len(rings) - 1) * n
        faces.append(tuple(last + i for i in range(n)))
        self._emit(verts, faces, mat)

    def profile_x(self, poly, x0, x1, mat, r=0.0006, c=0.0, segs=1):
        """Side outline in (y, z) extruded across x0..x1."""
        self.prism(poly, x0, x1, (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                   mat, r, c, segs)

    def profile_y(self, poly, y0, y1, mat, r=0.0006, c=0.0, segs=1):
        """Cross-section in (x, z) extruded along y0..y1."""
        self.prism(poly, y0, y1, (0, 0, 0), (0, 1, 0), (1, 0, 0), (0, 0, 1),
                   mat, r, c, segs)

    def box(self, x0, x1, y0, y1, z0, z1, mat, r=0.0006, c=0.0):
        y0, y1 = min(y0, y1), max(y0, y1)
        z0, z1 = min(z0, z1), max(z0, z1)
        self.profile_x([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], x0, x1, mat, r, c)

    def obox(self, center, u, v, w, hu, hv, hw, mat, r=0.0006, c=0.0):
        """Oriented box: half sizes hu/hv/hw along unit axes u/v/w."""
        u, v, w = Vector(u).normalized(), Vector(v).normalized(), Vector(w).normalized()
        self.prism([(-hv, -hw), (hv, -hw), (hv, hw), (-hv, hw)], -hu, hu,
                   center, u, v, w, mat, r, c)

    # -- tubes ---------------------------------------------------------------- #
    def tube(self, p0, p1, r0, mat, n=10, r1=None, c=0.0):
        """Round (n-gon) tube/frustum from p0 to p1, capped; ``c`` chamfers ends."""
        p0, p1 = Vector(p0), Vector(p1)
        r1 = r0 if r1 is None else r1
        d = p1 - p0
        L = d.length
        if L < 1e-9:
            return
        d /= L
        side = d.cross(Vector((0.0, 0.0, 1.0)))
        if side.length < 1e-6:
            side = d.cross(Vector((0.0, 1.0, 0.0)))
        side.normalize()
        up = d.cross(side).normalized()
        c = min(c, 0.3 * L, 0.5 * min(r0, r1))

        def ring(center, r):
            return [center + (side * math.cos(t) + up * math.sin(t)) * r
                    for t in (2.0 * math.pi * k / n for k in range(n))]

        if c > 1e-7:
            rings = [ring(p0, r0 - c), ring(p0 + d * c, r0),
                     ring(p1 - d * c, r1), ring(p1, r1 - c)]
        else:
            rings = [ring(p0, r0), ring(p1, r1)]
        verts = [p for rg in rings for p in rg]
        faces = [tuple(range(n - 1, -1, -1))]
        for k in range(len(rings) - 1):
            b0, b1 = k * n, (k + 1) * n
            faces += [(b0 + i, b0 + (i + 1) % n, b1 + (i + 1) % n, b1 + i)
                      for i in range(n)]
        last = (len(rings) - 1) * n
        faces.append(tuple(last + i for i in range(n)))
        self._emit(verts, faces, mat)

    def cyl(self, axis, center, r, a0, a1, mat, n=10, c=0.0):
        """Axis-aligned cylinder; ``center`` = the two other coords."""
        u, w = center
        if axis == "x":
            p0, p1 = (a0, u, w), (a1, u, w)
        elif axis == "y":
            p0, p1 = (u, a0, w), (u, a1, w)
        else:
            p0, p1 = (u, w, a0), (u, w, a1)
        self.tube(p0, p1, r, mat, n=n, c=c)

    def wire(self, pts, r, mat, n=6):
        """Polyline of round wire (joints overlap; no miters needed at this size)."""
        for p0, p1 in zip(pts, pts[1:]):
            self.tube(p0, p1, r, mat, n=n)

    # -- output ----------------------------------------------------------------- #
    def to_mesh(self, name, mats, origin=(0.0, 0.0, 0.0)):
        ox, oy, oz = origin
        me = bpy.data.meshes.new(name)
        me.from_pydata([(x - ox, y - oy, z - oz) for x, y, z in self.v], [], self.f)
        for m in mats:
            me.materials.append(m)
        for poly, mi in zip(me.polygons, self.fm):
            poly.material_index = mi
        me.validate()
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=SMOOTH_ANGLE)
        me.update()
        return me

    def to_object(self, name, origin, coll, mats, local=False):
        """Object at ``origin``. Buffer coords are world unless ``local``."""
        me = self.to_mesh(name, mats, (0.0, 0.0, 0.0) if local else origin)
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
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None:
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


def _place(start, pitch, count):
    """Lay ``count`` lanes from ``start`` at ``pitch``, hopping the struts."""
    xs, x = [], start
    for _ in range(count):
        for lo, hi in STRUTS:
            if x + STRUT_CLEAR > lo and x - STRUT_CLEAR < hi:
                x = hi + STRUT_CLEAR
        xs.append(x)
        x += pitch
    return xs


def _lanes(keys):
    """Action-lane x per note: even spacing per section, struts stepped over."""
    x_hi = keys[-1].location.x
    notes = [int(k["midi_note"]) for k in keys]
    bass = [n for n in notes if n < BREAK_NOTE]
    treble = [n for n in notes if n >= BREAK_NOTE]
    lanes = {}
    pb = (BASS_TOP_X - BASS_LO_X) / (len(bass) - 1)
    for i, n in enumerate(bass):
        lanes[n] = BASS_LO_X + i * pb
    lo, hi = 0.005, 0.020                      # treble pitch: land 108 on its key
    for _ in range(60):
        pt = 0.5 * (lo + hi)
        if _place(TENOR_X, pt, len(treble))[-1] < x_hi:
            lo = pt
        else:
            hi = pt
    for n, x in zip(treble, _place(TENOR_X, pt, len(treble))):
        lanes[n] = x
    return lanes, pb, pt


def _plan(keys, meas):
    """Per-note action geometry on the fitted strike line.

    The strike line is fitted through each string's preferred strike point
    (~1/8 of its speaking length behind the front end, clamped in front of
    the model's damper line). This fit is shared with build/strings.py and
    build/harp.py and must stay stable. Each note gets its action lane ``ax``
    and the strike line ``s`` evaluated there.
    """
    xs = [k.location.x for k in keys]
    prefer = []
    for sf, sr, df in zip(meas["s_front"], meas["s_rear"], meas["d_front"]):
        s = sf + STRIKE_FRAC * (sr - sf)
        s = min(s, df - 0.0085)
        prefer.append(max(s, sf + 0.004))
    a, b = _fit_line(xs, prefer)
    lanes, pb, pt = _lanes(keys)
    plan = []
    for key in keys:
        note = int(key["midi_note"])
        ax = lanes[note]
        pitch = pb if note < BREAK_NOTE else pt
        plan.append({
            "note": note,
            "key": key,
            "color": key.get("key_color", "white"),
            "x": key.location.x,
            "ax": ax,
            "s": a + b * ax,
            "lane_w": pitch - LANE_CLEAR,
            "hinge_y": key.location.y,
            "hinge_z": key.location.z,
        })
    return {"line": (a, b), "notes": plan, "pitch": (pb, pt)}


# --------------------------------------------------------------------------- #
# Soundboard cut / bridge seat (the model's slab extends under the strike zone)
# --------------------------------------------------------------------------- #
def _cut_soundboard(plan):
    """Carve the belly-rail gap: the imported slab runs under the strike zone
    where a real grand has open air from the keybed up to the strings."""
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


def _open_belly_rail():
    """Open the inner rim's front wall below the belly rail.

    The model's inner case is a closed box whose front wall (y ~-0.398) runs
    from the keybed up to the soundboard. On a real grand that wall is the
    belly rail - a beam under the soundboard edge - and the damper underlevers
    reach back underneath it to their rail. Cut the wall's front and back
    faces below BELLY_Z across the action width, close the beam's underside
    and the opening's ends, and add a dark backing panel in the hollow so the
    opening reads as depth rather than see-through.
    """
    rim = bpy.data.objects.get(RIM)
    if rim is None or rim.type != "MESH":
        return "missing"
    if rim.get(BELLY_MARK, 0) == BELLY_VERSION:
        return "already-open"
    mw = rim.matrix_world
    inv = mw.inverted()
    n3 = mw.to_3x3()
    bm = bmesh.new()
    bm.from_mesh(rim.data)

    def wall_faces():
        out = []
        for f in bm.faces:
            nw = (n3 @ f.normal).normalized()
            ys = [(mw @ v.co).y for v in f.verts]
            if abs(nw.y) > 0.95 and max(ys) < -0.370 and min(ys) > -0.402:
                out.append(f)
        return out

    walls = wall_faces()
    if not walls:
        bm.free()
        return "no-wall"
    y_front = min((mw @ v.co).y for f in walls for v in f.verts)
    y_back = max((mw @ v.co).y for f in walls for v in f.verts)
    mat_idx = walls[0].material_index
    for co, no in (((0, 0, BELLY_Z), (0, 0, 1)), ((BELLY_X[0], 0, 0), (1, 0, 0)),
                   ((BELLY_X[1], 0, 0), (1, 0, 0))):
        geom = wall_faces()
        vs = {v for f in geom for v in f.verts}
        es = {e for f in geom for e in f.edges}
        bmesh.ops.bisect_plane(bm, geom=geom + list(vs) + list(es),
                               plane_co=inv @ Vector(co),
                               plane_no=(n3.transposed() @ Vector(no)).normalized())
    doomed = []
    for f in wall_faces():
        c = mw @ f.calc_center_median()
        if c.z < BELLY_Z and BELLY_X[0] < c.x < BELLY_X[1]:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")

    def quad(pts, outward):
        vs = [bm.verts.new(inv @ Vector(p)) for p in pts]
        f = bm.faces.new(vs)
        f.material_index = mat_idx
        f.normal_update()
        if (n3 @ f.normal).dot(Vector(outward)) < 0.0:
            f.normal_flip()

    z0 = 0.6765
    x0, x1 = BELLY_X
    quad([(x0, y_front, BELLY_Z), (x1, y_front, BELLY_Z), (x1, y_back, BELLY_Z),
          (x0, y_back, BELLY_Z)], (0, 0, -1))                      # beam underside
    quad([(x0, y_front, z0), (x0, y_back, z0), (x0, y_back, BELLY_Z),
          (x0, y_front, BELLY_Z)], (1, 0, 0))                       # opening ends
    quad([(x1, y_front, z0), (x1, y_back, z0), (x1, y_back, BELLY_Z),
          (x1, y_front, BELLY_Z)], (-1, 0, 0))
    yb = -0.150                                                      # backing panel
    quad([(x0, yb, z0), (x1, yb, z0), (x1, yb, 0.834), (x0, yb, 0.834)], (0, -1, 0))
    bm.to_mesh(rim.data)
    bm.free()
    rim.data.update()
    rim[BELLY_MARK] = BELLY_VERSION
    return f"opened {len(doomed)} wall faces below z {BELLY_Z}"


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
    return f"lifted {BRIDGE_SEAT_LIFT * 1000:.1f} mm"


# --------------------------------------------------------------------------- #
# Geometry solve: strike heights, hammer groups, kinematic gains
# --------------------------------------------------------------------------- #
def _bvh(names):
    from mathutils.bvhtree import BVHTree

    verts, polys = [], []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        mw = _world_matrix(obj)
        base = len(verts)
        verts += [tuple(mw @ v.co) for v in obj.data.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in obj.data.polygons]
    return BVHTree.FromPolygons(verts, polys) if verts else None


def _min_clearance(bvh, x, y, z0=0.845):
    up = Vector((0.0, 0.0, 1.0))
    zmin = 0.8950                       # nothing above: the string band's top
    for dx in (-0.0035, 0.0, 0.0035):
        for dy in (-0.003, 0.0, 0.003):
            hit = bvh.ray_cast(Vector((x + dx, y + dy, z0)), up, 0.10)
            if hit[0] is not None:
                zmin = min(zmin, hit[0].z)
    return zmin


def _rot(phi, y, z):
    """Rotate a local (y, z) point about the x axis by ``phi``."""
    c, s = math.cos(phi), math.sin(phi)
    return y * c - z * s, y * s + z * c


def _knuckle_low(phi):
    """Lowest point of the knuckle (relative to the center pin) at angle phi."""
    cy, cz = _rot(phi, LK, KNUCKLE_DZ)
    return cy, cz - KNUCKLE_R


def _crown(phi, bore):
    return _rot(phi, LH, bore)


def _phi_for_crown_z(dz, bore):
    """Shank angle that puts the crown ``dz`` above the center pin."""
    lo, hi = -0.6, 0.6
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _crown(mid, bore)[1] < dz:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _hammer_group(note):
    return min(HAMMER_GROUPS - 1, (note - 21) * HAMMER_GROUPS // 88)


def _hammer_dims(g):
    """Head width / felt half-depth / felt thickness by size group (bass -> treble)."""
    t = g / (HAMMER_GROUPS - 1)
    return {
        "width": 0.0120 - 0.0022 * t,
        "felt_d": 0.0130 - 0.0045 * t,
        "felt_t": 0.0260 - 0.0090 * t,
    }


def _kinematics():
    """Uniform action ratios (the stack geometry is identical in every lane)."""
    ky, kz = _knuckle_low(REST)                      # knuckle contact at rest
    omega = (BLOW - LETOFF_GAP) / RHO_NOM / LO_NOM * ky / JACK_W_ARM
    k = {
        "knuckle_dy": ky, "knuckle_z": HC_Z + kz,
        "omega": omega,
        "cap_rise": omega * HEEL_W_ARM,
        "slope": JACK_W_ARM * omega / ky,
    }
    # Distances from the wippen center (rear) forward to each contact.
    jack_y = ky + 0.002                              # jack pin (from HC)
    tender = ky - TENDER_REACH                       # tender tip (from HC)
    tip = -0.012                                     # rep-lever tip (from HC)
    w_y = ky + JACK_W_ARM                            # wippen center (from HC)
    rep_y = ky + (JACK_W_ARM - REP_W_ARM)            # rep pin (from HC)
    k.update({
        "jack_dy": jack_y, "tender_dy": tender, "tip_dy": tip,
        "w_dy": w_y, "rep_dy": rep_y, "cap_dy": w_y - HEEL_W_ARM,
        "d_tender": w_y - tender, "tender_arm": jack_y - tender,
        "d_tip": w_y - tip, "rep_arm": rep_y - tip,
    })
    k["jack_gain"] = k["d_tender"] * omega / k["tender_arm"]
    k["lever_gain"] = k["d_tip"] * omega / k["rep_arm"]
    return k


def _solve(plan):
    """Strike heights, hammer bores per size group, per-note rest/let-off."""
    bvh = _bvh(_OBSTACLES)
    k = _kinematics()
    notes = plan["notes"]
    for n in notes:
        n["hc_y"] = n["s"] + HC_DY
        cy, _ = _crown(PHI_TARGET, 0.044)
        n["strike_z"] = _min_clearance(bvh, n["ax"], n["hc_y"] + cy) - 0.0008
        n["group"] = _hammer_group(n["note"])
    # Bore per group: big enough that no note needs a steeper strike angle.
    bores = {}
    for g in range(HAMMER_GROUPS):
        need = []
        for n in notes:
            if n["group"] != g:
                continue
            dz = n["strike_z"] - HC_Z
            # crown_z(phi) = LH sin phi + bore cos phi
            need.append((dz - LH * math.sin(PHI_TARGET)) / math.cos(PHI_TARGET))
        bores[g] = math.ceil(max(need) * 2000.0) / 2000.0     # 0.5 mm steps
    flagged = []
    for n in notes:
        bore = bores[n["group"]]
        rho = math.hypot(LH, bore)
        phi_s = _phi_for_crown_z(n["strike_z"] - HC_Z, bore)
        n["bore"], n["rho"], n["phi_s"] = bore, rho, phi_s
        n["cap"] = phi_s - REST
        lo = (n["cap"] - LETOFF_GAP / rho) / k["slope"]
        n["letoff"] = min(max(lo, 0.80), 0.95)
        n["drop"] = (CHECK_GAP - LETOFF_GAP) / rho
        n["phi_c"] = phi_s - CHECK_GAP / rho
        if not (0.0 <= phi_s <= PHI_TARGET + 1e-6):
            flagged.append((n["note"], round(phi_s, 3)))
    return k, bores, flagged


# --------------------------------------------------------------------------- #
# Shared part meshes (local frames at their center pins)
# --------------------------------------------------------------------------- #
def _hammer_buf(g, bore):
    """Hammer: butt on the center pin, round shank, leather knuckle, mahogany
    molding with a tail toward the backcheck, egg-shaped felt head."""
    dims = _hammer_dims(g)
    hw, d, ft = dims["width"] / 2.0, dims["felt_d"], dims["felt_t"]
    b = _Buf()
    b.cyl("x", (0.0, 0.0), 0.0060, -0.0036, 0.0036, HORNBEAM, n=14, c=0.0004)  # butt
    b.tube((0.0, 0.003, 0.0), (0.0, LH - 0.002, 0.0), SHANK_R, HORNBEAM, n=10)
    b.cyl("x", (LK, KNUCKLE_DZ), KNUCKLE_R, -0.0046, 0.0046, LEATHER, n=16, c=0.0006)
    b.box(-0.0034, 0.0034, LK - 0.004, LK + 0.004, KNUCKLE_DZ, -0.001, HORNBEAM,
          r=0.0008)                                                  # knuckle core block
    zb = bore - ft
    y0 = LH
    molding = [
        (y0 - 0.0055, -0.0070), (y0 - 0.0055, zb - 0.002), (y0 - 0.0040, zb + 0.001),
        (y0 + 0.0040, zb + 0.001), (y0 + 0.0055, zb - 0.002), (y0 + 0.0055, 0.0030),
        (y0 + 0.0105, -0.0035), (y0 + 0.0135, -0.0090), (y0 + 0.0115, -0.0130),
        (y0 + 0.0030, -0.0115), (y0 - 0.0035, -0.0095),
    ]
    b.profile_x(molding, -(hw - 0.0004), hw - 0.0004, MAHOGANY, r=0.0012, c=0.0004)
    felt = [(y0 + 0.0052, zb - 0.0045), (y0 - 0.0052, zb - 0.0045)]
    steps = 14
    for i in range(steps + 1):
        t = math.pi * i / steps
        y = y0 - d * math.cos(t)
        z = zb + 0.002 + (bore - zb - 0.002) * (math.sin(t) ** 0.65)
        felt.append((y, z))
    b.profile_x(felt, -hw, hw, FELT, r=0.0, c=0.0007)
    return b, molding


def _wippen_buf(k):
    """Wippen body (center pin at the rear, jack fork at the front), heel and
    cushion over the capstan, repetition-lever post and spring."""
    b = _Buf()
    jy = -JACK_W_ARM + 0.002                          # jack pin (local y)
    hy = -HEEL_W_ARM
    py = -REP_W_ARM
    pz = REP_Z - W_Z
    body = [
        (0.0070, -0.0040), (0.0070, 0.0055), (-0.0120, 0.0080), (-0.0300, 0.0105),
        (-0.0600, 0.0105), (jy + 0.0110, 0.0075), (jy + 0.0110, -0.0060),
        (-0.0560, -0.0080), (-0.0360, -0.0080), (-0.0150, -0.0070), (0.0, -0.0065),
    ]
    b.profile_x(body, -0.0042, 0.0042, HORNBEAM, r=0.0015, c=0.0004)
    for sx in (-1.0, 1.0):                            # jack fork cheeks
        b.profile_x([(jy - 0.0080, -0.0050), (jy + 0.0120, -0.0060),
                     (jy + 0.0120, 0.0080), (jy - 0.0060, 0.0090)],
                    sx * 0.0036, sx * 0.0050, HORNBEAM, r=0.0012)
    b.cyl("x", (jy, JACK_Z - W_Z), 0.0007, -0.0052, 0.0052, STEEL, n=6)   # jack pin
    b.box(-0.0042, 0.0042, hy - 0.0085, hy + 0.0085, CAP_TOP - W_Z + 0.0010, -0.0060,
          HORNBEAM, r=0.0010)                                            # heel
    b.box(-0.0042, 0.0042, hy - 0.0080, hy + 0.0080, CAP_TOP - W_Z, CAP_TOP - W_Z + 0.0012,
          FELT_RED, r=0.0005)                                             # cushion
    b.box(-0.0045, 0.0045, py - 0.0030, py + 0.0030, 0.0080, pz - 0.0140, HORNBEAM,
          r=0.0010)                                                      # post
    for sx in (-1.0, 1.0):                            # post fork around the lever
        b.box(sx * 0.0028, sx * 0.0045, py - 0.0040, py + 0.0040, pz - 0.0160,
              pz + 0.0040, HORNBEAM, r=0.0008)
    b.cyl("x", (py, pz), 0.0007, -0.0047, 0.0047, STEEL, n=6)            # lever pin
    b.wire([(0.0, py - 0.0035, 0.0180), (0.0, py - 0.0150, 0.0340),
            (0.0, py - 0.0260, pz + 0.0015)], 0.0006, BRASS, n=5)       # rep spring
    b.wire([(0.0, jy + 0.0060, 0.0050), (0.0, jy + 0.0040, 0.0120)], 0.0005, BRASS, n=5)
    return b


def _jack_buf(top):
    """L-shaped jack: upright to the knuckle, tender forward to the button."""
    b = _Buf()
    outline = [
        (0.0015, -0.0040), (0.0015, top - 0.0012), (0.0003, top), (-0.0043, top),
        (-0.0055, top - 0.0012), (-0.0055, 0.0062), (-0.0100, 0.0057),
        (TENDER_CROWN[0], TENDER_CROWN[1]), (-0.0158, 0.0042), (-0.0162, 0.0010),
        (-0.0150, -0.0030), (-0.0060, -0.0040),
    ]
    b.profile_x(outline, -0.0033, 0.0033, HORNBEAM, r=0.0008)
    return b


def _lever_buf():
    """Repetition lever: forked window for the jack and the let-off screw,
    knuckle saddle, tip under the drop screw, regulating screw at the tail."""
    b = _Buf()
    k = _kinematics()
    tip = k["tip_dy"] - k["rep_dy"]                  # local y of the tip (< 0)
    sad = k["jack_dy"] - 0.002 - k["rep_dy"]         # saddle over the jack
    front = tip - 0.0035
    b.profile_x([(front, 0.0005), (front + 0.0080, 0.0005),
                 (front + 0.0080, 0.0085), (front, 0.0080)],
                -0.0060, 0.0060, HORNBEAM, r=0.0010)                  # tip bridge
    for sx in (-1.0, 1.0):
        b.profile_x([(front + 0.0070, 0.0005), (sad + 0.0080, 0.0005),
                     (sad + 0.0080, 0.0100), (sad, 0.0110),
                     (front + 0.0070, 0.0085)],
                    sx * 0.0038, sx * 0.0060, HORNBEAM, r=0.0008)     # cheeks
    b.profile_x([(sad + 0.0070, 0.0005), (sad + 0.0070, 0.0100), (-0.0200, 0.0085),
                 (0.0, 0.0055), (0.0120, 0.0045), (0.0140, 0.0010),
                 (0.0120, -0.0045), (-0.0040, -0.0045), (-0.0120, 0.0005)],
                -0.0026, 0.0026, HORNBEAM, r=0.0010)                  # tail
    b.cyl("z", (0.0, 0.0090), 0.0016, 0.0040, 0.0070, BRASS, n=8)     # reg. screw head
    return b


def _damper_lever_buf():
    """Damper underlever (pin at the rear): contact felt over the key end,
    wire block, sostenuto tab."""
    b = _Buf()
    front = -max(DC_ARM, DW_ARM) - 0.0060
    b.profile_x([(0.0070, -0.0055), (0.0070, 0.0050), (-0.0200, 0.0045),
                 (front, 0.0040), (front, -0.0040),
                 (-0.0200, -0.0040)], -0.0035, 0.0035, HORNBEAM, r=0.0012)
    b.box(-0.0035, 0.0035, -DC_ARM - 0.0060, -DC_ARM + 0.0060, -0.0075, -0.0040,
          FELT_RED, r=0.0006)
    b.box(-0.0038, 0.0038, -DW_ARM - 0.0045, -DW_ARM + 0.0045, 0.0040, 0.0120, MAPLE,
          r=0.0008)
    b.cyl("x", (-DW_ARM, 0.0085), 0.0012, -0.0048, 0.0048, BRASS, n=8)  # clamp screw
    b.box(-0.0030, 0.0030, -0.0565, -0.0535, 0.0040, 0.0110, MAPLE, r=0.0005)  # tab
    return b


def _damper_head_buf(kind, depth, width, height, spread, r_str):
    """Damper head on its felt (origin: felt bottom center on the string top).

    ``kind``: mono/bi/tri wedge felts that straddle the unison strings, or a
    flat treble felt. Local +Y runs along the strings.
    """
    b = _Buf()
    ft = 0.0065
    hw = width / 2.0
    felt = [(-hw, ft), (-hw, 0.0)]
    if kind == "mono":
        wedges = [(-(r_str + 0.0012), 0.0011, r_str), ((r_str + 0.0012), 0.0011, r_str)]
    elif kind == "bi":
        wedges = [(0.0, max(spread / 2.0 - r_str - 0.0001, 0.0003), r_str * 0.9)]
    elif kind == "tri":
        wedges = [(-spread / 2.0, 0.0013, r_str * 1.4), (spread / 2.0, 0.0013, r_str * 1.4)]
    else:
        wedges = []
    for xc, half, depth_w in sorted(wedges):
        felt += [(xc - half, 0.0), (xc, -depth_w), (xc + half, 0.0)]
    felt += [(hw, 0.0), (hw, ft)]
    b.profile_y(felt, -depth / 2.0, depth / 2.0, 1, r=0.0004)
    wood = [(-hw + 0.0002, ft - 0.0003), (hw - 0.0002, ft - 0.0003),
            (hw - 0.0002, ft + height - 0.004), (hw - 0.0030, ft + height),
            (-hw + 0.0030, ft + height), (-hw + 0.0002, ft + height - 0.004)]
    b.profile_y(wood, -depth / 2.0 + 0.0005, depth / 2.0 - 0.0005, 0,
                r=0.0015, c=0.0008, segs=2)
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
    for me in [m for m in bpy.data.meshes if m.users == 0 and m.name.startswith("ActionMesh.")]:
        bpy.data.meshes.remove(me)
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


_QEXPR = f"max(min(r*{Q:.4f},1),0)"
_QCLAMP = f"min(r*{Q:.4f},1)"


def _driver(obj, key, expr, with_hammer=False):
    var_specs = [("r", key, "rotation_euler[0]")]
    if with_hammer:
        var_specs.append(("h", key, '["hammer"]'))
    _drive(obj, "rotation_euler", 0, expr, var_specs)


def _parent_keep(child, parent, parent_world):
    """Parent with an inverse built from the intended transform (a fresh
    object's cached matrix_world is still identity)."""
    child.parent = parent
    child.matrix_parent_inverse = parent_world.inverted()


def _key_arm_buf(n, k):
    """Key stick behind the balance rail (the key hinge): starts flush with the
    visible key's rear face, cranks into its action lane, carries the capstan,
    the backcheck and (for damped notes) the damper lift block; ends over the
    back rail. World coords; built at rest."""
    b = _Buf()
    ax, s, hy, hz = n["ax"], n["s"], n["hinge_y"], n["hinge_z"]
    rx0, rx1 = n["rear_x"]
    w = n["lane_w"] - 0.0012
    lx0, lx1 = ax - w / 2.0, ax + w / 2.0
    y_end = s + (STICK_END_DY if n["damped"] else STICK_END_UNDAMPED)
    stations = [(hy + 0.0004, rx0, rx1), (CRANK_Y[0], rx0, rx1),
                (CRANK_Y[1], lx0, lx1), (y_end, lx0, lx1)]
    stations = [st for st in stations if st[0] >= hy + 0.0004 - 1e-9]
    stations.sort()
    zb, zt, ch = STICK_BOT, STICK_TOP, 0.0012
    ring_xz = lambda x0, x1: [(x0, zb), (x1, zb), (x1, zt - ch), (x1 - ch, zt),
                              (x0 + ch, zt), (x0, zt - ch)]
    rings = [[(x, y, z) for x, z in ring_xz(x0, x1)] for y, x0, x1 in stations]
    m = 6
    verts = [p for rg in rings for p in rg]
    faces = [tuple(range(m))]
    for i in range(len(rings) - 1):
        b0, b1 = i * m, (i + 1) * m
        faces += [(b0 + j, b0 + (j + 1) % m, b1 + (j + 1) % m, b1 + j) for j in range(m)]
    last = (len(rings) - 1) * m
    faces.append(tuple(last + j for j in range(m - 1, -1, -1)))
    b._emit(verts, faces, SPRUCE)

    # Capstan (brass, domed) under the wippen heel.
    cy = n["hc_y"] + k["cap_dy"]
    b.cyl("z", (ax, cy), 0.0040, zt - 0.0005, CAP_TOP - 0.0022, BRASS, n=10)
    b.tube((ax, cy, CAP_TOP - 0.0023), (ax, cy, CAP_TOP), 0.0040, BRASS, n=10, r1=0.0024)
    n["cap_y"] = cy

    # Backcheck: placed at full key press against the hammer tail at check,
    # then rotated back to the key's rest pose.
    tip_w, nrm_w = n["bc_contact"], n["bc_face"]         # world (y, z) at check
    psi_full = n["psi"]
    face_n = Vector((0.0, nrm_w[0], nrm_w[1]))           # from hammer into the check
    along = Vector((0.0, -face_n.z, face_n.y))           # face direction in YZ
    if along.z < 0:
        along = -along
    contact = Vector((ax, tip_w[0], tip_w[1]))
    lea_c = contact + face_n * 0.0008 - along * 0.0075
    wood_c = contact + face_n * (0.0016 + 0.0030) - along * 0.0075
    pivot = Matrix.Translation((0.0, hy, hz))
    back = pivot @ Matrix.Rotation(-psi_full, 4, "X") @ pivot.inverted()
    xa = Vector((1.0, 0.0, 0.0))
    fn_r = (back.to_3x3() @ face_n).normalized()
    al_r = (back.to_3x3() @ along).normalized()
    b.obox(back @ lea_c, xa, al_r, fn_r, 0.0045, 0.0100, 0.0008, LEATHER, r=0.0006)
    b.obox(back @ wood_c, xa, al_r, fn_r, 0.0042, 0.0100, 0.0030, MAPLE, r=0.0010)
    foot = back @ (wood_c - along * 0.0100)
    base = Vector((ax, foot.y - 0.004, zt - 0.0005))
    b.wire([tuple(base), tuple(foot)], 0.0011, BRASS, n=8)
    n["bc_rest"] = tuple(back @ contact)

    # Damper lift block under the underlever contact felt.
    if n["damped"]:
        y_c = s + DP_DY - DC_ARM
        top = DP_Z - 0.0075 - n["lift_gap"]
        b.box(ax - 0.0035, ax + 0.0035, y_c - 0.0060, y_c + 0.0060, zt - 0.0005,
              top - 0.0015, MAPLE, r=0.0008)
        b.box(ax - 0.0035, ax + 0.0035, y_c - 0.0055, y_c + 0.0055, top - 0.0015,
              top, FELT_RED, r=0.0005)
    return b


def _frame_buf(plan, k):
    """All static action parts in one mesh: tubular rails on five cast
    brackets, flanges + center pins, let-off rail + buttons, drop screws,
    hammer rest rail, and the key frame (balance rail, back rail + cloth)."""
    b = _Buf()
    a, slope = plan["line"]
    notes = plan["notes"]
    xL = min(n["rear_x"][0] for n in notes[:2]) - 0.0010
    xR = max(n["rear_x"][1] for n in notes[-2:]) + 0.0010

    def rail_box(x0, x1, dy0, dy1, z0, z1, mat, r=0.0010):
        """Box following the strike line (y offsets relative to it)."""
        def sy(x, dy):
            return a + slope * x + dy
        poly = [(dy0, z0), (dy1, z0), (dy1, z1), (dy0, z1)]
        pts = _round_poly(poly, r)
        rings = []
        for x in (x0, x1):
            rings.append([(x, sy(x, u), w) for u, w in pts])
        m = len(pts)
        verts = rings[0] + rings[1]
        faces = [tuple(range(m - 1, -1, -1)), tuple(m + i for i in range(m))]
        faces += [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
        b._emit(verts, faces, mat)

    def rail_tube(x0, x1, dy, z, r, mat):
        b.tube((x0, a + slope * x0 + dy, z), (x1, a + slope * x1 + dy, z), r, mat,
               n=16, c=0.0006)

    tube_dy = HC_DY - 0.018
    w_dy = HC_DY + k["w_dy"]
    rest_dy = HC_DY + 0.095
    # Tubular metallic action frame: hammer flange rail + wippen rail.
    rail_tube(xL, xR, tube_dy, 0.8290, 0.0095, BRASS)
    rail_tube(xL, xR, w_dy + 0.003, 0.7445, 0.0075, BRASS)
    # Let-off rail behind the flange rail; hammer rest rail with its felt.
    rail_box(xL, xR, HC_DY - 0.0040, HC_DY + 0.0075, 0.8195, 0.8248, MAPLE)
    rail_box(xL, xR, rest_dy - 0.007, rest_dy + 0.007, 0.7890, 0.8001, MAPLE)
    rail_box(xL, xR, rest_dy - 0.0065, rest_dy + 0.0065, 0.8001, 0.8016, FELT_RED,
             r=0.0005)
    # Key frame: balance rail under the hinges, back rail + cloth under the ends.
    kb0 = min(n["hinge_y"] for n in notes) - 0.0055
    b.box(xL, xR, kb0, -0.6995, KEYBED_Z, STICK_BOT - 0.0004, SPRUCE, r=0.0010)
    rail_box(xL, xR, STICK_END_UNDAMPED - 0.022, STICK_END_UNDAMPED + 0.001, KEYBED_Z,
             STICK_BOT - 0.0012, SPRUCE)
    rail_box(xL, xR, STICK_END_UNDAMPED - 0.021, STICK_END_UNDAMPED, STICK_BOT - 0.0012,
             STICK_BOT - 0.0002, FELT_GREEN, r=0.0004)
    for x0, x1 in ((xL - 0.0095, xL - 0.0005), (xR + 0.0005, xR + 0.0095)):   # cheeks
        y0 = -0.6995
        y1 = a + slope * (0.5 * (x0 + x1)) + STICK_END_UNDAMPED + 0.001
        b.box(x0, x1, y0, y1, KEYBED_Z, STICK_BOT - 0.004, SPRUCE, r=0.0012)

    # Per-note hardware.
    for n in notes:
        ax, hc = n["ax"], n["hc_y"]
        # Hammer flange on the tube: body, fork cheeks round the butt, pin, screw.
        b.box(ax - 0.0040, ax + 0.0040, hc - 0.0260, hc - 0.0070, 0.8370, 0.8435, MAPLE,
              r=0.0010)
        for sx in (-1.0, 1.0):
            b.profile_x([(hc - 0.0090, 0.8370), (hc + 0.0030, 0.8255),
                         (hc + 0.0070, 0.8290), (hc + 0.0060, 0.8400),
                         (hc - 0.0090, 0.8435)],
                        ax + sx * 0.0038, ax + sx * 0.0051, MAPLE, r=0.0010)
        b.cyl("x", (hc, HC_Z), 0.0007, ax - 0.0053, ax + 0.0053, STEEL, n=6)
        b.cyl("z", (ax, hc - 0.0215), 0.0023, 0.8435, 0.8452, BRASS, n=8)
        # Drop screw through flange and tube; punching just over the lever tip.
        tip_top = REP_Z + 0.0085
        ds = tip_top + k["d_tip"] * k["omega"] * n["letoff"]
        b.cyl("z", (ax, hc - 0.012), 0.0012, ds + 0.0012, 0.8435, STEEL, n=6)
        b.cyl("z", (ax, hc - 0.012), 0.0021, 0.8435, 0.8462, STEEL, n=8)
        b.cyl("z", (ax, hc - 0.012), 0.0026, ds, ds + 0.0014, FELT_RED, n=10)
        # Let-off button over the jack tender, screwed into the let-off rail.
        ty = hc + k["tender_dy"]
        tender_top = JACK_Z + TENDER_CROWN[1]
        btn = tender_top + k["d_tender"] * k["omega"] * n["letoff"]
        b.cyl("z", (ax, ty), 0.0013, btn + 0.004, 0.8200, STEEL, n=6)
        b.cyl("z", (ax, ty), 0.0040, btn + 0.0014, btn + 0.0050, MAPLE, n=10, c=0.0004)
        b.cyl("z", (ax, ty), 0.0038, btn, btn + 0.0015, FELT_RED, n=10)
        # Wippen flange on the wippen tube.
        wy = hc + k["w_dy"]
        for sx in (-1.0, 1.0):
            b.profile_x([(wy - 0.0060, 0.7505), (wy + 0.0110, 0.7505),
                         (wy + 0.0110, 0.7560), (wy + 0.0040, 0.7625),
                         (wy - 0.0050, 0.7620)],
                        ax + sx * 0.0043, ax + sx * 0.0057, MAPLE, r=0.0010)
        b.box(ax - 0.0057, ax + 0.0057, wy + 0.0030, wy + 0.0110, 0.7505, 0.7525,
              MAPLE, r=0.0006)
        b.cyl("x", (wy, W_Z), 0.0007, ax - 0.0059, ax + 0.0059, STEEL, n=6)

    # Cast action brackets: the two ends, the bass/treble break, and under
    # each treble strut (the lane gaps).
    xs = [xL - 0.0050]
    for left, right in zip(notes, notes[1:]):
        if right["ax"] - left["ax"] > 1.5 * plan["pitch"][1]:
            xs.append(0.5 * (left["ax"] + right["ax"]))
    xs.append(xR + 0.0050)
    for x in xs:
        hc = a + slope * x + HC_DY
        wy = hc + k["w_dy"]
        x0, x1 = x - 0.0025, x + 0.0025
        prof = [
            (hc - 0.032, KEYBED_Z), (hc - 0.010, KEYBED_Z), (hc - 0.010, 0.760),
            (hc + 0.020, 0.795), (rest_dy - HC_DY + hc - 0.007, 0.787),
            (rest_dy - HC_DY + hc + 0.007, 0.787), (rest_dy - HC_DY + hc + 0.007, 0.7995),
            (hc + 0.030, 0.8150), (hc + 0.010, 0.8265), (hc - 0.031, 0.8265),
            (hc - 0.032, 0.8150),
        ]
        b.profile_x(prof, x0, x1, IRON, r=0.0030, c=0.0006, segs=2)
        b.profile_x([(wy - 0.010, KEYBED_Z), (wy + 0.016, KEYBED_Z),
                     (wy + 0.016, 0.7380), (wy + 0.006, 0.7440), (wy - 0.006, 0.7440),
                     (wy - 0.010, 0.7380)], x0, x1, IRON, r=0.0025, c=0.0006, segs=2)
        p0, p1 = Vector((x, hc - 0.010, 0.765)), Vector((x, wy - 0.006, 0.739))
        d = (p1 - p0).normalized()
        b.obox((p0 + p1) / 2.0, d, (1.0, 0.0, 0.0), d.cross(Vector((1.0, 0.0, 0.0))),
               (p1 - p0).length / 2.0, 0.0025, 0.0035, IRON, r=0.0012)
        b.cyl("x", (a + slope * x + tube_dy, 0.8290), 0.0035, x0 - 0.0015, x1 + 0.0015,
              STEEL, n=10)                                               # tube bolt
    return b, xs


def _damper_frame_buf(plan, damped, xs):
    """Static damper action: underlever rail + flanges on posts, sostenuto rod,
    and the guide rail the wires rise through."""
    b = _Buf()
    a, slope = plan["line"]
    if not damped:
        return b
    x0 = damped[0]["ax"] - 0.0095
    x1 = damped[-1]["ax"] + 0.0095

    def sy(x, dy):
        return a + slope * x + dy

    def rail(dy0, dy1, z0, z1, mat, r=0.0010, xa=x0, xb=x1):
        pts = _round_poly([(dy0, z0), (dy1, z0), (dy1, z1), (dy0, z1)], r)
        m = len(pts)
        verts = [(xa, sy(xa, u), w) for u, w in pts] + [(xb, sy(xb, u), w) for u, w in pts]
        faces = [tuple(range(m - 1, -1, -1)), tuple(m + i for i in range(m))]
        faces += [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
        b._emit(verts, faces, mat)

    rail(DP_DY - 0.008, DP_DY + 0.012, 0.7350, 0.7455, MAPLE)
    rod_dy = DP_DY - 0.062
    b.tube((x0, sy(x0, rod_dy), 0.7645), (x1, sy(x1, rod_dy), 0.7645), 0.0040, MAPLE,
           n=12, c=0.0005)
    rail(rod_dy - 0.0012, rod_dy + 0.0012, 0.7680, 0.7700, FELT_RED, r=0.0004)
    rail(HEAD_DY - 0.008, HEAD_DY + 0.008, GUIDE_Z[0], GUIDE_Z[1], MAPLE, r=0.0015)
    for n in damped:
        ax, p = n["ax"], n["s"] + DP_DY
        for sx in (-1.0, 1.0):
            b.box(ax + sx * 0.0037, ax + sx * 0.0051, p - 0.0060, p + 0.0080,
                  0.7455, 0.7560, MAPLE, r=0.0008)
        b.cyl("x", (p, DP_Z), 0.0007, ax - 0.0053, ax + 0.0053, STEEL, n=6)
        b.cyl("z", n["wire_xy"], 0.0016, GUIDE_Z[0] - 0.0004,
              GUIDE_Z[1] + 0.0004, FELT_RED, n=8)                  # guide bushing
    for x in xs:
        if x < x0 - 0.02 or x > x1 + 0.02:
            continue
        xx = min(max(x, x0 + 0.004), x1 - 0.004)
        b.box(xx - 0.0025, xx + 0.0025, sy(xx, DP_DY - 0.006), sy(xx, DP_DY + 0.010),
              KEYBED_Z, 0.7350, IRON, r=0.0015)                     # lever rail post
        b.box(xx - 0.0025, xx + 0.0025, sy(xx, HEAD_DY - 0.006), sy(xx, HEAD_DY + 0.006),
              0.7700, GUIDE_Z[0], IRON, r=0.0015)                   # guide rail post
        b.box(xx - 0.0025, xx + 0.0025, sy(xx, rod_dy - 0.005), sy(xx, DP_DY + 0.004),
              0.7455, 0.7690, IRON, r=0.0015)                       # sostenuto bracket
    return b


def _key_rear_faces(keys):
    """x-extent of each visible key's rear face (the stick starts flush)."""
    out = {}
    for key in keys:
        mw = key.matrix_world
        vs = [mw @ v.co for v in key.data.vertices]
        ymax = max(v.y for v in vs)
        rear = [v for v in vs if v.y > ymax - 0.002]
        out[int(key["midi_note"])] = (min(v.x for v in rear) + 0.0003,
                                      max(v.x for v in rear) - 0.0003)
    return out


def _pedal_obj():
    for obj in bpy.data.objects:
        if obj.get("steinway_role") == "sustain_pedal":
            return obj
    return None


def _course_map():
    try:
        from . import strings as strings_mod
        return {c["note"]: c for c in strings_mod.course_lines()}
    except Exception:  # noqa: BLE001 - no stand-in strings to measure
        return {}


def _damper_kind(note, course):
    sec = course["sec"] if course else "tri"
    if sec in ("mono", "bi"):
        return sec
    return "tri" if note <= 71 else "flat"


BC_GAP = 0.0006          # backcheck leather -> hammer tail at check
BC_LEAN = math.radians(4.0)


def _solve_backcheck(n, molding):
    """Backcheck face for one note: the plane the hammer tail lands on at the
    check angle, set so the tail's whole rest -> check path stays in front of
    it (the backcheck must never be in the rising hammer's way)."""
    hc = n["hc_y"]

    def posed(phi):
        out = []
        for y, z in molding:
            ry, rz = _rot(phi, y, z)
            out.append(Vector((hc + ry, HC_Z + rz)))
        return out

    at_check, at_rest = posed(n["phi_c"]), posed(REST)
    i = max(range(len(at_check)), key=lambda j: at_check[j].x)   # rear-most point
    v = (at_check[i] - at_rest[i]).normalized()
    nf = Vector((-v.y, v.x))
    if nf.x > 0:
        nf = -nf                                    # face the hammer (toward -Y)
    nf = (nf * math.cos(BC_LEAN) - v * math.sin(BC_LEAN)).normalized()
    plane = min(nf.dot(p) for p in at_check) - BC_GAP
    contact = min(at_check, key=lambda p: nf.dot(p))
    contact = contact - nf * (nf.dot(contact) - plane)
    n["bc_contact"] = (contact.x, contact.y)
    n["bc_face"] = (-nf.x, -nf.y)
    n["bc_rest_margin"] = min(nf.dot(p) for p in at_rest) - plane


def _build(plan, coll, mats, k, bores):
    notes = plan["notes"]
    keys_rear = _key_rear_faces([n["key"] for n in notes])
    courses = _course_map()
    pedal = _pedal_obj()

    for n in notes:
        n["rear_x"] = keys_rear[n["note"]]
        n["cap_y"] = n["hc_y"] + k["cap_dy"]
        n["psi"] = k["cap_rise"] / (n["cap_y"] - n["hinge_y"])
        n["damped"] = n["note"] <= DAMPER_TOP and n["note"] in courses
        y_c = n["s"] + DP_DY - DC_ARM
        n["lift_a"] = n["psi"] * (y_c - n["hinge_y"])
        n["lift_gap"] = DLIFT_Q0 * n["lift_a"]

    # Shared meshes.
    wip_me = _wippen_buf(k).to_mesh("ActionMesh.Wippen", mats)
    jack_top = k["knuckle_z"] - JACK_Z - 0.0002
    jack_me = _jack_buf(jack_top).to_mesh("ActionMesh.Jack", mats)
    lever_me = _lever_buf().to_mesh("ActionMesh.RepLever", mats)
    dlever_me = _damper_lever_buf().to_mesh("ActionMesh.DamperLever", mats)
    ham_meshes, moldings = {}, {}
    for g in range(HAMMER_GROUPS):
        buf, molding = _hammer_buf(g, bores[g])
        ham_meshes[g] = buf.to_mesh(f"ActionMesh.Hammer.{g}", mats)
        moldings[g] = molding

    for n in notes:
        note, key, ax, hc = n["note"], n["key"], n["ax"], n["hc_y"]
        lo = n["letoff"]

        _solve_backcheck(n, moldings[n["group"]])
        n["molding"] = moldings[n["group"]]

        arm = _key_arm_buf(n, k).to_object(
            f"KeyArm.{note:03d}", (ax, n["hinge_y"], n["hinge_z"]), coll, mats)
        _tag(arm, "key_arm", note, psi=n["psi"])
        _driver(arm, key, f"{n['psi']:.5f}*{_QEXPR}")

        w_loc = Vector((ax, hc + k["w_dy"], W_Z))
        wip = bpy.data.objects.new(f"Wippen.{note:03d}", wip_me)
        wip.location = w_loc
        coll.objects.link(wip)
        _tag(wip, "wippen", note, omega=k["omega"])
        _driver(wip, key, f"-{k['omega']:.5f}*{_QEXPR}")
        w_world = Matrix.Translation(w_loc)

        jack = bpy.data.objects.new(f"Jack.{note:03d}", jack_me)
        jack.location = (ax, hc + k["jack_dy"], JACK_Z)
        coll.objects.link(jack)
        _parent_keep(jack, wip, w_world)
        _tag(jack, "jack", note, gain=k["jack_gain"], letoff=lo)
        _driver(jack, key, f"{k['jack_gain']:.4f}*max({_QCLAMP}-{lo:.4f},0)")

        lev = bpy.data.objects.new(f"RepLever.{note:03d}", lever_me)
        lev.location = (ax, hc + k["rep_dy"], REP_Z)
        coll.objects.link(lev)
        _parent_keep(lev, wip, w_world)
        _tag(lev, "rep_lever", note, gain=k["lever_gain"], letoff=lo)
        _driver(lev, key, f"{k['lever_gain']:.4f}*max({_QCLAMP}-{lo:.4f},0)")

        ham = bpy.data.objects.new(f"Hammer.{note:03d}", ham_meshes[n["group"]])
        ham.location = (ax, hc, HC_Z)
        ham.rotation_euler.x = REST
        coll.objects.link(ham)
        ramp = 1.0 / max(1.0 - lo, 0.05)
        _tag(ham, "hammer", note, rest=REST, slope=k["slope"], letoff=lo,
             drop=n["drop"], cap=n["cap"], impulse=HAM_IMPULSE, ramp=ramp,
             bore=n["bore"])
        expr = (
            f"{REST:.4f}+min({k['slope']:.4f}*min({_QEXPR},{lo:.4f})"
            f"-{n['drop']:.4f}*min(max({_QCLAMP}-{lo:.4f},0)*{ramp:.3f},1)"
            f"+{HAM_IMPULSE}*h,{n['cap']:.4f})"
        )
        _driver(ham, key, expr, with_hammer=True)

    frame, bracket_xs = _frame_buf(plan, k)
    fobj = frame.to_object("Action_Frame", (0.0, 0.0, 0.0), coll, mats)
    _tag(fobj, "frame", -1)

    dampers = _build_dampers(plan, coll, mats, courses, pedal, dlever_me, bracket_xs)
    return dampers


def _build_dampers(plan, coll, mats, courses, pedal, dlever_me, bracket_xs):
    """Per-note damper action (notes 21..DAMPER_TOP): felted head on its course,
    vertical wire (cranked toward the lane under the guide rail) down to the
    underlever, which the key end lifts from ~45 % travel and the sustain tray
    lifts for the pedal."""
    tops = bpy.data.objects.get("Dampers_Tops")
    bots = bpy.data.objects.get("Dampers_Bottoms")
    for obj in (tops, bots):
        if obj is not None:
            _hide_keep(obj)
            obj[REPLACED_PROP] = 1
    top_mat = (tops.data.materials[0] if tops and tops.data.materials else mats[MAHOGANY])
    felt_mat = (bots.data.materials[0] if bots and bots.data.materials else mats[FELT])
    dmats = [top_mat, felt_mat, mats[BRASS]]

    plate = _bvh(_PLATE)
    damped = [n for n in plan["notes"] if n["damped"]]
    head_meshes = {}
    built, blocked = 0, []

    var_ped = [("pd", pedal, "rotation_euler[0]")] if pedal is not None else []
    ped_q = f"max(min(pd*{PEDAL_Q:.4f},1),0)"
    kz = DW_ARM / DC_ARM

    for n in damped:
        note, key, ax = n["note"], n["key"], n["ax"]
        c = courses[note]
        F, R = c["F"], c["R"]
        y_h = n["s"] + HEAD_DY
        t = (y_h - F.y) / (R.y - F.y)
        cx = F.x + t * (R.x - F.x)
        hb = max((Fk.z + (Rk.z - Fk.z) * ((y_h - Fk.y) / (Rk.y - Fk.y)))
                 for Fk, Rk in c["unisons"]) + c["r"] + 0.0002
        d = R - F
        yaw = math.atan2(-d.x, d.y)
        kind = _damper_kind(note, c)
        spread = {"mono": 0.0, "bi": 0.0030, "tri": 0.0044}.get(c["sec"], 0.0044)
        if kind == "mono":
            off = c["r"] + 0.0021
        elif kind == "bi":
            off = spread / 2.0 + c["r"] + 0.0016
        else:
            off = spread / 2.0
        # Head size group: depth 45 -> 28 mm, height 16 -> 12 mm across the range.
        u = (note - 21) / (DAMPER_TOP - 21)
        bucket = int(u * 11.999)
        ub = (bucket + 0.5) / 12.0
        depth = round(0.045 - 0.017 * ub, 4)
        height = round(0.016 - 0.004 * ub, 4)
        width = min(n["lane_w"] - 0.0006, 0.0125)
        r_str = round(c["r"], 4)
        hkey = (kind, bucket, round(width, 4), r_str if kind != "flat" else 0.0)
        if hkey not in head_meshes:
            head_meshes[hkey] = _damper_head_buf(kind, depth, width, height, spread,
                                                 r_str).to_mesh(
                f"ActionMesh.DamperHead.{kind}.{bucket}", dmats)
        head = bpy.data.objects.new(f"Damper.{note:03d}", head_meshes[hkey])
        head.location = (cx, y_h, hb)
        head.rotation_euler.z = yaw
        coll.objects.link(head)

        # Wire: up between the unison strings into the head, vertical through
        # the guide rail, then cranked over to the lane's underlever. Take the
        # side of the course that clears the plate (struts flank a few notes).
        def wire_pts(side):
            wx = cx + side * off * math.cos(yaw)
            wy = y_h + side * off * math.sin(yaw)
            return [(wx, wy, hb + 0.0040), (wx, wy, GUIDE_Z[0] - 0.006),
                    (ax, y_h, 0.8050), (ax, y_h, DP_Z + 0.0120)]

        def touching(pts):
            if plate is None:
                return 0
            hits = 0
            for p0, p1 in zip(pts, pts[1:]):
                p0, p1 = Vector(p0), Vector(p1)
                for i in range(12):
                    loc = plate.find_nearest(p0.lerp(p1, i / 11.0), 0.0016)[0]
                    hits += loc is not None
            return hits

        pts = min((wire_pts(1.0), wire_pts(-1.0)), key=touching)
        wx, wy = pts[0][0], pts[0][1]
        wb = _Buf()
        wb.wire(pts, 0.0009, 2, n=6)
        wire = wb.to_object(f"DamperWire.{note:03d}", (0.0, 0.0, 0.0), coll, dmats)
        head_world = Matrix.LocRotScale(Vector((cx, y_h, hb)),
                                        mathutils.Euler((0.0, 0.0, yaw)), None)
        _parent_keep(wire, head, head_world)
        _tag(wire, "damper_wire", note)
        n["wire_xy"] = (wx, wy)
        hits = touching(pts)
        if hits:
            blocked.append((note, "wire", hits))
        if plate is not None:
            # Head footprint vs the plate (raised struts beside the course).
            foot = 0
            for fx in (-0.0062, 0.0, 0.0062):
                for fy in (-depth / 2.0, 0.0, depth / 2.0):
                    lx = fx * math.cos(yaw) - fy * math.sin(yaw)
                    ly = fx * math.sin(yaw) + fy * math.cos(yaw)
                    for fz in (0.002, 0.008, 0.016):
                        p = Vector((cx + lx, y_h + ly, hb + fz))
                        foot += plate.find_nearest(p, 0.0008)[0] is not None
            if foot:
                blocked.append((note, "head", foot))

        A, G = n["lift_a"], n["lift_gap"]
        key_term = f"max({A:.5f}*{_QCLAMP}-{G:.5f},0)"
        specs = [("r", key, "rotation_euler[0]")] + var_ped
        if pedal is not None:
            z_expr = f"{hb:.5f}+max({key_term}*{kz:.4f},{DPEDAL_LIFT}*{ped_q})"
            t_expr = (f"-max({key_term}*{1.0 / DC_ARM:.4f},"
                      f"{DPEDAL_LIFT / DW_ARM:.4f}*{ped_q})")
        else:
            z_expr = f"{hb:.5f}+{key_term}*{kz:.4f}"
            t_expr = f"-{key_term}*{1.0 / DC_ARM:.4f}"
        _tag(head, "damper_head", note, lift_a=A, lift_g=G, lift_k=kz,
             pedal_lift=DPEDAL_LIFT)
        _drive(head, "location", 2, z_expr, list(specs))

        lev = bpy.data.objects.new(f"DamperLever.{note:03d}", dlever_me)
        lev.location = (ax, n["s"] + DP_DY, DP_Z)
        coll.objects.link(lev)
        _tag(lev, "damper_lever", note, lift_a=A, lift_g=G, arm=DC_ARM,
             pedal_rot=DPEDAL_LIFT / DW_ARM)
        _drive(lev, "rotation_euler", 0, t_expr, list(specs))
        built += 1

    dframe = _damper_frame_buf(plan, damped, bracket_xs)
    if dframe.v:
        dobj = dframe.to_object("Damper_Frame", (0.0, 0.0, 0.0), coll, mats)
        _tag(dobj, "frame", -1)

    # Sustain tray under the underlevers.
    if damped:
        a, b = plan["line"]
        tb = _Buf()
        x0, x1 = damped[0]["ax"] - 0.0095, damped[-1]["ax"] + 0.0095
        ty = DP_DY - DT_ARM
        for z0, z1, mat in ((0.7380, 0.7455, MAPLE), (0.7455, 0.7460, FELT_RED)):
            pts = _round_poly([(ty - 0.008, z0), (ty + 0.008, z0), (ty + 0.008, z1),
                               (ty - 0.008, z1)], 0.0004 if mat == FELT_RED else 0.0012)
            m = len(pts)
            verts = ([(x0, a + b * x0 + u, w) for u, w in pts]
                     + [(x1, a + b * x1 + u, w) for u, w in pts])
            faces = [tuple(range(m - 1, -1, -1)), tuple(m + i for i in range(m))]
            faces += [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
            tb._emit(verts, faces, mat)
        tray = tb.to_object("Damper_Tray", (0.0, 0.0, 0.0), coll, mats)
        gain = DPEDAL_LIFT / DW_ARM * DT_ARM
        _tag(tray, "damper_tray", -1, gain=gain)
        if pedal is not None:
            _drive(tray, "location", 2, f"{gain:.5f}*{ped_q}", var_ped)
    if blocked:
        print(f"[action] dampers touching the plate: {blocked}")
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
def _verify(plan, k):
    deps = bpy.context.evaluated_depsgraph_get()
    picks = (21, 36, 49, 50, 60, 61, 84, 88, 108)
    sample = [n for n in plan["notes"] if n["note"] in picks]
    worst = {"heel": 0.0, "knuckle": 0.0, "strike": 0.0, "letoff": 0.0,
             "drop": 0.0, "check": 0.0}

    def world(name, local):
        ob = bpy.data.objects[name].evaluated_get(deps)
        return ob.matrix_world @ Vector(local)

    def pose(key, q, h):
        key.rotation_euler.x = q * PRESS_ANGLE
        key["hammer"] = h
        key.update_tag()
        deps.update()

    for n in sample:
        nn, key, ax = f"{n['note']:03d}", n["key"], n["ax"]
        hinge = Vector((ax, n["hinge_y"], n["hinge_z"]))
        cap_local = Vector((0.0, n["cap_y"] - n["hinge_y"], CAP_TOP - n["hinge_z"]))
        heel_local = (0.0, -HEEL_W_ARM, CAP_TOP - W_Z)
        jt = k["knuckle_z"] - JACK_Z - 0.0002
        for q in (0.0, 0.5 * n["letoff"], 0.95 * n["letoff"], 1.0):
            pose(key, q, 0.0)
            cap = world(f"KeyArm.{nn}", cap_local)
            heel = world(f"Wippen.{nn}", heel_local)
            worst["heel"] = max(worst["heel"], abs(heel.z - cap.z))
            if q < n["letoff"]:
                top = world(f"Jack.{nn}", (0.0, -0.002, jt))
                kc = world(f"Hammer.{nn}", (0.0, LK, KNUCKLE_DZ))
                worst["knuckle"] = max(worst["knuckle"],
                                       abs((top - kc).length - KNUCKLE_R))
        # Let-off: tender reaches the button, lever tip reaches the drop screw.
        pose(key, n["letoff"], 0.0)
        tender = world(f"Jack.{nn}", (0.0, *TENDER_CROWN))
        btn = JACK_Z + TENDER_CROWN[1] + k["d_tender"] * k["omega"] * n["letoff"]
        worst["letoff"] = max(worst["letoff"], abs(tender.z - btn))
        tipw = world(f"RepLever.{nn}", (0.0, k["tip_dy"] - k["rep_dy"], 0.0085))
        ds = REP_Z + 0.0085 + k["d_tip"] * k["omega"] * n["letoff"]
        worst["drop"] = max(worst["drop"], abs(tipw.z - ds))
        # Strike: the live channel throws the crown to the string.
        pose(key, 0.6, 1.0)
        crown = world(f"Hammer.{nn}", (0.0, LH, n["bore"]))
        worst["strike"] = max(worst["strike"], abs(crown.z - n["strike_z"]))
        # Check: key held, hammer falls onto the backcheck.
        pose(key, 1.0, 0.0)
        # bc_rest is the leather contact at rest; ride it on the arm's rotation.
        rot = Matrix.Translation(hinge) @ Matrix.Rotation(
            n["psi"], 4, "X") @ Matrix.Translation(-hinge)
        bc = rot @ Vector(n["bc_rest"])
        face = Vector((0.0, *n["bc_face"]))
        gap = min(face.dot(bc - world(f"Hammer.{nn}", (0.0, y, z)))
                  for y, z in n["molding"])
        worst["check"] = max(worst["check"], abs(gap - BC_GAP))
        pose(key, 0.0, 0.0)

    # Damper action: a pressed key lifts its damper; the pedal lifts them all.
    damper = {"key": None, "pedal": None}
    probe = bpy.data.objects.get("Damper.060")
    pedal = _pedal_obj()
    if probe is not None:
        key = next(n["key"] for n in plan["notes"] if n["note"] == 60)
        rest = probe.evaluated_get(deps).location.z
        pose(key, 1.0, 0.0)
        damper["key"] = probe.evaluated_get(deps).location.z - rest
        pose(key, 0.0, 0.0)
        if pedal is not None:
            pedal.rotation_euler.x = math.radians(5.0)
            pedal.update_tag()
            deps.update()
            damper["pedal"] = probe.evaluated_get(deps).location.z - rest
            pedal.rotation_euler.x = 0.0
            pedal.update_tag()
            deps.update()
    return worst, damper


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
    belly = _open_belly_rail()
    seated = _seat_bridge_on_soundboard()
    k, bores, flagged = _solve(plan)
    coll = _fresh_collection()
    mats = _materials()
    dampers = _build(plan, coll, mats, k, bores)
    _tag_targets(plan)
    worst, damper = _verify(plan, k)
    szs = [n["strike_z"] for n in plan["notes"]]
    a, b = plan["line"]
    return {
        "notes": len(plan["notes"]),
        "objects": len(coll.objects),
        "meshes": len({o.data.name for o in coll.objects if o.data is not None}),
        "soundboard": cut,
        "belly_rail": belly,
        "bridge_seat": seated,
        "action_line": (round(a, 4), round(b, 4)),
        "pitch_mm": tuple(round(p * 1000, 2) for p in plan["pitch"]),
        "strike_z": (round(min(szs), 4), round(max(szs), 4)),
        "bores_mm": {g: round(v * 1000, 1) for g, v in bores.items()},
        "cap_rise_mm": round(k["cap_rise"] * 1000, 2),
        "dampers": dampers,
        "low_clearance_notes": flagged,
        "errors_mm": {kk: round(v * 1000, 2) for kk, v in worst.items()},
        "damper_lift_mm": {kk: (round(v * 1000, 2) if v is not None else None)
                           for kk, v in damper.items()},
        # Back-compat keys used by scripts/build_all.py / build_action.py.
        "heel_err": worst["heel"],
        "strike_err": worst["strike"],
        "damper_err": (abs(damper["pedal"] - DPEDAL_LIFT)
                       if damper["pedal"] is not None else 0.0)
        + (1.0 if (damper["key"] or 0.0) < 0.002 else 0.0),
    }
