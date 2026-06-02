"""Scene properties for the Steinway MIDI add-on."""

import math

import bpy

from . import midi

# Held at module scope so Blender does not garbage-collect the enum item strings
# returned from the dynamic callback (a well-known EnumProperty pitfall).
_PORT_ITEMS = [("__none__", "No MIDI inputs found", "")]


def _port_items(self, context):
    names = midi.list_input_ports()
    items = [(n, n, "") for n in names] if names else [("__none__", "No MIDI inputs found", "")]
    _PORT_ITEMS.clear()
    _PORT_ITEMS.extend(items)
    return _PORT_ITEMS


class STEINWAY_Props(bpy.types.PropertyGroup):
    midi_port: bpy.props.EnumProperty(
        name="MIDI Port",
        description="MIDI input device to listen to (e.g. your Yamaha P-515)",
        items=_port_items,
    )
    press_angle: bpy.props.FloatProperty(
        name="Press Angle",
        description="How far a key tips down when pressed",
        default=math.radians(3.5), min=0.0, max=math.radians(12.0),
        subtype="ANGLE",
    )
    smoothing: bpy.props.FloatProperty(
        name="Smoothing",
        description="Key easing per tick (1.0 = instant snap, lower = softer)",
        default=0.5, min=0.05, max=1.0,
    )
    running: bpy.props.BoolProperty(name="Running", default=False)


def register():
    bpy.utils.register_class(STEINWAY_Props)
    bpy.types.Scene.steinway = bpy.props.PointerProperty(type=STEINWAY_Props)


def unregister():
    if hasattr(bpy.types.Scene, "steinway"):
        del bpy.types.Scene.steinway
    bpy.utils.unregister_class(STEINWAY_Props)
