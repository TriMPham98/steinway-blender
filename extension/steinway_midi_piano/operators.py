"""Operators: build the model, install the MIDI backend, and run live playback."""

import os
import sys
import subprocess

import bpy

from .build import keyboard, case
from . import midi, anim


class STEINWAY_OT_build(bpy.types.Operator):
    bl_idname = "steinway.build"
    bl_label = "Build Piano"
    bl_description = "Generate the procedural Steinway Model D (keyboard + case)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        keyboard.build()
        case.build()
        self.report({"INFO"}, "Built Steinway Model D (88 keys)")
        return {"FINISHED"}


class STEINWAY_OT_install_backend(bpy.types.Operator):
    bl_idname = "steinway.install_backend"
    bl_label = "Install MIDI Backend"
    bl_description = (
        "pip install python-rtmidi into Blender's Python "
        "(fallback when the extension's bundled wheel is unavailable)"
    )

    def execute(self, context):
        if midi.backend_available():
            self.report({"INFO"}, "MIDI backend already available")
            return {"FINISHED"}
        py = os.path.join(
            sys.prefix, "bin", f"python{sys.version_info.major}.{sys.version_info.minor}"
        )
        try:
            subprocess.check_call([py, "-m", "pip", "install", "python-rtmidi"])
        except Exception as exc:  # noqa: BLE001 - surface any pip failure to the user
            self.report({"ERROR"}, f"pip install failed: {exc}")
            return {"CANCELLED"}
        if midi.backend_available():
            self.report({"INFO"}, "Installed python-rtmidi")
        else:
            self.report({"WARNING"}, "Installed, but not importable yet - restart Blender")
        return {"FINISHED"}


class STEINWAY_OT_live(bpy.types.Operator):
    bl_idname = "steinway.live"
    bl_label = "Start"
    bl_description = "Start live MIDI - play your piano to move the keys in real time"

    _timer = None
    _port = None
    _state = None

    @classmethod
    def poll(cls, context):
        return not context.scene.steinway.running

    def invoke(self, context, event):
        props = context.scene.steinway
        if not midi.backend_available():
            self.report({"ERROR"}, "MIDI backend missing - install the bundled wheel first")
            return {"CANCELLED"}
        port_name = props.midi_port
        if not port_name or port_name == "__none__":
            self.report({"ERROR"}, "No MIDI input - plug in your piano and reopen the Port menu")
            return {"CANCELLED"}
        self._state = anim.LiveState(note_map=anim.build_note_map())
        if not self._state.note_map:
            self.report({"ERROR"}, "No piano in the scene - click Build Piano first")
            return {"CANCELLED"}
        try:
            self._port = midi.open_input(port_name)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"Could not open '{port_name}': {exc}")
            return {"CANCELLED"}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        props.running = True
        self.report({"INFO"}, f"Live: {port_name}")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        props = context.scene.steinway
        if not props.running or event.type == "ESC":
            return self._finish(context)
        if event.type == "TIMER":
            try:
                for note, pressed in midi.drain(self._port):
                    anim.set_note(self._state, note, pressed)
                anim.ease_step(self._state, props.press_angle, props.smoothing)
            except Exception as exc:  # noqa: BLE001
                self.report({"ERROR"}, f"MIDI error: {exc}")
                return self._finish(context)
            _redraw(context)
        return {"PASS_THROUGH"}

    def cancel(self, context):
        self._finish(context)

    def _finish(self, context):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        if self._port is not None:
            try:
                self._port.close()
            except Exception:  # noqa: BLE001
                pass
            self._port = None
        if self._state is not None:
            anim.reset(self._state)
            self._state = None
        context.scene.steinway.running = False
        _redraw(context)
        return {"FINISHED"}


class STEINWAY_OT_stop(bpy.types.Operator):
    bl_idname = "steinway.stop"
    bl_label = "Stop"
    bl_description = "Stop live MIDI"

    @classmethod
    def poll(cls, context):
        return context.scene.steinway.running

    def execute(self, context):
        context.scene.steinway.running = False
        return {"FINISHED"}


def _redraw(context):
    if context.screen is None:
        return
    for area in context.screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()


_CLASSES = (
    STEINWAY_OT_build,
    STEINWAY_OT_install_backend,
    STEINWAY_OT_live,
    STEINWAY_OT_stop,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
