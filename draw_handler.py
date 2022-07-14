import bpy
from . import global_data

def startup_cb(*args):
    bpy.ops.view3d.slvs_register_draw_cb()
    return None

def register():
    # Register drawcallback
    bpy.app.timers.register(startup_cb, first_interval=1, persistent=True)

def unregister():
    handle = global_data.draw_handle
    if handle:
        bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")