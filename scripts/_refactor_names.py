"""One-shot Title_Case_With_Underscores normalization of the playable .blend.

Single source of truth for the rename map so the .blend and the code that
references part/collection names by string literal cannot drift apart.

Two modes (auto-detected):

* **blend mode** (run under Blender) - rename collections + objects, drop the
  orphan ``Collection``, save::

      B=/Applications/Blender.app/Contents/MacOS/Blender
      $B --background assets/steinway_grand_playable.blend \\
          --python scripts/_refactor_names.py -- --out assets/steinway_grand_playable.blend

* **code mode** (run under plain python3) - substring-rewrite every hardcoded
  name literal in the operator/export/web files::

      python3 scripts/_refactor_names.py --code

Convention: Title_Case_With_Underscores, glTF-safe (three.js rewrites spaces /
``&`` / dots in node names anyway, so make the Blender name *equal* the exported
node name). Indexed action/key series (``Key.NNN``, ``Hammer.NNN`` ...) keep
their dotted index. ``Curve.001`` is left as the documented stray-curve sentinel
that export_glb / scene-utils strip by name.
"""

from __future__ import annotations

# Collections to delete outright (orphan leftover; its only member, Camera, is
# also linked under Environment, so the object survives).
DELETE_COLLECTIONS = ["Collection"]

COLLECTION_RENAMES = {
    "EVIROMENT": "Environment",
    "STEINWAY GRAND PIANO": "Steinway_Grand_Piano",
    "KEYS": "Keys",
    "WHEELS": "Wheels",
    "SUSTAIN PEDALS": "Sustain_Pedals",
    "LEGS": "Legs",
    "LID PROP": "Lid_Prop",
    "LID SECTIONS": "Lid_Sections",
    "LID Butt Hinges": "Lid_Butt_Hinges",
    "Continous Hinge for LID": "Continuous_Hinge_For_Lid",
    "MUSIC RACK SECTIONS": "Music_Rack_Sections",
    "Steinway & Sons Logo": "Steinway_And_Sons_Logo",
    "Brass Sound Works": "Brass_Sound_Works",
    # Already convention-compliant (kept, listed for completeness):
    # "Bench", "Steinway_Action", "Steinway_Keys"
}

OBJECT_RENAMES = {
    # --- case / body ---
    "Piano Outer Body": "Piano_Outer_Body",
    "Piano Base": "Piano_Base",
    "Inside Rim Case": "Inside_Rim_Case",
    "Name Board": "Name_Board",
    "Fall Board": "Fall_Board",
    "Key Slip": "Key_Slip",
    "Key Block Left": "Key_Block_Left",
    "Key Block Right": "Key_Block_Right",
    "Curve": "Steinway_Logo",            # logo decal mesh (joins Piano_Static)
    # --- interior ---
    "Dampers Bottoms": "Dampers_Bottoms",
    "Dampers Tops": "Dampers_Tops",
    "String Pins": "String_Pins",
    "String Supports-01": "String_Supports_01",
    "String Supports-02": "String_Supports_02",
    # --- legs / wheels / pedals ---
    "Left Main Leg": "Left_Main_Leg",
    "Right Main Leg": "Right_Main_Leg",
    "Middle Main Leg": "Middle_Main_Leg",
    "Wheel-01": "Wheel_01",
    "Wheel-02": "Wheel_02",
    "Wheel-03": "Wheel_03",
    "Left SustainPedal": "Left_Sustain_Pedal",
    "Right Sustain Pedal": "Right_Sustain_Pedal",
    "Middle Sustain Pedal": "Middle_Sustain_Pedal",
    "Left Pedal Connector Rod": "Left_Pedal_Connector_Rod",
    "Middle Pedal Connector Rod": "Middle_Pedal_Connector_Rod",
    "Right Pedal Connector Rod": "Right_Pedal_Connector_Rod",
    "Base Main Pedal Post": "Base_Main_Pedal_Post",
    "Left Main Pedal Post": "Left_Main_Pedal_Post",
    "Right Main Pedal Post": "Right_Main_Pedal_Post",
    # --- lid sections + hinges ---
    "Large Lid Section": "Large_Lid_Section",
    "Small Lid Section": "Small_Lid_Section",
    "Large Lid Rubber Cushions": "Large_Lid_Rubber_Cushions",
    "Small Lid Rubber Cushions": "Small_Lid_Rubber_Cushions",
    "Lid Butt Hinge": "Lid_Butt_Hinge",
    "Lid Butt Hinge.001": "Lid_Butt_Hinge.001",
    "Base Butt Hinge": "Base_Butt_Hinge",
    "Base Butt Hinge.001": "Base_Butt_Hinge.001",
    "Butt Hinge Rod": "Butt_Hinge_Rod",
    "Butt Hinge Rod.001": "Butt_Hinge_Rod.001",
    "Long Continous Hinge ROD": "Long_Continuous_Hinge_Rod",
    "Long Continuos Hinge TOP": "Long_Continuous_Hinge_Top",
    "Long Continuos Hinge BOTTOM": "Long_Continuous_Hinge_Bottom",
    "Long Continous Hinge Screws": "Long_Continuous_Hinge_Screws",
    # --- lid prop ---
    "Lid Support Cup": "Lid_Support_Cup",
    "Lid Support Prop": "Lid_Support_Prop",
    "Lip Prop Hinge": "Lid_Prop_Hinge",   # misspelling: Lip -> Lid
    "Lid Prop Hinge Rod": "Lid_Prop_Hinge_Rod",
    "Lid Prop Hinge Bolt Heads": "Lid_Prop_Hinge_Bolt_Heads",
    "Lid Prop Hinge Screws": "Lid_Prop_Hinge_Screws",
    # --- music rack ---
    "Music Shelf": "Music_Shelf",
    "Music Rack": "Music_Rack",
    "Sheet Music Page Holder": "Sheet_Music_Page_Holder",
    # --- bench ---
    "Seat Cushion": "Seat_Cushion",
    "Seat Frame": "Seat_Frame",
    "Leg-01": "Bench_Leg_01",
    "Leg-02": "Bench_Leg_02",
    "Leg-03": "Bench_Leg_03",
    "Leg-04": "Bench_Leg_04",
    # --- rig empties ---
    "Key Lid Hinge": "Key_Lid_Hinge",
    "Lid Fold Frame": "Lid_Fold_Frame",
    "Lid Fold Hinge": "Lid_Fold_Hinge",
    # Already convention-compliant (kept): Soundboard, Strings, Strings_Full,
    # Tuning_Pins, Hitch_Pins, String_Pins, Action_Frame, Damper_Tray,
    # Brass_Sound_Works.001/.002, Curve.001 (sentinel).
}


# Files whose hardcoded name literals must track the rename (code mode).
# Excluded on purpose:
#   * web/src/scene-utils.js - its only relevant literal is the "Curve" stray-
#     curve sentinel, which is left as Curve.001 (not renamed) by design.
#   * build/retarget.py - the one-time bootstrap runs against the *raw* import
#     (old space-separated names), so its source-lookup literals must stay old.
CODE_FILES = [
    "scripts/export_glb.py",
    "scripts/inspect_dampers.py",
    "scripts/inspect_scene.py",
    "extension/steinway_midi_piano/build/case.py",
    "extension/steinway_midi_piano/build/harp.py",
    "extension/steinway_midi_piano/build/action.py",
    "extension/steinway_midi_piano/build/strings.py",
    "web/src/case.js",
]


def _all_renames():
    """Merged name map for code-mode substring replacement."""
    m = {}
    m.update(COLLECTION_RENAMES)
    m.update(OBJECT_RENAMES)
    return m


def run_blend(out_path):
    import bpy

    renamed_coll = renamed_obj = 0
    for old, new in COLLECTION_RENAMES.items():
        c = bpy.data.collections.get(old)
        if c is not None:
            c.name = new
            renamed_coll += 1
        else:
            print(f"[refactor] WARN collection not found: {old!r}")
    for old, new in OBJECT_RENAMES.items():
        o = bpy.data.objects.get(old)
        if o is not None:
            o.name = new
            renamed_obj += 1
        else:
            print(f"[refactor] WARN object not found: {old!r}")
    for name in DELETE_COLLECTIONS:
        c = bpy.data.collections.get(name)
        if c is not None:
            members = [o.name for o in c.objects]
            bpy.data.collections.remove(c)
            print(f"[refactor] removed collection {name!r} (members kept: {members})")

    # Verify no target name accidentally collided (Blender appends .001 on clash).
    for new in list(COLLECTION_RENAMES.values()):
        if bpy.data.collections.get(new) is None:
            print(f"[refactor] ERROR expected collection missing after rename: {new!r}")
    for new in list(OBJECT_RENAMES.values()):
        if bpy.data.objects.get(new) is None:
            print(f"[refactor] ERROR expected object missing after rename: {new!r}")

    print(f"[refactor] collections renamed: {renamed_coll}, objects renamed: {renamed_obj}")
    if out_path:
        bpy.ops.wm.save_as_mainfile(filepath=out_path)
        print(f"[refactor] saved {out_path}")
    else:
        print("[refactor] dry run (no --out): nothing written")


def run_code():
    import os

    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    renames = _all_renames()
    # Skip bare-word keys (no space / hyphen / dot): those can collide with code
    # identifiers (e.g. "KEYS" inside KEYS_COLL, "Curve" inside isStrayCurve...).
    # They never appear as standalone name literals in the code anyway; the .blend
    # rename already covers them. Multi-token names can only appear quoted.
    bare = re.compile(r"^[A-Za-z0-9]+$")
    safe = {k: v for k, v in renames.items() if not bare.match(k)}
    # Longest first so a shorter key never corrupts a longer literal.
    keys = sorted(safe, key=len, reverse=True)
    total = 0
    for rel in CODE_FILES:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            print(f"[refactor] skip (missing): {rel}")
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        n = 0
        for old in keys:
            new = renames[old]
            if old in text:
                cnt = text.count(old)
                text = text.replace(old, new)
                n += cnt
        if n:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"[refactor] {rel}: {n} replacement(s)")
            total += n
    print(f"[refactor] code replacements total: {total}")


def main():
    import sys

    try:
        import bpy  # noqa: F401
        is_blend = True
    except ImportError:
        is_blend = False

    if is_blend:
        argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
        out = None
        if "--out" in argv:
            out = argv[argv.index("--out") + 1]
            if not out.startswith("/"):
                import os
                out = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), out
                )
        run_blend(out)
    else:
        run_code()


main()
