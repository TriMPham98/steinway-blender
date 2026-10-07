"""Build a procedural Carnegie Hall (Isaac Stern Auditorium) around the Steinway.

    B=/Applications/Blender.app/Contents/MacOS/Blender
    $B --background assets/steinway_grand_playable.blend --python scripts/build_carnegie_hall.py
    $B --background --factory-startup --python scripts/build_carnegie_hall.py -- --no-blend

Everything is generated from code (bmesh) — no source .blend or downloads:

* the stage under the arched, gilded proscenium with its vaulted shell,
* the raked parquet with curved rows of red seats,
* the horseshoe of First Tier and Second Tier boxes, the Dress Circle and the
  steep Balcony, each with a cream-and-gold parapet and under-tier lamps,
* the ceiling with the oval dome and its rings of bulbs,
* the trim that makes it read as the real room: coffered arch reveal, gilt
  panel frames on every tier front, red damask in the boxes, ribbed ceiling
  and dome, arched wall panels, doors with exit signs, aisle runners.

Lighting is baked with Cycles into vertex colours (stage wash, front-of-house
key, dome and under-tier lamps, bounce light and occlusion), so the viewer
draws the hall unlit at almost no cost.

The hall is laid out in the piano's own frame: stage top at Z=0 under the feet,
keyboard (-Y) toward stage right, so the curved side and the open lid face the
house (+X), as a recital grand stands. The piano is never moved, so the live
MIDI drivers keep working.

Outputs:

* ``assets/steinway_carnegie_hall.blend`` — the playable piano on the stage, with
  stage lights and a house camera (skip with ``--no-blend``).
* ``web/public/models/carnegie_hall.glb`` — the hall alone, in the same world
  coordinates as ``steinway.glb``, so the viewer applies the piano's framing
  offset and the two line up. Vertex colour ``Hall_Light`` is the baked
  lighting times a per-face tone (plank tones); Blender renders ignore it.
"""

from __future__ import annotations

import math
import os
import random
import sys
import time

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

COLLECTION = "Carnegie_Hall"
LIGHT_ATTR = "Hall_Light"  # exported: baked light x tone
TONE_ATTR = "Hall_Tone"  # per-face albedo variation (plank tones)
BAKE_ATTR = "Hall_Bake"
BAKE_SAMPLES = 384
BAKE_SMOOTH = 2  # neighbour-averaging passes over the per-vertex bake
# Large faces are split so the per-vertex bake has enough samples to resolve
# light pools and contact shadows.
MAX_EDGE = 1.0

# --- Plan (metres; X = toward the house, Y = across, Z = up) ---------------
STAGE_TOP = -0.003  # a hair under the piano's feet so casters don't z-fight
PARQUET_Z = -1.15  # house floor at the stage lip
STAGE_BACK_X = -10.0
STAGE_FRONT_X = 3.6  # apron centre; the lip curves back toward the sides
APRON_SAG = 1.2
PROSC_X = 2.0  # proscenium wall plane
REVEAL = 1.0  # depth of the arch reveal behind the proscenium
ARCH_HALF_W = 9.0
ARCH_SPRING = 10.5
ARCH_RISE = 4.5
SHELL_TAPER_Y = 0.82  # the stage shell narrows and lowers toward the back
SHELL_TAPER_Z = 0.9

HALL_HALF_W = 13.5
HALL_BACK_X = 33.6
HALL_CORNER_R = 9.0  # rounded back corners: the tiers sweep round in a horseshoe
CEILING_Z = 22.5
PARQUET_RAKE = 1.4  # rise of the house floor from stage lip to back wall

DOME_CX = (PROSC_X + HALL_BACK_X) * 0.5
DOME_A = 9.5
DOME_B = 8.0
DOME_H = 2.8

# name, floor Z, first X along the side walls, depth, seat rows, boxes, step per row
TIERS = (
    ("First_Tier", 3.4, PROSC_X + 0.3, 3.6, 2, True, 0.0),
    ("Second_Tier", 7.0, PROSC_X + 0.3, 3.6, 2, True, 0.0),
    ("Dress_Circle", 10.8, 8.0, 4.6, 4, False, 0.28),
    ("Balcony", 14.6, 12.0, 7.5, 8, False, 0.36),
)
ROW_PITCH = 0.9
SEAT_PITCH = 0.56

MATERIALS = {
    # name: (base colour (linear), metallic, roughness, emission strength)
    "Hall_Plaster": ((0.78, 0.69, 0.53), 0.0, 0.75, 0.0),
    "Hall_Gold": ((0.86, 0.64, 0.27), 1.0, 0.32, 0.0),
    "Hall_Velvet": ((0.22, 0.018, 0.022), 0.0, 0.9, 0.0),
    "Hall_Carpet": ((0.20, 0.03, 0.035), 0.0, 0.95, 0.0),
    "Hall_Stage_Wood": ((0.36, 0.20, 0.09), 0.0, 0.42, 0.0),
    "Hall_Dark_Wood": ((0.09, 0.045, 0.025), 0.0, 0.5, 0.0),
    "Hall_Fabric": ((0.25, 0.03, 0.035), 0.0, 0.85, 0.0),
    "Hall_Bulb": ((1.0, 0.86, 0.62), 0.0, 0.4, 6.0),
    "Hall_Exit": ((1.0, 0.08, 0.04), 0.0, 0.4, 4.0),
}
UNBAKED = {"Hall_Bulb", "Hall_Exit"}  # self-lit: exported at full brightness


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _argv_after_double_dash():
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


class Kit:
    """One bmesh per material; every face corner carries a Hall_Tone value."""

    def __init__(self):
        self.meshes = {}
        self._solid = None  # centre of the closed solid being built (box/bulb)

    def _bm(self, mat):
        if mat not in self.meshes:
            bm = bmesh.new()
            bm.loops.layers.float_color.new(TONE_ATTR)
            bm.faces.layers.int.new("solid")
            self.meshes[mat] = bm
        return self.meshes[mat]

    def face(self, mat, pts, tone=1.0, smooth=False):
        """Add a face; quads longer than MAX_EDGE become a grid of quads."""
        if len(pts) == 4:
            a, b, c, d = (Vector(p) for p in pts)
            nu = min(48, math.ceil(max((b - a).length, (c - d).length) / MAX_EDGE))
            nv = min(48, math.ceil(max((d - a).length, (c - b).length) / MAX_EDGE))
            if nu * nv > 1:
                return self._grid(mat, a, b, c, d, nu, nv, tone, smooth)
        bm = self._bm(mat)
        verts = [bm.verts.new(p) for p in pts]
        try:
            f = bm.faces.new(verts)
        except ValueError:
            for v in verts:
                bm.verts.remove(v)
            return None
        self._finish(bm, f, tone, smooth)
        return f

    def _grid(self, mat, a, b, c, d, nu, nv, tone, smooth):
        bm = self._bm(mat)
        grid = [
            [bm.verts.new((a.lerp(b, i / nu)).lerp(d.lerp(c, i / nu), j / nv)) for j in range(nv + 1)]
            for i in range(nu + 1)
        ]
        for i in range(nu):
            for j in range(nv):
                quad = (grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1])
                try:
                    f = bm.faces.new(quad)
                except ValueError:
                    continue
                self._finish(bm, f, tone, smooth)

    def _finish(self, bm, f, tone, smooth):
        f.smooth = smooth
        if self._solid is not None:
            # Faces of a closed solid point away from its centre.
            f.normal_update()
            if f.normal.dot(f.calc_center_median() - self._solid) < 0:
                f.normal_flip()
            f[bm.faces.layers.int["solid"]] = 1
        layer = bm.loops.layers.float_color[TONE_ATTR]
        for loop in f.loops:
            loop[layer] = (tone, tone, tone, 1.0)

    def strip(self, mat, a, b, tone=1.0, smooth=False, closed=False):
        """Quads bridging two equal-length polylines."""
        n = len(a)
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            self.face(mat, (a[i], a[j], b[j], b[i]), tone, smooth)

    def box(self, mat, center, fwd, size, tone=1.0, bottom=False):
        """Oriented box: ``fwd`` is the local +X in the XY plane, size = (x, y, z)."""
        fwd = Vector((fwd.x, fwd.y, 0)).normalized()
        side = Vector((-fwd.y, fwd.x, 0))
        up = Vector((0, 0, 1))
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2

        def c(sx, sy, sz):
            return center + fwd * (sx * hx) + side * (sy * hy) + up * (sz * hz)

        faces = [
            ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)),
            ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)),
            ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)),
            ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)),
            ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)),
        ]
        if bottom:
            faces.append(((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)))
        self._solid = center
        for quad in faces:
            self.face(mat, [c(*q) for q in quad], tone)
        self._solid = None

    def bulb(self, center, r=0.07):
        """Low-poly octahedron lamp."""
        axes = [Vector((r, 0, 0)), Vector((0, r, 0)), Vector((-r, 0, 0)), Vector((0, -r, 0))]
        top = center + Vector((0, 0, r))
        bot = center - Vector((0, 0, r))
        for i in range(4):
            a, b = center + axes[i], center + axes[(i + 1) % 4]
            self._solid = center
            self.face("Hall_Bulb", (a, b, top))
            self.face("Hall_Bulb", (b, a, bot))
            self._solid = None


# --- 2D helpers -------------------------------------------------------------


def ray_hit(poly, center, theta):
    """Distance from ``center`` along angle ``theta`` to a star-shaped polygon."""
    d = (math.cos(theta), math.sin(theta))
    best = None
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i][0] - center[0], poly[i][1] - center[1]
        bx, by = poly[(i + 1) % n][0] - center[0], poly[(i + 1) % n][1] - center[1]
        ex, ey = bx - ax, by - ay
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            continue
        t = (ax * ey - ay * ex) / den
        u = (ax * d[1] - ay * d[0]) / den
        if t > 1e-9 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return best


def ring(inner, outer, center):
    """Matched point loops between two star-shaped polygons (an annulus).

    Samples both outlines on the union of their vertex angles, so each
    straight edge and corner of either polygon is reproduced exactly.
    """
    angles = set()
    for poly in (inner, outer):
        for x, y in poly:
            angles.add(math.atan2(y - center[1], x - center[0]) % math.tau)
    angles = sorted(angles)
    a, b = [], []
    for th in angles:
        ri, ro = ray_hit(inner, center, th), ray_hit(outer, center, th)
        c, s = math.cos(th), math.sin(th)
        a.append((center[0] + c * ri, center[1] + s * ri))
        b.append((center[0] + c * ro, center[1] + s * ro))
    return a, b


def ellipse(cx, cy, a, b, n, scale=1.0):
    return [
        (cx + a * scale * math.cos(math.tau * i / n), cy + b * scale * math.sin(math.tau * i / n))
        for i in range(n)
    ]


def arch_outline(half_w, spring, rise, n_arc=32, closed=True, bottom=0.0):
    """Proscenium opening in (Y, Z): straight jambs, semi-elliptic head.

    ``closed`` outlines run along the stage at ``bottom`` back to the start;
    open ones are just the jambs and head (a sweep profile).
    """
    pts = [(-half_w, bottom)] if closed else [(-half_w, STAGE_TOP)]
    pts.append((-half_w, spring))
    for i in range(1, n_arc):
        t = math.pi - math.pi * i / n_arc
        pts.append((half_w * math.cos(t), spring + rise * math.sin(t)))
    pts.append((half_w, spring))
    pts.append((half_w, bottom) if closed else (half_w, STAGE_TOP))
    return pts


def resample(pts, step):
    """Points every ``step`` metres along a polyline, plus local tangents."""
    out = []
    carry = step * 0.5
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = (b - a).length
        if seg < 1e-9:
            continue
        tangent = (b - a) / seg
        s = carry
        while s <= seg:
            out.append((a + (b - a) * (s / seg), tangent))
            s += step
        carry = s - seg
    return out


def horseshoe(inset, x_start, z=0.0, side_step=1.0, corner_segs=10):
    """Wall plan (inset 0) or a tier rail (inset = depth), with outward normals.

    Runs up the -Y side wall from ``x_start``, round the back corner, across
    the back wall and down the +Y side. Every inset shares the corner centres,
    so loops of different insets have matching samples and bridge cleanly.
    """
    r = HALL_CORNER_R - inset
    hw = HALL_HALF_W - inset
    cx = HALL_BACK_X - HALL_CORNER_R
    cy = HALL_HALF_W - HALL_CORNER_R
    pts, normals = [], []
    n_side = max(1, math.ceil((cx - x_start) / side_step))
    for i in range(n_side):
        x = x_start + (cx - x_start) * i / n_side
        pts.append(Vector((x, -hw, z)))
        normals.append(Vector((0, -1, 0)))
    for i in range(corner_segs + 1):
        t = -math.pi / 2 + (math.pi / 2) * i / corner_segs
        n = Vector((math.cos(t), math.sin(t), 0))
        pts.append(Vector((cx, -cy, z)) + n * r)
        normals.append(n)
    n_back = max(1, math.ceil(2 * cy / side_step))
    for i in range(1, n_back):
        pts.append(Vector((cx + r, -cy + 2 * cy * i / n_back, z)))
        normals.append(Vector((1, 0, 0)))
    for i in range(corner_segs + 1):
        t = (math.pi / 2) * i / corner_segs
        n = Vector((math.cos(t), math.sin(t), 0))
        pts.append(Vector((cx, cy, z)) + n * r)
        normals.append(n)
    for i in range(1, n_side + 1):
        x = cx - (cx - x_start) * i / n_side
        pts.append(Vector((x, hw, z)))
        normals.append(Vector((0, 1, 0)))
    return pts, normals


def at_z(pts, z):
    return [Vector((p.x, p.y, z)) for p in pts]


def wall_half_width(x):
    """Half-width of the hall plan at depth ``x``."""
    cx = HALL_BACK_X - HALL_CORNER_R
    if x <= cx:
        return HALL_HALF_W
    dx = min(x - cx, HALL_CORNER_R)
    return HALL_HALF_W - HALL_CORNER_R + math.sqrt(HALL_CORNER_R**2 - dx**2)


def parquet_z(x):
    return PARQUET_Z + PARQUET_RAKE * smoothstep(PROSC_X, HALL_BACK_X, x)


def on_straight(p, margin):
    """True where a horseshoe point is on a straight run, ``margin`` clear of a corner."""
    return (p.x < HALL_BACK_X - HALL_CORNER_R - margin
            or abs(p.y) < HALL_HALF_W - HALL_CORNER_R - margin)


def add_frame(kit, p, t, z0, z1, w, bar=0.05, mat="Hall_Gold"):
    """Rectangular moulding frame on a vertical face through ``p`` along ``t``."""
    h = w / 2

    def q(u, v):
        return Vector((p.x + t.x * u, p.y + t.y * u, v))

    for u0, u1, v0, v1 in ((-h, h, z0, z0 + bar), (-h, h, z1 - bar, z1),
                           (-h, -h + bar, z0 + bar, z1 - bar), (h - bar, h, z0 + bar, z1 - bar)):
        kit.face(mat, [q(u0, v0), q(u1, v0), q(u1, v1), q(u0, v1)])


def arch_fill(kit, mat, half_w, bottom, spring, rise, to3d, cols=16, tone=1.0):
    """Solid arch-headed panel as vertical columns (subdivided for the bake)."""

    def top(u):
        return spring + rise * math.sqrt(max(0.0, 1 - (u / half_w) ** 2))

    for i in range(cols):
        u0 = -half_w + 2 * half_w * i / cols
        u1 = -half_w + 2 * half_w * (i + 1) / cols
        kit.face(mat, [to3d(u0, bottom), to3d(u1, bottom), to3d(u1, top(u1)), to3d(u0, top(u0))], tone)


def arch_frame(kit, half_w, bottom, spring, rise, w, to3d, mat="Hall_Gold"):
    """Gilt moulding round an arch-headed opening (both outlines closed below)."""
    inner = arch_outline(half_w, spring, rise, bottom=bottom)
    outer = arch_outline(half_w + w, spring, rise + w, bottom=bottom - w)
    center = (0.0, (bottom + spring) / 2)
    a, b = ring(inner, outer, center)
    kit.strip(mat, [to3d(*p) for p in a], [to3d(*p) for p in b], closed=True)


def add_door(kit, a, b, floor, height=2.1, exit_sign=False):
    """Dark wood door from ``a`` to ``b`` (both on the face) with a gilt frame."""
    t = (b - a).normalized()
    mid = (a + b) / 2
    w = (b - a).length
    kit.face("Hall_Dark_Wood", [Vector((a.x, a.y, floor)), Vector((b.x, b.y, floor)),
                                Vector((b.x, b.y, floor + height)), Vector((a.x, a.y, floor + height))])
    n = Vector((-t.y, t.x, 0))  # off the face, toward the viewer
    add_frame(kit, mid + n * 0.01, t, floor, floor + height + 0.12, w + 0.24, 0.1)
    if exit_sign:
        kit.box("Hall_Exit", mid + n * 0.06 + Vector((0, 0, floor + height + 0.3)),
                n, (0.1, 0.62, 0.22))


def add_seat(kit, base, facing, tone=1.0):
    """A theatre seat: cushion box + upholstered back, gilt-free and low-poly."""
    f = Vector((facing.x, facing.y, 0)).normalized()
    kit.box("Hall_Velvet", base + f * 0.05 + Vector((0, 0, 0.42)), f, (0.44, 0.5, 0.1), tone)
    kit.box("Hall_Velvet", base - f * 0.22 + Vector((0, 0, 0.5)), f, (0.09, 0.52, 1.0), tone)


# --- Building blocks --------------------------------------------------------


def build_stage(kit):
    rnd = random.Random(1891)  # Carnegie Hall opened in 1891

    def stage_half_w(x):
        if x >= PROSC_X - REVEAL:
            return ARCH_HALF_W
        t = (PROSC_X - REVEAL - x) / (PROSC_X - REVEAL - STAGE_BACK_X)
        return ARCH_HALF_W * (1 - t * (1 - SHELL_TAPER_Y))

    def apron_x(y):
        return STAGE_FRONT_X - APRON_SAG * (y / ARCH_HALF_W) ** 2

    def shell_x(y):
        """Most upstage X still inside the tapering shell at half-width |y|."""
        p = PROSC_X - REVEAL
        t = (1 - abs(y) / ARCH_HALF_W) / (1 - SHELL_TAPER_Y)
        return max(STAGE_BACK_X, p - (p - STAGE_BACK_X) * t)

    # Planks run up- and downstage, staggered, each with its own tone. Their
    # ends are cut along the shell walls and the curved lip.
    plank_w, plank_l = 0.18, 2.4
    n_planks = int(2 * ARCH_HALF_W / plank_w)
    for i in range(n_planks):
        y0 = -ARCH_HALF_W + i * plank_w
        y1 = y0 + plank_w
        x = STAGE_BACK_X - plank_l * rnd.random()
        while x < STAGE_FRONT_X:
            x1 = x + plank_l
            xa0, xa1 = max(x, shell_x(y0)), max(x, shell_x(y1))
            xb0, xb1 = min(x1, apron_x(y0)), min(x1, apron_x(y1))
            if xb0 - xa0 > 0.02 and xb1 - xa1 > 0.02:
                k = 0.82 + 0.3 * rnd.random()
                kit.face(
                    "Hall_Stage_Wood",
                    [Vector((xa0, y0, STAGE_TOP)), Vector((xb0, y0, STAGE_TOP)),
                     Vector((xb1, y1, STAGE_TOP)), Vector((xa1, y1, STAGE_TOP))],
                    k,
                )
            x = x1

    # Sub-floor under the planks fills the ragged ends at the walls and lip.
    outline = []
    for i in range(25):
        y = -ARCH_HALF_W + 2 * ARCH_HALF_W * i / 24
        outline.append(Vector((apron_x(y) + 0.002, y, STAGE_TOP - 0.006)))
    outline += [
        Vector((PROSC_X - REVEAL, ARCH_HALF_W, STAGE_TOP - 0.006)),
        Vector((STAGE_BACK_X, ARCH_HALF_W * SHELL_TAPER_Y, STAGE_TOP - 0.006)),
        Vector((STAGE_BACK_X, -ARCH_HALF_W * SHELL_TAPER_Y, STAGE_TOP - 0.006)),
        Vector((PROSC_X - REVEAL, -ARCH_HALF_W, STAGE_TOP - 0.006)),
    ]
    kit.face("Hall_Dark_Wood", outline)

    # Stage front: the dark curved lip down to the parquet.
    lip_top = [Vector((apron_x(y), y, STAGE_TOP)) for y in
               (-ARCH_HALF_W + 2 * ARCH_HALF_W * i / 32 for i in range(33))]
    lip_bot = [Vector((p.x, p.y, PARQUET_Z - 0.05)) for p in lip_top]
    kit.strip("Hall_Dark_Wood", lip_bot, lip_top, smooth=True)
    # A gold nosing along the lip edge.
    nose_a = [p + Vector((0.02, 0, -0.01)) for p in lip_top]
    nose_b = [p + Vector((0.02, 0, -0.07)) for p in lip_top]
    kit.strip("Hall_Gold", nose_b, nose_a, smooth=True)
    for sign in (-1, 1):
        y = sign * ARCH_HALF_W
        kit.face("Hall_Dark_Wood", [
            Vector((PROSC_X, y, PARQUET_Z - 0.05)), Vector((apron_x(y), y, PARQUET_Z - 0.05)),
            Vector((apron_x(y), y, STAGE_TOP)), Vector((PROSC_X, y, STAGE_TOP)),
        ])


def build_back_wall(kit, back):
    """Stage back wall: columns under the shell's own back profile points, so
    its top edge meets the vault exactly (coarser chords leave slivers)."""
    for p, q in zip(back, back[1:]):
        if abs(q.y - p.y) < 1e-6:
            continue  # a vertical jamb segment
        kit.face("Hall_Plaster", [Vector((STAGE_BACK_X, p.y, STAGE_TOP)), Vector((STAGE_BACK_X, q.y, STAGE_TOP)),
                                  q.copy(), p.copy()])


def build_proscenium_and_shell(kit):
    opening = arch_outline(ARCH_HALF_W, ARCH_SPRING, ARCH_RISE)
    frame = [(-HALL_HALF_W, PARQUET_Z - 0.05), (HALL_HALF_W, PARQUET_Z - 0.05),
             (HALL_HALF_W, CEILING_Z), (-HALL_HALF_W, CEILING_Z)]
    center = (0.0, 6.0)

    def yz(pts, x):
        return [Vector((x, y, z)) for y, z in pts]

    a, b = ring(opening, frame, center)
    kit.strip("Hall_Plaster", yz(a, PROSC_X), yz(b, PROSC_X), closed=True)

    # Gilded architrave round the arch, proud of the wall.
    # Its foot runs on down to the parquet beside the stage.
    gilt = arch_outline(ARCH_HALF_W + 0.7, ARCH_SPRING, ARCH_RISE + 0.7, bottom=PARQUET_Z)
    a, b = ring(opening, gilt, center)
    kit.strip("Hall_Gold", yz(a, PROSC_X + 0.04), yz(b, PROSC_X + 0.04), closed=True)
    # A cartouche at the crown.
    kit.box("Hall_Gold", Vector((PROSC_X + 0.12, 0, ARCH_SPRING + ARCH_RISE + 1.3)),
            Vector((1, 0, 0)), (0.2, 2.4, 1.6))

    # Reveal, then the vaulted shell narrowing to the back wall.
    profile = arch_outline(ARCH_HALF_W, ARCH_SPRING, ARCH_RISE, closed=False)
    front = yz(profile, PROSC_X)
    reveal = yz(profile, PROSC_X - REVEAL)
    kit.strip("Hall_Plaster", front, reveal, smooth=True)
    back = [Vector((STAGE_BACK_X, y * SHELL_TAPER_Y, z * SHELL_TAPER_Z)) for y, z in profile]
    loops = [reveal]
    for i in range(1, 9):
        t = i / 8
        loops.append([r.lerp(bk, t) for r, bk in zip(reveal, back)])
    for la, lb in zip(loops, loops[1:]):
        kit.strip("Hall_Plaster", la, lb, smooth=True)
    build_back_wall(kit, back)

    # Back wall: nested gilt arches framing an inset panel.
    bc = (0.0, 5.0)
    for s, w in ((0.62, 0.18), (0.42, 0.12)):
        inner = arch_outline(ARCH_HALF_W * s, ARCH_SPRING * s, ARCH_RISE * s)
        outer = arch_outline(ARCH_HALF_W * s + w, ARCH_SPRING * s, ARCH_RISE * s + w, bottom=-0.5)
        a, b = ring(inner, outer, bc)
        kit.strip("Hall_Gold", yz(a, STAGE_BACK_X + 0.03), yz(b, STAGE_BACK_X + 0.03), closed=True)

    # Pilasters with gilt capitals along the shell walls, and a cornice at the spring.
    for i in range(5):
        x = PROSC_X - REVEAL - 1.6 - i * 2.3
        t = (PROSC_X - REVEAL - x) / (PROSC_X - REVEAL - STAGE_BACK_X)
        hw = ARCH_HALF_W * (1 - t * (1 - SHELL_TAPER_Y))
        hz = ARCH_SPRING * (1 - t * (1 - SHELL_TAPER_Z))
        for sign in (-1, 1):
            c = Vector((x, sign * (hw - 0.05), hz / 2))
            kit.box("Hall_Plaster", c, Vector((1, 0, 0)), (0.5, 0.12, hz))
            kit.box("Hall_Gold", Vector((x, sign * (hw - 0.08), hz - 0.25)),
                    Vector((1, 0, 0)), (0.62, 0.18, 0.5))
    for sign in (-1, 1):
        a = [Vector((p.x, sign * (abs(p.y) - 0.03), p.z)) for p in
             (reveal[1], back[1])]
        kit.face("Hall_Gold", [a[0] - Vector((0, 0, 0.25)), a[1] - Vector((0, 0, 0.25)),
                               a[1], a[0]])


def build_house(kit):
    # Parquet floor, raked toward the back, as strips across the plan.
    xs = [PROSC_X + (HALL_BACK_X - PROSC_X) * i / 40 for i in range(41)]
    left = [Vector((x, -wall_half_width(x), parquet_z(x))) for x in xs]
    right = [Vector((x, wall_half_width(x), parquet_z(x))) for x in xs]
    kit.strip("Hall_Carpet", left, right)

    # Walls round the horseshoe, up to the ceiling.
    wall, _ = horseshoe(0.0, PROSC_X)
    kit.strip("Hall_Plaster", at_z(wall, PARQUET_Z - 0.05), at_z(wall, CEILING_Z))
    # Gilt cornice and a dado rail.
    wall_in, _ = horseshoe(0.04, PROSC_X)
    kit.strip("Hall_Gold", at_z(wall_in, CEILING_Z - 0.55), at_z(wall_in, CEILING_Z - 0.05))
    kit.strip("Hall_Dark_Wood", at_z(wall_in, PARQUET_Z), at_z(wall_in, PARQUET_Z + 1.1))

    # Ceiling: an annulus between the plan and the dome's oval opening.
    plan = [(p.x, p.y) for p in wall]  # closes along the proscenium wall
    oval = ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64)
    a, b = ring(oval, plan, (DOME_CX, 0.0))
    kit.strip("Hall_Plaster", [Vector((x, y, CEILING_Z)) for x, y in a],
              [Vector((x, y, CEILING_Z)) for x, y in b], closed=True)

    # Shallow oval dome over the house.
    rings = []
    for k in range(9):
        phi = (math.pi / 2) * k / 8
        s = math.cos(phi)
        z = CEILING_Z + DOME_H * math.sin(phi)
        rings.append([Vector((x, y, z)) for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64, s)])
    for ra, rb in zip(rings, rings[1:]):
        kit.strip("Hall_Plaster", ra, rb, smooth=True, closed=True)

    # Gilt rings at the dome rim and a centre medallion.
    for s0, s1, z in ((1.0, 1.07, CEILING_Z - 0.02), (0.55, 0.6, None)):
        if z is None:  # hang just below the dome's surface at the ring's outer edge
            z = CEILING_Z + DOME_H * math.sqrt(1 - s1 * s1) - 0.04
        ra = [Vector((x, y, z)) for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64, s0)]
        rb = [Vector((x, y, z)) for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64, s1)]
        kit.strip("Hall_Gold", ra, rb, closed=True)
    med = [Vector((x, y, CEILING_Z + DOME_H - 0.02)) for x, y in ellipse(DOME_CX, 0.0, 1.2, 1.0, 24)]
    kit.face("Hall_Gold", list(reversed(med)))

    # Rings of bulbs: round the rim, and two inside the dome.
    for s, n, zoff in ((1.035, 56, -0.12), (0.8, 44, None), (0.45, 28, None)):
        for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, n, s):
            if zoff is None:
                z = CEILING_Z + DOME_H * math.sqrt(max(0.0, 1 - s * s)) - 0.1
            else:
                z = CEILING_Z + zoff
            kit.bulb(Vector((x, y, z)), 0.09)

    # Parquet seating: curved rows facing the stage, with two aisles.
    focus = Vector((STAGE_FRONT_X - 8.0, 0.0, 0.0))
    x = STAGE_FRONT_X + 2.6
    while x < HALL_BACK_X - 2.2:
        radius = x - focus.x
        dth = SEAT_PITCH / radius
        n = int(math.asin(min(1.0, HALL_HALF_W / radius)) / dth) + 1
        for i in range(-n, n + 1):
            th = i * dth
            p = Vector((focus.x + radius * math.cos(th), radius * math.sin(th), 0))
            if p.x > HALL_BACK_X - 1.6 or abs(p.y) > wall_half_width(p.x) - 1.3:
                continue
            if 4.0 < abs(p.y) < 5.2:
                continue
            p.z = parquet_z(p.x)
            add_seat(kit, p, focus - p)
        x += ROW_PITCH * 1.05


def build_trim(kit):
    """Ornament and fittings that make the room read as Carnegie Hall."""
    # Coffered reveal: gilt ribs across the arch soffit with rosettes between.
    profile = [Vector((PROSC_X, y, z)) for y, z in
               arch_outline(ARCH_HALF_W, ARCH_SPRING, ARCH_RISE, closed=False)]
    marks = resample(profile, 1.3)
    for i, (p, t) in enumerate(marks):
        n = Vector((0, t.z, -t.y))  # into the opening
        if p.z < ARCH_SPRING - 0.1:  # coffers on the arch head only
            continue
        a = p + n * 0.03
        kit.face("Hall_Gold", [a - t * 0.08, a + t * 0.08,
                               a + t * 0.08 - Vector((REVEAL, 0, 0)), a - t * 0.08 - Vector((REVEAL, 0, 0))])
        if i + 1 < len(marks):
            mid = (p + marks[i + 1][0]) / 2 + n * 0.08 - Vector((REVEAL / 2, 0, 0))
            kit.box("Hall_Gold", mid, Vector((1, 0, 0)), (0.24, 0.24, 0.24))

    # Ceiling: gilt ribs from the dome out to the walls, and an outer oval.
    wall, _ = horseshoe(0.0, PROSC_X)
    plan = [(p.x, p.y) for p in wall]
    oval = ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64)
    a, b = ring(oval, plan, (DOME_CX, 0.0))
    zc = CEILING_Z - 0.03
    for i in range(0, len(a), 6):
        pa, pb = Vector((*a[i], zc)), Vector((*b[i], zc))
        d = (pb - pa).normalized()
        side = Vector((-d.y, d.x, 0)) * 0.15
        kit.face("Hall_Gold", [pa - side, pb - side, pb + side, pa + side])
    ra = [Vector((x, y, zc - 0.01)) for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64, 1.30)]
    rb = [Vector((x, y, zc - 0.01)) for x, y in ellipse(DOME_CX, 0.0, DOME_A, DOME_B, 64, 1.34)]
    kit.strip("Hall_Gold", ra, rb, closed=True)

    # Dome: gilt meridian ribs from the rim up to the inner ring.
    phi_top = math.acos(0.6)
    for k in range(20):
        th = math.tau * k / 20
        left, right = [], []
        for j in range(7):
            phi = phi_top * j / 6
            sc = math.cos(phi) * 0.995
            z = CEILING_Z + DOME_H * math.sin(phi) - 0.04
            d = 0.15 / (0.5 * (DOME_A + DOME_B) * sc)
            for th2, out in ((th - d, left), (th + d, right)):
                out.append(Vector((DOME_CX + DOME_A * sc * math.cos(th2),
                                   DOME_B * sc * math.sin(th2), z)))
        kit.strip("Hall_Gold", left, right, smooth=True)

    # Tall arched panels on the side walls between the proscenium and the
    # Dress Circle, framed in gilt with damask fields.
    for sign in (-1, 1):
        y = sign * (HALL_HALF_W - 0.03)

        def wall_pt(u, v, y=y):
            return Vector((5.3 + u, y, v))

        arch_fill(kit, "Hall_Fabric", 1.9, 10.2, 18.5, 1.9, wall_pt, cols=6)
        arch_frame(kit, 1.9, 10.2, 18.5, 1.9, 0.22,
                   lambda u, v, y=y: Vector((5.3 + u, y + sign * -0.01, v)))

    # Doors with exit signs: back of the parquet and along the side walls.
    xb = HALL_BACK_X - 0.05
    floor = parquet_z(HALL_BACK_X)
    for yc in (-2.4, 2.4):
        add_door(kit, Vector((xb, yc - 0.75, 0)), Vector((xb, yc + 0.75, 0)), floor, exit_sign=True)
    for x in (12.0, 20.0):
        for sign in (-1, 1):
            y = sign * (HALL_HALF_W - 0.05)
            a, b = Vector((x - 0.75, y, 0)), Vector((x + 0.75, y, 0))
            if sign > 0:
                a, b = b, a
            add_door(kit, a, b, parquet_z(x), exit_sign=x > 15)

    # Darker runners down the two aisles.
    xs = [STAGE_FRONT_X + 2.0 + (HALL_BACK_X - 1.6 - STAGE_FRONT_X - 2.0) * i / 24 for i in range(25)]
    for sign in (-1, 1):
        lo = [Vector((x, sign * 4.05, parquet_z(x) + 0.006)) for x in xs]
        hi = [Vector((x, sign * 5.15, parquet_z(x) + 0.006)) for x in xs]
        kit.strip("Hall_Carpet", lo if sign > 0 else hi, hi if sign > 0 else lo, 0.7)

    # Side doors into the stage shell near the back wall.
    def shell_hw(x):
        t = (PROSC_X - REVEAL - x) / (PROSC_X - REVEAL - STAGE_BACK_X)
        return ARCH_HALF_W * (1 - t * (1 - SHELL_TAPER_Y))

    for sign in (-1, 1):
        x0, x1 = -9.35, -7.95
        a = Vector((x0, sign * (shell_hw(x0) - 0.03), 0))
        b = Vector((x1, sign * (shell_hw(x1) - 0.03), 0))
        if sign > 0:
            a, b = b, a
        add_door(kit, a, b, STAGE_TOP, height=2.6)


def build_tier(kit, name, z, x_start, depth, rows, boxes, step):
    """One horseshoe tier: slab, soffit, parapet, lamps, boxes and seats."""
    rail, normals = horseshoe(depth, x_start)
    wall, _ = horseshoe(0.0, x_start)
    soffit_z = z - 0.6
    top_z = z + rows * step

    # Floor: a tread per row, rising toward the wall. The first starts behind
    # the parapet so its edge doesn't flicker through the parapet face.
    edges = [depth - 0.18] + [depth - 0.45 - ROW_PITCH * k for k in range(1, rows)] + [0.0]
    for k in range(rows):
        za = z + step * k
        a, _ = horseshoe(edges[k], x_start)
        b, _ = horseshoe(edges[k + 1], x_start)
        kit.strip("Hall_Carpet", at_z(a, za), at_z(b, za))
        if k + 1 < rows and step > 0:
            kit.strip("Hall_Dark_Wood", at_z(b, za), at_z(b, za + step))

    # Soffit and the face of the slab.
    kit.strip("Hall_Plaster", at_z(wall, soffit_z), at_z(rail, soffit_z))
    # Parapet: plaster front with gilt mouldings and a velvet capping.
    cap_z = z + 0.95
    front = horseshoe(depth + 0.02, x_start)[0]
    kit.strip("Hall_Plaster", at_z(rail, soffit_z), at_z(rail, cap_z))
    back = horseshoe(depth - 0.18, x_start)[0]
    kit.strip("Hall_Plaster", at_z(back, cap_z), at_z(back, z))
    kit.strip("Hall_Velvet", at_z(rail, cap_z), at_z(back, cap_z))
    kit.strip("Hall_Gold", at_z(front, cap_z - 0.16), at_z(front, cap_z - 0.04))
    kit.strip("Hall_Gold", at_z(front, soffit_z + 0.05), at_z(front, soffit_z + 0.22))
    kit.strip("Hall_Gold", at_z(front, z + 0.15), at_z(front, z + 0.25))
    # Gilt panel frames along the straight runs of the parapet front.
    face_path = horseshoe(depth + 0.035, x_start)[0]
    for p, t in resample(face_path, 1.7):
        if p.x > x_start + 0.9 and on_straight(p, 0.7):
            add_frame(kit, p, t, z + 0.32, cap_z - 0.24, 1.3)
    # Red damask lining the boxes.
    if boxes:
        lining = horseshoe(0.02, x_start)[0]
        kit.strip("Hall_Fabric", at_z(lining, z), at_z(lining, z + 2.6))

    # End caps, a hair beyond the tier so the tread edges don't z-fight them.
    for i in (0, -1):
        x = x_start - 0.01
        kit.face("Hall_Plaster", [Vector((x, rail[i].y, soffit_z)),
                                  Vector((x, wall[i].y, soffit_z)),
                                  Vector((x, wall[i].y, top_z + 1.0)),
                                  Vector((x, rail[i].y, cap_z))])

    # Lamps along the soffit edge.
    line = at_z(horseshoe(depth - 0.25, x_start)[0], soffit_z - 0.09)
    for p, _ in resample(line, 1.6):
        kit.bulb(p, 0.07)

    # Box partitions for the boxed tiers.
    if boxes:
        for p, tangent in resample(rail, 2.7):
            n = Vector((tangent.y, -tangent.x, 0))  # outward (toward the wall)
            # From behind the parapet back to the wall.
            c = p + n * ((depth + 0.18) / 2) + Vector((0, 0, 0.8))
            kit.box("Hall_Plaster", c, n, (depth - 0.18, 0.07, 1.6))

    # Seats, one row per tread, facing in across the hall.
    for k in range(rows):
        inset = depth - 0.75 - ROW_PITCH * k
        if inset < 0.35:
            break
        row = horseshoe(inset, x_start)[0]
        for p, tangent in resample(row, SEAT_PITCH):
            if p.x < x_start + 0.5:
                continue
            inward = Vector((-tangent.y, tangent.x, 0))
            p = Vector((p.x, p.y, z + step * k))
            add_seat(kit, p, inward)
    return name


# --- Scene assembly ---------------------------------------------------------


def make_material(name, spec):
    color, metallic, roughness, emission = spec
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = (*color, 1.0)
    return mat


def clear_previous():
    coll = bpy.data.collections.get(COLLECTION)
    if not coll:
        return
    for obj in list(coll.all_objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Light):
                bpy.data.lights.remove(data)
            elif isinstance(data, bpy.types.Camera):
                bpy.data.cameras.remove(data)
    for child in list(coll.children):
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(coll)


def orient_faces(meshes):
    """Point every open face toward the room, so the bake lights the right side.

    The procedural surfaces are wound arbitrarily, and Cycles bakes the side a
    normal points to. For each face, look both ways: the side with the longer
    clear view is the room (a wall's back sees nothing, a soffit's top sees
    the tier floor 0.6 m up, a parapet's inner face sees its back 0.18 m away).
    Each side casts a small fan of rays, so a pilaster right in front of a
    wall doesn't make the wall's back look more open than the stage.
    Closed solids (seats, boxes, lamps) were already oriented outward.
    """
    verts, polys = [], []
    for bm in meshes.values():
        base = len(verts)
        bm.verts.index_update()
        verts.extend(v.co.copy() for v in bm.verts)
        polys.extend([base + v.index for v in f.verts] for f in bm.faces)
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=False)

    def clearance(origin, n):
        # Normal plus four rays tilted 45 degrees; escaping counts as zero
        # (that side is outside the hall).
        t = n.orthogonal().normalized()
        b = n.cross(t)
        total = 0.0
        for d in (n, n + t, n - t, n + b, n - b):
            hit = tree.ray_cast(origin, d.normalized())
            total += hit[3] if hit[0] is not None else 0.0
        return total

    flipped = 0
    for bm in meshes.values():
        solid = bm.faces.layers.int["solid"]
        for f in bm.faces:
            if f[solid]:
                continue
            f.normal_update()
            n = f.normal
            if n.length < 0.5:
                continue
            c = f.calc_center_median()
            if clearance(c - n * 0.004, -n) > clearance(c + n * 0.004, n):
                f.normal_flip()
                flipped += 1
    print(f"[carnegie] oriented normals ({flipped:,} faces flipped)")


def build():
    clear_previous()
    coll = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(coll)

    kit = Kit()
    build_stage(kit)
    build_proscenium_and_shell(kit)
    build_house(kit)
    for tier in TIERS:
        build_tier(kit, *tier)
    build_trim(kit)

    orient_faces(kit.meshes)
    meshes = []
    for mat_name, bm in kit.meshes.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        mesh = bpy.data.meshes.new(mat_name)
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(make_material(mat_name, MATERIALS[mat_name]))
        obj = bpy.data.objects.new(mat_name, mesh)
        coll.objects.link(obj)
        meshes.append(obj)
    return coll, meshes


def add_lights(coll):
    """Concert lighting: used for the bake, and kept in the .blend for renders."""
    warm = (1.0, 0.84, 0.66)
    stage = (1.0, 0.94, 0.86)

    def light(name, kind, loc, energy, color, aim=None, rot_z=0.0, **props):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color
        for key, value in props.items():
            setattr(data, key, value)
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        if aim is not None:
            obj.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        else:
            obj.rotation_euler = (0.0, 0.0, rot_z)  # pointing straight down
        coll.objects.link(obj)
        return obj

    # Stage: a broad overhead wash plus two front-of-house keys from the ceiling.
    light("Hall_Stage_Wash", "AREA", (-2.5, 0.0, 12.5), 16000, stage,
          shape="RECTANGLE", size=10.0, size_y=7.0)
    for sign in (-1, 1):
        light(f"Hall_Front_Key_{'L' if sign < 0 else 'R'}", "SPOT", (12.0, sign * 5.0, 16.0),
              45000, stage, aim=(0.0, 0.0, 1.0), spot_size=math.radians(38), spot_blend=0.6)
    # House: the dome glow and the lamp rows under every tier.
    light("Hall_Dome_Glow", "AREA", (DOME_CX, 0.0, CEILING_Z + 0.3), 90000, warm,
          shape="ELLIPSE", size=2 * DOME_A, size_y=2 * DOME_B)
    # Ceiling downlights over the stalls and the upper tiers.
    for x in (6.0, 12.0, 24.0, 29.0):
        for y in (-9.0, 0.0, 9.0):
            if abs(y) < 1 and 9 < x < 27:
                continue  # the dome covers the middle
            light(f"Hall_Downlight_{int(x)}_{int(y)}", "AREA", (x, y, CEILING_Z - 0.1), 9000, warm,
                  shape="DISK", size=2.0)
    # A soft glow in the middle of the house lights the tier fronts, which
    # face inward and catch nothing from the downlights.
    light("Hall_House_Fill", "POINT", (18.0, 0.0, 9.0), 60000, warm, shadow_soft_size=3.0)
    # Uplight into the dome, which the downward glow leaves dark.
    light("Hall_Dome_Uplight", "AREA", (DOME_CX, 0.0, CEILING_Z - 0.6), 25000, warm,
          aim=(DOME_CX, 0.0, CEILING_Z + 10.0), shape="ELLIPSE", size=1.6 * DOME_A, size_y=1.6 * DOME_B)
    # Uplight into the stage vault, which the overhead wash can't reach.
    light("Hall_Vault_Uplight", "AREA", (-4.0, 0.0, 7.0), 7000, stage, aim=(-4.0, 0.0, 20.0),
          shape="RECTANGLE", size=8.0, size_y=6.0)
    # Washes on the stage shell's side walls.
    for sign in (-1, 1):
        light(f"Hall_Shell_Wash_{'L' if sign < 0 else 'R'}", "AREA", (-3.5, sign * 3.5, 9.0), 9000,
              stage, aim=(-3.5, sign * 9.0, 4.0), shape="RECTANGLE", size=9.0, size_y=4.0)
    cx = HALL_BACK_X - HALL_CORNER_R
    cy = HALL_HALF_W - HALL_CORNER_R
    for name, z, x_start, depth, *_ in TIERS:
        zl = z - 0.75
        run = cx - x_start
        w = depth * 0.6
        for sign in (-1, 1):
            light(f"Hall_{name}_Lamps_{'L' if sign < 0 else 'R'}", "AREA",
                  (x_start + run / 2, sign * (HALL_HALF_W - depth / 2), zl), 220 * run * w, warm,
                  shape="RECTANGLE", size=run, size_y=w)
        light(f"Hall_{name}_Lamps_Back", "AREA", (HALL_BACK_X - depth / 2, 0.0, zl),
              220 * 2 * cy * w, warm, rot_z=math.pi / 2, shape="RECTANGLE", size=2 * cy, size_y=w)


def set_world():
    """A dim, warm house: the hall is lit by its own lights, not the sky."""
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.02, 0.016, 0.012, 1.0)
        bg.inputs["Strength"].default_value = 1.0


def add_camera(coll):
    cam_data = bpy.data.cameras.new("Hall_Camera")
    cam_data.lens = 35
    cam = bpy.data.objects.new("Hall_Camera", cam_data)
    cam.location = (24.0, -7.5, 5.5)
    cam.rotation_euler = (Vector((0.0, 0.0, 2.6)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(cam)
    return cam


def bake_lighting(meshes):
    """Bake diffuse light (direct + bounce, no albedo) into each mesh's corners.

    The piano and the studio rig are hidden so only the hall and its lights
    count; metals bake as diffuse so the gilt gets occlusion like the plaster.
    Bakes per vertex (shared corners agree, so no per-face blotches), smooths
    the Monte Carlo noise, then writes Hall_Light = curve(bake) x Hall_Tone.
    The curve divides by the median and applies x / (1 + x): ordinary
    surfaces land near 0.5, the lit stage rolls off toward 1 instead of
    clipping. Returns the median used.
    """
    import numpy as np

    scene = bpy.context.scene
    saved_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.samples = BAKE_SAMPLES
    hidden = [o for o in scene.objects
              if COLLECTION not in {c.name for c in o.users_collection} and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    metals = []
    for o in meshes:
        for mat in o.data.materials:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            metals.append((bsdf, bsdf.inputs["Metallic"].default_value))
            bsdf.inputs["Metallic"].default_value = 0.0

    targets = [o for o in meshes if o.name not in UNBAKED]
    for o in targets:
        attr = o.data.color_attributes.new(BAKE_ATTR, "FLOAT_COLOR", "POINT")
        o.data.color_attributes.active_color = attr
    bpy.ops.object.select_all(action="DESELECT")
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    t0 = time.time()
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"},
                        target="VERTEX_COLORS", use_clear=True)
    print(f"[carnegie] baked lighting in {time.time() - t0:.1f}s")

    for bsdf, value in metals:
        bsdf.inputs["Metallic"].default_value = value
    for o in hidden:
        o.hide_render = False
    scene.render.engine = saved_engine

    def read(mesh, name):
        attr = mesh.color_attributes[name]
        arr = np.empty(len(attr.data) * 4, dtype=np.float32)
        attr.data.foreach_get("color", arr)
        return arr.reshape(-1, 4)

    baked = {}
    for o in targets:
        mesh = o.data
        light = read(mesh, BAKE_ATTR)[:, :3].astype(np.float64)
        edges = np.empty(len(mesh.edges) * 2, dtype=np.int64)
        mesh.edges.foreach_get("vertices", edges)
        a, b = edges[0::2], edges[1::2]
        for _ in range(BAKE_SMOOTH):
            acc = light.copy()
            deg = np.ones(len(light))
            np.add.at(acc, a, light[b])
            np.add.at(acc, b, light[a])
            np.add.at(deg, a, 1)
            np.add.at(deg, b, 1)
            light = acc / deg[:, None]
        baked[o.name] = light
        mesh.color_attributes.remove(mesh.color_attributes[BAKE_ATTR])

    median = float(np.median(np.concatenate([v.max(axis=1) for v in baked.values()])))
    for o in meshes:
        mesh = o.data
        tone = read(mesh, TONE_ATTR)
        if o.name in baked:
            x = baked[o.name] / max(median, 1e-6)
            light = x / (1.0 + x.max(axis=1, keepdims=True))  # hue-preserving roll-off
            loop_verts = np.empty(len(mesh.loops), dtype=np.int64)
            mesh.loops.foreach_get("vertex_index", loop_verts)
            rgb = light[loop_verts] * tone[:, :1]
            out = np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1)
        else:
            out = tone
        attr = mesh.color_attributes.new(LIGHT_ATTR, "FLOAT_COLOR", "CORNER")
        attr.data.foreach_set("color", out.astype(np.float32).ravel())
        mesh.color_attributes.remove(mesh.color_attributes[TONE_ATTR])
    return median


def export_glb(meshes, out):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=out,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_vertex_color="NAME",
        export_vertex_color_name=LIGHT_ATTR,
        export_extras=False,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
    )


def main():
    t0 = time.time()
    root = _repo_root()
    argv = _argv_after_double_dash()
    out_glb = os.path.join(root, "web", "public", "models", "carnegie_hall.glb")
    if "--out" in argv:
        out_glb = os.path.abspath(argv[argv.index("--out") + 1])
    out_blend = os.path.join(root, "assets", "steinway_carnegie_hall.blend")

    coll, meshes = build()
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    print(f"[carnegie] {len(meshes)} meshes, {tris:,} triangles")
    add_lights(coll)
    set_world()
    median = bake_lighting(meshes)
    print(f"[carnegie] bake median {median:.3f}")

    export_glb(meshes, out_glb)
    print(f"[carnegie] wrote {out_glb} ({os.path.getsize(out_glb) / 1e6:.1f} MB)")

    if "--no-blend" not in argv:
        scene = bpy.context.scene
        scene.camera = add_camera(coll)
        bpy.ops.wm.save_as_mainfile(filepath=out_blend, copy=True)
        print(f"[carnegie] wrote {out_blend}")
    print(f"[carnegie] done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
