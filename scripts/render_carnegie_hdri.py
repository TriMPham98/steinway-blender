"""Bake an equirectangular HDRI of the Carnegie Hall set for web-viewer IBL.

Renders ``assets/carnegie_hall.blend`` from the piano/listening position with a
Cycles panoramic camera and writes a Radiance ``.hdr`` the three.js viewer loads
into its PMREM environment (real hall reflections in the lacquer and gold plate).

Run headless::

    /Applications/Blender.app/Contents/MacOS/Blender -b assets/carnegie_hall.blend \
        --python scripts/render_carnegie_hdri.py

Output: ``web/public/env/carnegie.hdr`` (2048x1024, scene-linear via Raw view
transform so it drives IBL as radiance, not tone-mapped pixels).
"""
import math
import os

import bpy

# Ear height at the piano on stage (CamTarget sits at z=0.8). Capturing the probe
# here puts the auditorium in front of the instrument and the shell behind it.
PROBE_POS = (0.0, 0.0, 1.2)
RES_X, RES_Y = 2048, 1024
SAMPLES = 128

repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(repo, "web", "public", "env")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "carnegie.hdr")

scene = bpy.context.scene

# Cycles: EEVEE has no panoramic camera. CPU keeps this reproducible headless.
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True

# Equirectangular panoramic camera at the listening position, world up = image up.
cam_data = bpy.data.cameras.new("HDRIProbe")
cam_data.type = "PANO"
# Panorama type moved between native/cycles across versions; set whichever exists.
try:
    cam_data.panorama_type = "EQUIRECTANGULAR"
except (AttributeError, TypeError):
    cam_data.cycles.panorama_type = "EQUIRECTANGULAR"
cam_obj = bpy.data.objects.new("HDRIProbe", cam_data)
cam_obj.location = PROBE_POS
# +90deg X puts world +Z at the top of the equirect; +90deg Z aims the seam to
# the side so the stage front is centred.
cam_obj.rotation_euler = (math.radians(90), 0.0, math.radians(90))
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "HDR"

# Raw view transform: store scene-linear radiance, not a Filmic/AgX-graded image,
# so three.js PMREM treats it as light. Keep the look neutral.
try:
    scene.view_settings.view_transform = "Raw"
except TypeError:
    scene.view_settings.view_transform = "Standard"
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0

scene.render.filepath = out_path
print(f"[carnegie-hdri] rendering {RES_X}x{RES_Y} -> {out_path}")
bpy.ops.render.render(write_still=True)
print(f"[carnegie-hdri] wrote {out_path} ({os.path.getsize(out_path)} bytes)")
