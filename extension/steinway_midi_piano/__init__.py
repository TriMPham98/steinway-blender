"""Steinway MIDI Piano.

Play a procedural Steinway Model D in Blender, live, from a MIDI keyboard
(developed against a Yamaha P515). The package is split into:

  build/   - pure procedural geometry (keyboard + case), no MIDI
  midi.py  - thin mido wrapper (no bpy)
  anim.py  - note -> key-rotation state machine (bpy, main thread only)
  props,operators,panel - the add-on UI glue

The build/ and anim/ modules are intentionally import-safe without the MIDI
backend so the model can be generated and tested headlessly.
"""

from . import props, operators, panel

_MODULES = (props, operators, panel)


def register():
    for mod in _MODULES:
        mod.register()


def unregister():
    for mod in reversed(_MODULES):
        mod.unregister()
