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

        layout.operator("steinway.build", icon="OUTLINER_OB_MESH")

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
        col.prop(props, "smoothing")


def register():
    bpy.utils.register_class(STEINWAY_PT_panel)


def unregister():
    bpy.utils.unregister_class(STEINWAY_PT_panel)
