# Use a bpy.app.timer to register stuff that needs a valid context which isn't available during the normal registration

import bpy

from . import assets_manager, global_data


def startup_cb(*args):
    bpy.ops.view3d.slvs_register_draw_cb()
    assets_manager.load()
    return None


def register():
    bpy.app.timers.register(startup_cb, first_interval=1, persistent=True)


def unregister():
    handle = global_data.draw_handle
    if handle:
        bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
