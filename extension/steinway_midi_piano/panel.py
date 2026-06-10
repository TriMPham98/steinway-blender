"""Sidebar (N-panel) UI for the Steinway MIDI add-on."""

import bpy

from . import midi


class STEINWAY_PT_panel(bpy.types.Panel):
    bl_label = "Steinway MIDI"
    bl_idname = "STEINWAY_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Steinway MIDI"

    def draw(self, context):
        layout = self.layout
        props = context.scene.steinway

        ready = sum(1 for o in bpy.data.objects if o.get("midi_note") is not None)
        if ready >= 88:
            layout.label(text=f"Keys ready ({ready})", icon="CHECKMARK")
            hammers = sum(
                1 for o in bpy.data.objects if o.get("action_part") == "hammer"
            )
            if hammers >= 88:
                layout.label(text=f"Action ready ({hammers} hammers)", icon="CHECKMARK")
            else:
                layout.operator("steinway.build_action", icon="MOD_BUILD")
        else:
            layout.operator("steinway.prepare", icon="MOD_BUILD")

        box = layout.box()
        if midi.backend_available():
            box.label(text="MIDI backend ready", icon="CHECKMARK")
        else:
            box.label(text="MIDI backend missing", icon="ERROR")
            box.operator("steinway.install_backend", icon="IMPORT")
        box.prop(props, "midi_port", text="Port")

        row = layout.row(align=True)
        row.scale_y = 1.4
        if props.running:
            row.operator("steinway.stop", icon="PAUSE", depress=True)
        else:
            row.operator("steinway.live", icon="PLAY")

        col = layout.column(align=True)
        col.prop(props, "press_angle")
        col.prop(props, "snappiness")
        col.prop(props, "velocity_sensitivity")


def register():
    bpy.utils.register_class(STEINWAY_PT_panel)


def unregister():
    bpy.utils.unregister_class(STEINWAY_PT_panel)
