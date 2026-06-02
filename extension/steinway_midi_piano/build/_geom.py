"""Collection helpers shared by the retarget build step. Pure bpy, headless-safe."""

import bpy


def ensure_collection(name):
    """Return a scene collection with `name`, creating + linking it if needed."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_collection(name):
    """Remove a collection and every object inside it (idempotent rebuilds)."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for scene in bpy.data.scenes:
        if coll.name in scene.collection.children:
            scene.collection.children.unlink(coll)
    bpy.data.collections.remove(coll)
