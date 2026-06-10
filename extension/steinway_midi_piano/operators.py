"""Operators: build the model, install the MIDI backend, and run live playback."""

import os
import sys
import time
import subprocess

import bpy

from .build import retarget, action
from . import midi, anim

_TIMER_INTERVAL = 0.01   # modal timer period (s); also the first-frame dt seed


class STEINWAY_OT_prepare(bpy.types.Operator):
    bl_idname = "steinway.prepare"
    bl_label = "Prepare Imported Keys"
    bl_description = (
        "Split the imported model's joined White/Black key meshes into 88 "
        "MIDI-mapped key objects and tag the sustain pedal"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            summary = retarget.prepare()
        except Exception as exc:  # noqa: BLE001 - surface a clear message in the UI
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if summary.get("status") == "already-prepared":
            self.report({"INFO"}, "Keys already prepared")
        else:
            self.report(
                {"INFO"},
                f"Prepared {summary['white']}+{summary['black']} keys "
                f"(MIDI {summary['low']}..{summary['high']}); "
                f"pedal: {summary['pedal'] or 'not found'}",
            )
        return {"FINISHED"}


class STEINWAY_OT_build_action(bpy.types.Operator):
    bl_idname = "steinway.build_action"
    bl_label = "Build Double Escapement"
    bl_description = (
        "Build the 88-note grand action behind the fallboard - key arms with "
        "capstans and backchecks, wippens, jacks, repetition levers, and felt "
        "hammers that strike when you play"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.get("midi_note") is not None for o in bpy.data.objects)

    def execute(self, context):
        try:
            summary = action.build()
        except Exception as exc:  # noqa: BLE001 - surface a clear message in the UI
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Action built: {summary['notes']} notes, {summary['objects']} parts "
            f"(soundboard: {summary['soundboard']})",
        )
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
    _last_t = None

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
        self._state = anim.LiveState(
            note_map=anim.build_note_map(),
            pedal_obj=anim.find_pedal(),
            feel=anim.feel_from_props(props),
        )
        if not self._state.note_map:
            self.report(
                {"ERROR"},
                "No tagged keys - open the Steinway model and click Prepare Imported Keys",
            )
            return {"CANCELLED"}
        try:
            self._port = midi.open_input(port_name)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"Could not open '{port_name}': {exc}")
            return {"CANCELLED"}

        wm = context.window_manager
        self._timer = wm.event_timer_add(_TIMER_INTERVAL, window=context.window)
        self._last_t = time.perf_counter()
        wm.modal_handler_add(self)
        props.running = True
        self.report({"INFO"}, f"Live: {port_name}")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        props = context.scene.steinway
        if not props.running or event.type == "ESC":
            return self._finish(context)
        if event.type == "TIMER":
            now = time.perf_counter()
            dt = (now - self._last_t) if self._last_t is not None else _TIMER_INTERVAL
            self._last_t = now
            try:
                self._state.feel = anim.feel_from_props(props)
                for ev in midi.drain(self._port):
                    if ev[0] == "note":
                        anim.set_note(self._state, ev[1], ev[2])
                    elif ev[0] == "sustain":
                        anim.set_sustain(self._state, ev[1])
                anim.ease_step(self._state, props.press_angle, dt)
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
        self._last_t = None
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
    STEINWAY_OT_prepare,
    STEINWAY_OT_build_action,
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
